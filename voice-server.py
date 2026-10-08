import io
import os
import math
import threading
import time
from collections import OrderedDict

import numpy as np
import onnxruntime as ort
import soundfile as sf

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
from kokoro_onnx import Kokoro


app = Flask(__name__)

CORS(
    app,
    resources={
        r"/*": {
            "origins": "*",
            "methods": ["GET", "POST", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"]
        }
    }
)


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = (
        "Content-Type, Authorization"
    )
    response.headers["Access-Control-Allow-Methods"] = (
        "GET, POST, OPTIONS"
    )
    return response


MODEL_PATH = os.environ.get(
    "KOKORO_MODEL_PATH",
    "kokoro-v1.0.onnx"
)

VOICES_PATH = os.environ.get(
    "KOKORO_VOICES_PATH",
    "voices-v1.0.bin"
)


ALLOWED_VOICES = {
    "af_heart",
    "af_bella",
    "af_nicole",
    "af_sarah",
    "af_sky",
    "am_adam",
    "am_michael",
    "bf_emma",
    "bf_isabella",
    "bm_george",
    "bm_lewis"
}


kokoro_engine = None
inference_lock = threading.Lock()
audio_cache = OrderedDict()
cache_bytes = 0
MAX_CACHE_BYTES = 8 * 1024 * 1024
MAX_CACHE_ENTRIES = 16


@app.before_request
def log_request():
    print(
        "REQUEST:",
        request.method,
        request.path,
        "ORIGIN:",
        request.headers.get("Origin"),
        flush=True
    )


def get_kokoro():
    global kokoro_engine

    if kokoro_engine is not None:
        return kokoro_engine

    print(
        "Loading optimized Kokoro ONNX engine...",
        flush=True
    )

    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(
            "Kokoro model file was not found: " + MODEL_PATH
        )

    if not os.path.exists(VOICES_PATH):
        raise FileNotFoundError(
            "Kokoro voices file was not found: " + VOICES_PATH
        )

    # Optimized for the Render CPU environment.
    session_options = ort.SessionOptions()

    # One compute thread avoids contention on the shared free-tier CPU.
    session_options.intra_op_num_threads = 1
    session_options.add_session_config_entry("session.intra_op.allow_spinning", "0")
    session_options.add_session_config_entry("session.inter_op.allow_spinning", "0")
    session_options.inter_op_num_threads = 1

    session_options.execution_mode = (
        ort.ExecutionMode.ORT_SEQUENTIAL
    )

    session_options.graph_optimization_level = (
        ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    )

    # Keep ONNX Runtime's normal memory management enabled.
    # This generally gives smoother repeated inference than
    # disabling the memory arena.
    session_options.enable_cpu_mem_arena = True
    session_options.enable_mem_pattern = True

    print(
        "Creating ONNX Runtime session...",
        flush=True
    )

    session = ort.InferenceSession(
        MODEL_PATH,
        sess_options=session_options,
        providers=["CPUExecutionProvider"]
    )

    print(
        "ONNX Runtime session created.",
        flush=True
    )

    kokoro_engine = Kokoro.from_session(
        session,
        VOICES_PATH
    )

    print(
        "Kokoro ONNX engine loaded successfully.",
        flush=True
    )

    return kokoro_engine


def get_language(voice_id):
    if (
        voice_id.startswith("bf_")
        or
        voice_id.startswith("bm_")
    ):
        return "en-gb"

    return "en-us"


@app.route("/", methods=["GET", "OPTIONS"])
def home():
    return jsonify({
        "service": "Zynora Voice Server",
        "provider": "Kokoro ONNX INT8",
        "status": "online"
    })


@app.route("/health", methods=["GET", "OPTIONS"])
def health():
    return jsonify({
        "ok": True,
        "service": "zynora-voice",
        "provider": "kokoro-onnx-int8",
        "model_found": os.path.exists(MODEL_PATH),
        "voices_found": os.path.exists(VOICES_PATH),
        "engine_loaded": kokoro_engine is not None
    })


@app.route("/voices", methods=["GET", "OPTIONS"])
def voices():
    return jsonify({
        "voices": sorted(
            list(ALLOWED_VOICES)
        )
    })


@app.route("/speak", methods=["POST", "OPTIONS"])
def speak():
    global cache_bytes
    request_started = time.perf_counter()
    if request.method == "OPTIONS":
        return "", 204

    try:
        print(
            "Speak request received.",
            flush=True
        )

        data = request.get_json(
            silent=True
        ) or {}

        text = str(
            data.get(
                "text",
                ""
            )
        ).strip()

        voice_id = str(
            data.get(
                "voice",
                "af_heart"
            )
        ).strip()

        speed_value = data.get(
            "speed",
            1.0
        )

        if not text:
            return jsonify({
                "error": "Dialogue text is required."
            }), 400

        if len(text) > 500:
            return jsonify({
                "error": "Maximum preview length is 500 characters."
            }), 400

        if voice_id not in ALLOWED_VOICES:
            return jsonify({
                "error": "Invalid Zynora voice ID."
            }), 400

        try:
            speed = float(speed_value)

        except (
            TypeError,
            ValueError
        ):
            speed = 1.0

        if not math.isfinite(speed):
            speed = 1.0

        speed = max(
            0.7,
            min(
                speed,
                1.3
            )
        )

        language = get_language(
            voice_id
        )

        print(
            "Generating:",
            voice_id,
            "Language:",
            language,
            "Speed:",
            speed,
            "Characters:",
            len(text),
            flush=True
        )

        # Serialize inference to avoid competing model loads and CPU-heavy jobs.
        # Repeated dialogue/voice/speed combinations reuse the encoded WAV.
        cache_key = (text, voice_id, speed, language)
        with inference_lock:
            wav_bytes = audio_cache.get(cache_key)
            cache_hit = wav_bytes is not None
            if cache_hit:
                audio_cache.move_to_end(cache_key)
            else:
                engine = get_kokoro()
                inference_started = time.perf_counter()
                samples, sample_rate = engine.create(
                    text, voice=voice_id, speed=speed, lang=language
                )
                if samples is None:
                    raise ValueError("No audio was generated.")
                samples = np.asarray(samples, dtype=np.float32)
                if samples.size == 0:
                    raise ValueError("No audio was generated.")
                samples = np.clip(
                    np.nan_to_num(samples, nan=0.0, posinf=0.0, neginf=0.0),
                    -1.0, 1.0
                )
                buffer = io.BytesIO()
                sf.write(buffer, samples, sample_rate, format="WAV", subtype="PCM_16")
                wav_bytes = buffer.getvalue()
                inference_seconds = time.perf_counter() - inference_started
                print("VOICE TIMING: inference_seconds=",
                      round(inference_seconds, 3), "audio_seconds=",
                      round(samples.size / sample_rate, 3), flush=True)
                if len(wav_bytes) <= MAX_CACHE_BYTES:
                    audio_cache[cache_key] = wav_bytes
                    cache_bytes += len(wav_bytes)
                    while (cache_bytes > MAX_CACHE_BYTES or
                           len(audio_cache) > MAX_CACHE_ENTRIES):
                        _, removed = audio_cache.popitem(last=False)
                        cache_bytes -= len(removed)

        elapsed = time.perf_counter() - request_started
        print("Voice generation completed successfully.",
              "Total seconds:", round(elapsed, 3),
              "Cache hit:", cache_hit, flush=True)
        response = send_file(
            io.BytesIO(wav_bytes), mimetype="audio/wav",
            as_attachment=False, download_name="zynora-voice.wav"
        )
        response.headers["X-Zynora-Cache"] = "HIT" if cache_hit else "MISS"
        response.headers["Server-Timing"] = "voice;dur=" + str(round(elapsed * 1000, 1))
        return response

    except Exception as error:
        print(
            "VOICE ERROR:",
            repr(error),
            flush=True
        )

        return jsonify({
            "error": "Voice generation failed.",
            "details": str(error)
        }), 500


if __name__ == "__main__":
    port = int(
        os.environ.get(
            "PORT",
            10000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
