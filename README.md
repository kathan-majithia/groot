# IamGroot Steganographic Encoder

Hide any text message inside a single, natural-length "I am Groot" audio
clip. The clip's pitch and loudness vary in a unique, message-specific way.
**No database, no external key file needed** — everything needed to
recover the text lives inside the wav file itself. An optional password
adds real AES-256-GCM encryption on top (see below).

## How it works (short version)

1. Your text is turned into bytes, then protected with Reed-Solomon error
   correction (so it survives compression, re-recording, background noise).
2. A small self-protected header is prepended, telling the decoder exactly
   how many more "symbols" of audio to expect.
3. The whole bitstream is sliced into ~90ms chunks ("symbols"). Each chunk's
   bits set an absolute pitch (Hz) and an absolute loudness (dB) target.
4. A single seed utterance of "I am Groot" (via `espeak-ng`) is stretched or
   compressed with the WORLD vocoder (`pyworld`) to exactly as many symbols
   as needed, with each symbol's pitch/loudness forced to its target value.
5. Decoding reverses this: measure pitch (YIN) and loudness (RMS dB) of each
   fixed-duration segment, requantize to bits, Reed-Solomon-correct, decode
   header then payload, recover the original UTF-8 text.

Longer messages → longer audio. No repetition of the phrase — just one
continuous, longer or shorter "I am Groot".

## Setup

```bash
# system dependency
sudo apt install espeak-ng      # Debian/Ubuntu
# or: brew install espeak-ng    # macOS

pip install -r requirements.txt
```

## Usage

```bash
# Encode (no password -- pure steganography)
python -m iamgroot encode "Hello, My name is Kathan" out.wav

# Encode WITH a password (AES-256-GCM encryption before steganography)
python -m iamgroot encode "Hello, My name is Kathan" out.wav groot123

# Decode
python -m iamgroot decode out.wav

# Decode a password-protected message (wrong password -> clear error, no plaintext)
python -m iamgroot decode out.wav groot123
```

Or from Python:

```python
from iamgroot import encode, decode

encode("Hello, world!", "secret.wav")
text = decode("secret.wav")   # -> "Hello, world!"

# with a password
encode("Top secret", "secret2.wav", password="groot123")
text = decode("secret2.wav", password="groot123")   # -> "Top secret"
decode("secret2.wav", password="wrong")              # -> raises ValueError
decode("secret2.wav")                                # -> raises ValueError (no password given)
```

### About the password layer

`crypto.py` derives a 256-bit key from your password via PBKDF2-HMAC-SHA256
(200,000 iterations) and encrypts the message with AES-256-GCM *before* it
ever gets turned into audio. GCM includes a built-in authenticity tag, so:

- Right password -> exact plaintext back.
- Wrong password -> decryption fails outright (tag check rejects it) --
  never a garbled/partial result, just a clear error.
- The salt and nonce (not secret) travel inside the audio itself, same as
  everything else in this scheme. Only the password is secret, and it's
  never written to the file -- you must supply it again to decode.

This turns the project into steganography *and* real encryption, which is
a natural fit for a security-course "voice-based steganography" project:
the audio hides that a message exists, and (with a password) the message
is genuinely unreadable without the right key even if someone suspects
and extracts the hidden bits.

Run the built-in self-test:

```bash
python3 -m iamgroot.selftest
```

## Tuning (config.py)

- `F0_BITS` / `ENERGY_BITS`: bits per acoustic channel per symbol. More
  bits = more capacity per second of audio, but more fragile to noise.
- `SYMBOL_MS`: duration of one data-carrying audio chunk. Longer = more
  robust, shorter = more capacity per second.
- `PAYLOAD_ECC_RATIO` / `MIN_ECC_BYTES`: how much Reed-Solomon redundancy
  to add. Tuned empirically against this project's own measured ~5-7%
  acoustic bit-error rate on continuous multi-symbol audio (currently 1.6
  = 160% parity overhead, validated at 100/100 and 60/60 stress-test runs).
- `SMOOTHING_KERNEL_FRAC`: how much of each symbol's boundary blends into
  its neighbor, for a less robotic "staircase" sound. Swept empirically:
  higher values sound smoother but cost decode reliability -- 0.25 is the
  current safe setting after re-validating against `PAYLOAD_ECC_RATIO`.

## Known limitations

- Single Reed-Solomon block, so total (data + ECC) bytes must stay under
  255 (a GF(256) hard limit) — caps messages at roughly 90-100 characters
  with the default ECC ratio. Chunking into multiple RS blocks would lift
  this, and is a natural next step.
- Timbre/formant channel was prototyped and dropped: it landed in the
  wrong quantization bin >40% of the time and degraded pitch accuracy, so
  the scheme currently uses two channels (pitch + loudness), not three.
- Every symbol is fully "voiced" with forced pitch (needed for the decoder
  to reliably read it), so the audio has a buzzy, semi-monotone quality
  rather than perfectly natural movie-Groot speech. This is an intrinsic
  tradeoff of the steganographic design, not a bug: a fully natural voice
  (with real consonants, silences, natural prosody) has far less "room" to
  reliably carry absolute-valued hidden data. Light smoothing is applied at
  symbol boundaries to reduce the robotic "staircase" effect without
  hurting decode reliability.

## Roadmap notes (for the website version)

- Wrap `encode`/`decode` in a FastAPI backend; keep this package's logic
  fully decoupled from any web/CLI concerns (already the case).
- Multi-block Reed-Solomon chunking for longer messages.
- Password/AES-GCM layer is implemented (see above) -- for a production
  site, consider also rate-limiting password attempts against a given
  audio file if it's ever exposed via a public decode endpoint.
