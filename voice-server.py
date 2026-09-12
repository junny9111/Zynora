import io
import os

import soundfile as sf

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
from kokoro_onnx import Kokoro


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

    response.headers[
        "Access-Control-Allow-Origin"
    ] = "*"

    response.headers[
        "Access-Control-Allow-Headers"
    ] = (
        "Content-Type, Authorization"
    )

    response.headers[
        "Access-Control-Allow-Methods"
    ] = (
        "GET, POST, OPTIONS"
    )

    return response


# ---------------------------------------------------------
# SETTINGS
# ---------------------------------------------------------

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
# LOAD LIGHTWEIGHT ONNX ENGINE
# ---------------------------------------------------------

def get_kokoro():

    global kokoro_engine


    if kokoro_engine is None:

        print(
            "Loading Kokoro ONNX engine...",
            flush=True
        )


        if not os.path.exists(
            MODEL_PATH
        ):

            raise FileNotFoundError(
                "Kokoro model file was not found: "
                +
                MODEL_PATH
            )


        if not os.path.exists(
            VOICES_PATH
        ):

            raise FileNotFoundError(
                "Kokoro voices file was not found: "
                +
                VOICES_PATH
            )


        kokoro_engine = Kokoro(
            MODEL_PATH,
            VOICES_PATH
        )


        print(
            "Kokoro ONNX engine loaded.",
            flush=True
        )


    return kokoro_engine


# ---------------------------------------------------------
# LANGUAGE FOR VOICE
# ---------------------------------------------------------

def get_language(
    voice_id
):

    if (
        voice_id.startswith(
            "bf_"
        )
        or
        voice_id.startswith(
            "bm_"
        )
    ):

        return "en-gb"


    return "en-us"


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
        "Kokoro ONNX",

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
        "kokoro-onnx",

        "model_found":
        os.path.exists(
            MODEL_PATH
        ),

        "voices_found":
        os.path.exists(
            VOICES_PATH
        )
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
        # VALIDATE TEXT
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
        # VALIDATE VOICE
        # ---------------------------------------------

        if voice_id not in ALLOWED_VOICES:

            return jsonify({
                "error":
                "Invalid Zynora voice ID."
            }), 400


        # ---------------------------------------------
        # VALIDATE SPEED
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
            flush=True
        )


        # ---------------------------------------------
        # LOAD ONNX ENGINE
        # ---------------------------------------------

        engine = get_kokoro()


        # ---------------------------------------------
        # GENERATE AUDIO
        # ---------------------------------------------

        samples, sample_rate = (
            engine.create(
                text,
                voice=voice_id,
                speed=speed,
                lang=language
            )
        )


        if (
            samples is None
            or
            len(samples) == 0
        ):

            return jsonify({
                "error":
                "No audio was generated."
            }), 500


        # ---------------------------------------------
        # CREATE WAV IN MEMORY
        # ---------------------------------------------

        buffer = io.BytesIO()


        sf.write(
            buffer,
            samples,
            sample_rate,
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
            download_name=
            "zynora-voice.wav"
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
        host=
        "0.0.0.0",

        port=
        port
    )
