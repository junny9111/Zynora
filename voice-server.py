import io
import os

import numpy as np
import soundfile as sf

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
from kokoro import KPipeline


app = Flask(__name__)

CORS(
    app,
    resources={
        r"/*": {
            "origins": [
                "https://junny9111.github.io"
            ]
        }
    }
)


SAMPLE_RATE = 24000


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


american_pipeline = None
british_pipeline = None


def get_pipeline(voice_id):

    global american_pipeline
    global british_pipeline

    if voice_id.startswith("bf_") or voice_id.startswith("bm_"):

        if british_pipeline is None:
            british_pipeline = KPipeline(
                lang_code="b"
            )

        return british_pipeline

    if american_pipeline is None:
        american_pipeline = KPipeline(
            lang_code="a"
        )

    return american_pipeline


def audio_to_numpy(audio):

    if hasattr(audio, "detach"):
        audio = audio.detach()

    if hasattr(audio, "cpu"):
        audio = audio.cpu()

    if hasattr(audio, "numpy"):
        audio = audio.numpy()

    return np.asarray(
        audio,
        dtype=np.float32
    )


@app.route("/", methods=["GET"])
def home():

    return jsonify({
        "service": "Zynora Voice Server",
        "provider": "Kokoro",
        "status": "online"
    })


@app.route("/health", methods=["GET"])
def health():

    return jsonify({
        "ok": True,
        "service": "zynora-voice",
        "provider": "kokoro"
    })


@app.route("/voices", methods=["GET"])
def voices():

    return jsonify({
        "voices": sorted(
            list(ALLOWED_VOICES)
        )
    })


@app.route("/speak", methods=["POST"])
def speak():

    try:

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
                "error":
                "Dialogue text is required."
            }), 400


        if len(text) > 1500:

            return jsonify({
                "error":
                "Maximum dialogue length is 1500 characters."
            }), 400


        if voice_id not in ALLOWED_VOICES:

            return jsonify({
                "error":
                "Invalid Zynora voice ID."
            }), 400


        try:

            speed = float(
                speed_value
            )

        except (TypeError, ValueError):

            speed = 1.0


        speed = max(
            0.7,
            min(
                speed,
                1.3
            )
        )


        pipeline = get_pipeline(
            voice_id
        )


        generator = pipeline(
            text,
            voice=voice_id,
            speed=speed
        )


        audio_parts = []


        for _, _, audio in generator:

            if audio is None:
                continue

            audio_array = audio_to_numpy(
                audio
            )

            if audio_array.size:
                audio_parts.append(
                    audio_array
                )


        if not audio_parts:

            return jsonify({
                "error":
                "No audio was generated."
            }), 500


        final_audio = np.concatenate(
            audio_parts
        )


        buffer = io.BytesIO()


        sf.write(
            buffer,
            final_audio,
            SAMPLE_RATE,
            format="WAV"
        )


        buffer.seek(0)


        return send_file(
            buffer,
            mimetype="audio/wav",
            as_attachment=False,
            download_name="zynora-voice.wav"
        )


    except Exception as error:

        print(
            "VOICE ERROR:",
            repr(error)
        )

        return jsonify({
            "error":
            "Voice generation failed.",
            "details":
            str(error)
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
