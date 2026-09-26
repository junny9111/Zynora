import io
import os

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

    session_options.intra_op_num_threads = 2
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

        engine = get_kokoro()

        samples, sample_rate = engine.create(
            text,
            voice=voice_id,
            speed=speed,
            lang=language
        )

        if samples is None:
            return jsonify({
                "error": "No audio was generated."
            }), 500

        samples = np.asarray(
            samples,
            dtype=np.float32
        )

        if samples.size == 0:
            return jsonify({
                "error": "No audio was generated."
            }), 500

        # Prevent accidental clipping or invalid values
        # from reaching the WAV encoder.
        samples = np.nan_to_num(
            samples,
            nan=0.0,
            posinf=0.0,
            neginf=0.0
        )

        samples = np.clip(
            samples,
            -1.0,
            1.0
        )

        buffer = io.BytesIO()

        sf.write(
            buffer,
            samples,
            sample_rate,
            format="WAV",
            subtype="PCM_16"
        )

        buffer.seek(0)

        print(
            "Voice generation completed successfully.",
            "Sample rate:",
            sample_rate,
            "Samples:",
            samples.size,
            flush=True
        )

        return send_file(
            buffer,
            mimetype="audio/wav",
            as_attachment=False,
            download_name="zynora-voice.wav"
        )

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
