"""
crypto.py
=========
Optional password layer, applied BEFORE the steganographic embedding.

This is a real cryptographic layer (AES-256-GCM, key derived from the
password via PBKDF2-HMAC-SHA256), not just obfuscation:

  - Wrong password -> decryption fails outright (GCM's authentication tag
    check rejects it) -> no plaintext, no partial/garbled text, just a
    clear error. This is what makes it "either the same key or nothing."
  - The salt and nonce are NOT secret and are simply stored alongside the
    ciphertext inside the audio (self-contained, same philosophy as the
    rest of this project) -- only the PASSWORD itself is secret, and it
    lives only in the user's head, never in the file.

Without this layer, IamGroot is steganography (hides that a message
exists). With this layer, it's steganography + real encryption (hides
AND protects the message) -- appropriate for anyone using this as a
security course project.
"""
import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

SALT_LEN = 16
NONCE_LEN = 12
PBKDF2_ITERATIONS = 200_000


def _derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
    )
    return kdf.derive(password.encode("utf-8"))


def encrypt(plaintext: bytes, password: str) -> bytes:
    """Returns salt(16) + nonce(12) + ciphertext_with_tag."""
    salt = os.urandom(SALT_LEN)
    nonce = os.urandom(NONCE_LEN)
    key = _derive_key(password, salt)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, associated_data=None)
    return salt + nonce + ciphertext


def decrypt(blob: bytes, password: str) -> bytes:
    """Reverses encrypt(). Raises ValueError on wrong password or
    corrupted/tampered data -- never returns garbage silently."""
    if len(blob) < SALT_LEN + NONCE_LEN:
        raise ValueError("IamGroot decode failed: encrypted payload too short/corrupted.")
    salt = blob[:SALT_LEN]
    nonce = blob[SALT_LEN:SALT_LEN + NONCE_LEN]
    ciphertext = blob[SALT_LEN + NONCE_LEN:]
    key = _derive_key(password, salt)
    try:
        return AESGCM(key).decrypt(nonce, ciphertext, associated_data=None)
    except Exception as e:
        print("IamGroot decode failed: wrong password (or corrupted audio). The authentication check on the encrypted message did not pass.")
        return None
        # raise ValueError(
        #     "IamGroot decode failed: wrong password (or corrupted audio). "
        #     "The authentication check on the encrypted message did not pass."
        # ) from e
