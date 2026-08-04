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

from iamgroot import encode, decode, config, ecc  # noqa: E402

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024  # 25MB upload ceiling

AES_OVERHEAD_BYTES = 16 + 12 + 16  # salt + nonce + GCM tag


def max_chars(encrypted: bool) -> int:
    """Largest message (in UTF-8 bytes, treated as chars for the ASCII-ish
    common case) that still gets the FULL intended ECC ratio -- not just
    barely fitting in the 255-byte GF(256) block. If we only checked "fits
    at all", compute_ecc_len's self-capping means almost any length
    trivially fits with degraded (unsafe) redundancy."""
    overhead = AES_OVERHEAD_BYTES if encrypted else 0
    lo, hi = 1, config.MAX_RS_BLOCK
    best = 0
    while lo <= hi:
        mid = (lo + hi) // 2
        data_len = mid + overhead
        if data_len >= config.MAX_RS_BLOCK:
            hi = mid - 1
            continue
        desired_ecc = max(config.MIN_ECC_BYTES, math.ceil(data_len * config.PAYLOAD_ECC_RATIO))
        actual_ecc = ecc.compute_ecc_len(data_len)
        if actual_ecc >= desired_ecc and data_len + actual_ecc <= config.MAX_RS_BLOCK:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def estimate_duration_seconds(n_chars: int, encrypted: bool) -> float:
    data_len = n_chars + (AES_OVERHEAD_BYTES if encrypted else 0)
    ecc_len = ecc.compute_ecc_len(data_len)
    rs_total = data_len + ecc_len
    payload_symbols = -(-(rs_total * 8) // config.BITS_PER_SYMBOL)
    total_symbols = config.HEADER_SYMBOLS + payload_symbols
    return round(total_symbols * config.SYMBOL_MS / 1000.0, 2)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/estimate")
def api_estimate():
    n = request.args.get("chars", default=0, type=int)
    encrypted = request.args.get("encrypted", default="false") == "true"
    cap = max_chars(encrypted)
    n = max(0, n)
    return jsonify({
        "max_chars": cap,
        "duration_seconds": estimate_duration_seconds(min(n, cap) if n else 0, encrypted),
        "fits": n <= cap,
    })


@app.route("/api/encode", methods=["POST"])
def api_encode():
    data = request.get_json(silent=True) or {}
    text = (data.get("message") or "").strip()
    password = (data.get("password") or "").strip() or None

    if not text:
        return jsonify({"error": "Write something for the voice to carry first."}), 400

    cap = max_chars(password is not None)
    if len(text.encode("utf-8")) > cap:
        return jsonify({
            "error": f"That message is too long for one breath of audio. "
                     f"Keep it to about {cap} characters"
                     + (" when a password is set (encryption adds overhead)." if password else ".")
        }), 400

    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(suffix=".wav")
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
        mimetype="audio/wav",
        as_attachment=True,
        download_name="iamgroot_message.wav",
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
    app.run(debug=True, use_reloader=False, port=5000)
