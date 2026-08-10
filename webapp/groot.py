"""
lsb_steganography.py
=====================
Classic LSB (Least Significant Bit) audio steganography, with an optional
password layer for a fair comparison against IamGroot.

Hides a message inside the last bit of each sample byte of a WAV cover
file. Needs an existing cover audio file -- unlike IamGroot, this does NOT
generate audio from the message; it just quietly edits an existing file.

Framing: a 4-byte big-endian length header is hidden first, telling the
decoder exactly how many more bits to read (same self-describing idea as
IamGroot's header -- no delimiter needed, so encrypted/binary payloads with
arbitrary byte values are handled safely).

Password (optional): derives a 256-bit key via PBKDF2-HMAC-SHA256
(200,000 iterations) and encrypts the message with AES-256-GCM *before* it
gets hidden. Wrong password -> decryption fails outright (GCM's built-in
authentication tag rejects it), never garbled/partial text.

Usage:
    python lsb_steganography.py encode groot.wav "secret text" out.wav
    python lsb_steganography.py encode groot.wav "secret text" out.wav mypassword
    python lsb_steganography.py decode out.wav
    python lsb_steganography.py decode out.wav mypassword

Requires: pip install cryptography
"""
import os
import sys
import wave

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

SALT_LEN = 16
NONCE_LEN = 12
PBKDF2_ITERATIONS = 200_000


# --------------------------------------------------------------------------
# Password layer (same design as IamGroot's crypto.py)
# --------------------------------------------------------------------------
def _derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt,
                      iterations=PBKDF2_ITERATIONS)
    return kdf.derive(password.encode("utf-8"))


def _encrypt(plaintext: bytes, password: str) -> bytes:
    salt = os.urandom(SALT_LEN)
    nonce = os.urandom(NONCE_LEN)
    key = _derive_key(password, salt)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, associated_data=None)
    return salt + nonce + ciphertext


def _decrypt(blob: bytes, password: str) -> bytes:
    if len(blob) < SALT_LEN + NONCE_LEN:
        raise ValueError("Payload too short to be a valid encrypted message.")
    salt = blob[:SALT_LEN]
    nonce = blob[SALT_LEN:SALT_LEN + NONCE_LEN]
    ciphertext = blob[SALT_LEN + NONCE_LEN:]
    key = _derive_key(password, salt)
    try:
        return AESGCM(key).decrypt(nonce, ciphertext, associated_data=None)
    except Exception as e:
        raise ValueError("Wrong password (or corrupted/tampered audio).") from e


# --------------------------------------------------------------------------
# Bit-level helpers
# --------------------------------------------------------------------------
def _bytes_to_bits(data: bytes) -> str:
    return "".join(format(b, "08b") for b in data)


def _bits_to_bytes(bits: str) -> bytes:
    return bytes(int(bits[i:i + 8], 2) for i in range(0, len(bits), 8))


# --------------------------------------------------------------------------
# Encode / decode
# --------------------------------------------------------------------------
def encode( message: str, output_path: str,cover_path: str = 'groot.wav', password: str = None) -> None:
    audio = wave.open(cover_path, "rb")
    frame_bytes = bytearray(audio.readframes(audio.getnframes()))
    params = audio.getparams()
    audio.close()

    payload = message.encode("utf-8")
    if password:
        payload = _encrypt(payload, password)

    header = len(payload).to_bytes(4, "big")  # self-describing length, no delimiter needed
    bits = _bytes_to_bits(header + payload)

    if len(bits) > len(frame_bytes):
        raise ValueError(
            f"Message too long for this cover file: need {len(bits)} sample "
            f"bytes, only {len(frame_bytes)} available. Use a longer cover "
            f"clip or a shorter message."
        )

    for i, bit in enumerate(bits):
        frame_bytes[i] = (frame_bytes[i] & 0b11111110) | int(bit)

    out = wave.open(output_path, "wb")
    out.setparams(params)
    out.writeframes(bytes(frame_bytes))
    out.close()
    print(f"Encoded -> {output_path}" + (" (password-protected)" if password else ""))


def decode(stego_path: str, password: str = None) -> str:
    audio = wave.open(stego_path, "rb")
    frame_bytes = bytearray(audio.readframes(audio.getnframes()))
    audio.close()

    all_bits = "".join(str(b & 1) for b in frame_bytes)

    header_bits = all_bits[:32]
    payload_len = int(header_bits, 2) if len(header_bits) == 32 else 0
    if payload_len <= 0 or payload_len > len(frame_bytes):
        raise ValueError("No valid hidden message found in this file.")

    payload_bits = all_bits[32: 32 + payload_len * 8]
    payload = _bits_to_bytes(payload_bits)

    if password:
        payload = _decrypt(payload, password)

    try:
        return payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise ValueError(
            "Couldn't read this as plain text -- it looks like this message "
            "was encoded with a password. Supply the password to decode it."
        )


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    mode = sys.argv[1]
    if mode == "encode":
        if len(sys.argv) not in (5, 6):
            print('Usage: python lsb_steganography.py encode cover.wav "text" out.wav [password]')
            sys.exit(1)
        cover, msg, out = sys.argv[2], sys.argv[3], sys.argv[4]
        pw = sys.argv[5] if len(sys.argv) == 6 else None
        encode(cover, msg, out, password=pw)
    elif mode == "decode":
        if len(sys.argv) not in (3, 4):
            print("Usage: python lsb_steganography.py decode stego.wav [password]")
            sys.exit(1)
        stego = sys.argv[2]
        pw = sys.argv[3] if len(sys.argv) == 4 else None
        print("Decoded message:", decode(stego, password=pw))
    else:
        print(__doc__)
        sys.exit(1)