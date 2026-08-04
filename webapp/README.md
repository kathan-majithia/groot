# IamGroot -- web UI

A small Flask front end over the `iamgroot` package: write a message, get a
downloadable voice clip; upload a clip, get the message back. Optional
password gives real AES-256-GCM encryption underneath the steganography.

## Run it

```bash
# from the iamgroot_proj/ directory (one level up from here)
pip install -r webapp/requirements.txt
sudo apt install espeak-ng     # if you haven't already, for the core package

python webapp/app.py
```

Then open **http://127.0.0.1:5000**.

## What's here

```
webapp/
  app.py                  Flask backend: /api/estimate, /api/encode, /api/decode
  templates/index.html    Page markup
  static/css/style.css    Styling
  static/js/main.js       Tabs, live char/duration estimate, drag-and-drop, requests
```

`app.py` imports the existing `iamgroot` package directly (it's the sibling
folder one level up) -- nothing in `iamgroot/` was touched to build this.

## Notes

- Nothing is persisted server-side: uploaded/generated audio lives in a
  temp file for the duration of one request only, then is deleted.
- `/api/estimate` powers the live character-counter and duration estimate
  in the UI -- it recomputes the real Reed-Solomon capacity (which shrinks
  when a password is set, since AES-GCM adds ~44 bytes of overhead).
- For anything beyond local testing, run behind a real WSGI server
  (gunicorn/uwsgi) instead of Flask's dev server, and set
  `app.config["MAX_CONTENT_LENGTH"]` (already set to 25MB) appropriately
  for your deployment.
