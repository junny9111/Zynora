import io
import os

import numpy as np
import soundfile as sf

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
from kokoro import KPipeline


app = Flask(__name__)


# ---------------------------------------------------------
# CORS
# ---------------------------------------------------------

CORS(
    app,
    resources={
        r"/*": {
            "origins": "*",
            "methods": [
                "GET",
                "POST",
                "OPTIONS"
            ],
            "allow_headers": [
                "Content-Type",
                "Authorization"
            ]
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


# ---------------------------------------------------------
# SETTINGS
# ---------------------------------------------------------

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


# ---------------------------------------------------------
# REQUEST LOGGING
# ---------------------------------------------------------

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


# ---------------------------------------------------------
# KOKORO PIPELINE
# ---------------------------------------------------------

def get_pipeline(voice_id):

    global american_pipeline
    global british_pipeline


    if (
        voice_id.startswith("bf_")
        or
        voice_id.startswith("bm_")
    ):

        if british_pipeline is None:

            print(
                "Loading British Kokoro pipeline...",
                flush=True
            )

            british_pipeline = KPipeline(
                lang_code="b"
            )

        return british_pipeline


    if american_pipeline is None:

        print(
            "Loading American Kokoro pipeline...",
            flush=True
        )

        american_pipeline = KPipeline(
            lang_code="a"
        )


    return american_pipeline


def audio_to_numpy(audio):

    if hasattr(
        audio,
        "detach"
    ):

        audio = audio.detach()


    if hasattr(
        audio,
        "cpu"
    ):

        audio = audio.cpu()


    if hasattr(
        audio,
        "numpy"
    ):

        audio = audio.numpy()


    return np.asarray(
        audio,
        dtype=np.float32
    )


# ---------------------------------------------------------
# HOME
# ---------------------------------------------------------

@app.route(
    "/",
    methods=[
        "GET",
        "OPTIONS"
    ]
)
def home():

    return jsonify({
        "service":
        "Zynora Voice Server",

        "provider":
        "Kokoro",

        "status":
        "online"
    })


# ---------------------------------------------------------
# HEALTH
# ---------------------------------------------------------

@app.route(
    "/health",
    methods=[
        "GET",
        "OPTIONS"
    ]
)
def health():

    return jsonify({
        "ok":
        True,

        "service":
        "zynora-voice",

        "provider":
        "kokoro"
    })


# ---------------------------------------------------------
# VOICES
# ---------------------------------------------------------

@app.route(
    "/voices",
    methods=[
        "GET",
        "OPTIONS"
    ]
)
def voices():

    return jsonify({
        "voices":
        sorted(
            list(
                ALLOWED_VOICES
            )
        )
    })


# ---------------------------------------------------------
# SPEAK
# ---------------------------------------------------------

@app.route(
    "/speak",
    methods=[
        "POST",
        "OPTIONS"
    ]
)
def speak():

    if request.method == "OPTIONS":

        return (
            "",
            204
        )


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


        # ---------------------------------------------
        # Validate text
        # ---------------------------------------------

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


        # ---------------------------------------------
        # Validate voice
        # ---------------------------------------------

        if voice_id not in ALLOWED_VOICES:

            return jsonify({
                "error":
                "Invalid Zynora voice ID."
            }), 400


        # ---------------------------------------------
        # Validate speed
        # ---------------------------------------------

        try:

            speed = float(
                speed_value
            )

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


        print(
            "Generating voice:",
            voice_id,
            flush=True
        )


        # ---------------------------------------------
        # Load model
        # ---------------------------------------------

        pipeline = get_pipeline(
            voice_id
        )


        # ---------------------------------------------
        # Generate audio
        # ---------------------------------------------

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

            print(
                "No audio generated.",
                flush=True
            )

            return jsonify({
                "error":
                "No audio was generated."
            }), 500


        final_audio = np.concatenate(
            audio_parts
        )


        # ---------------------------------------------
        # WAV
        # ---------------------------------------------

        buffer = io.BytesIO()


        sf.write(
            buffer,
            final_audio,
            SAMPLE_RATE,
            format="WAV"
        )


        buffer.seek(0)


        print(
            "Voice generation completed.",
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
            "error":
            "Voice generation failed.",

            "details":
            str(error)
        }), 500


# ---------------------------------------------------------
# START
# ---------------------------------------------------------

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
