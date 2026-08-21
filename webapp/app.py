"""
app.py
======
Flask backend for the IamGroot web UI. Wraps the existing iamgroot package
(encode/decode) behind two JSON endpoints, plus a capacity/duration
estimator so the frontend can show live feedback as the user types.

Run:
    cd webapp
    python app.py
Then open http://127.0.0.1:5000
"""
import io
import os
import sys
import math
import tempfile
import traceback

from flask import Flask, request, jsonify, send_file, render_template

# Make the sibling `iamgroot` package importable regardless of cwd.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from groot import encode, decode

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024  # 25MB upload ceiling

AES_OVERHEAD_BYTES = 16 + 12 + 16  # salt + nonce + GCM tag

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/encode", methods=["POST"])
def api_encode():
    data = request.get_json(silent=True) or {}
    text = (data.get("message") or "").strip()
    password = (data.get("password") or "").strip() or None

    if not text:
        return jsonify({"error": "Write something for the voice to carry first."}), 400

    # cap = max_chars(password is not None)
    # if len(text.encode("utf-8")) > cap:
    #     return jsonify({
    #         "error": f"That message is too long for one breath of audio. "
    #                  f"Keep it to about {cap} characters"
    #                  + (" when a password is set (encryption adds overhead)." if password else ".")
    #     }), 400

    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(suffix=".mp3")
        os.close(fd)
        encode(text, tmp_path, password=password)
        with open(tmp_path, "rb") as f:
            audio_bytes = f.read()
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"Couldn't grow that into a voice: {e}"}), 500
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)

    return send_file(
        io.BytesIO(audio_bytes),
        mimetype="audio/mp3",
        as_attachment=True,
        download_name="iamgroot_message.mp3",
    )


@app.route("/api/decode", methods=["POST"])
def api_decode():
    if "audio" not in request.files:
        return jsonify({"error": "No audio file arrived with that request."}), 400

    audio_file = request.files["audio"]
    if audio_file.filename == "":
        return jsonify({"error": "Choose a .wav file to reveal first."}), 400

    password = (request.form.get("password") or "").strip() or None

    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        audio_file.save(tmp_path)
        message = decode(tmp_path, password=password)
    except ValueError as e:
        return jsonify({"error": str(e)}), 422
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"That audio didn't decode cleanly: {e}"}), 500
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)

    return jsonify({"message": message})


if __name__ == "__main__":
    # use_reloader=False: the debug reloader watches the whole Python
    # environment for changes, including site-packages. On some setups
    # (seen on Windows with librosa/lazy_loader) it falsely detects a
    # change mid-request and restarts the server, killing whatever
    # encode/decode call was in flight. debug=True still gives you the
    # in-browser traceback on errors -- just without the flaky auto-reload.
    app.run(host="0.0.0.0", debug=False, use_reloader=False, port=5000)
