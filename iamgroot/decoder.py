"""
decoder.py
==========
Public entry point: decode(wav_path, password=None) -> str.

Reads the wav, chops it into fixed-duration symbol segments (SYMBOL_MS
each -- a global constant, not stored anywhere, so no key is needed for
the STEGANOGRAPHIC layer), measures pitch/loudness per segment, requantizes
to bit levels, decodes the self-protected header first to learn the
payload length and whether it's encrypted, then decodes the payload and
runs Reed-Solomon error correction to recover the original bytes.

If the header says the payload is encrypted, `password` must be supplied
and match what was used at encode time, or AES-GCM's authentication check
fails and no plaintext is produced -- by design.
"""
import struct
from typing import Optional

import numpy as np
import librosa

from . import config, ecc, crypto
from .bitstream import bits_to_bytes
from .acoustic import measure_segment, target_to_levels, symbol_levels_to_bits
from .vocoder import samples_per_symbol


def _load_audio(wav_path: str) -> np.ndarray:
    x, sr = librosa.load(wav_path, sr=config.SAMPLE_RATE, mono=True)
    return x.astype(np.float64)


def _read_symbols(x: np.ndarray, n_symbols: int, start_symbol: int = 0):
    sps = samples_per_symbol()
    bits = []
    for s in range(start_symbol, start_symbol + n_symbols):
        lo = s * sps
        hi = lo + sps
        seg = x[lo:hi] if hi <= len(x) else np.pad(x[lo:], (0, max(0, hi - len(x))))
        target = measure_segment(seg, config.SAMPLE_RATE)
        levels = target_to_levels(target)
        bits.extend(symbol_levels_to_bits(levels))
    return bits


def decode(wav_path: str, password: Optional[str] = None) -> str:
    x = _load_audio(wav_path)

    # --- Step 1: read the fixed-size, self-protected header ---
    header_bits = _read_symbols(x, config.HEADER_SYMBOLS, start_symbol=0)
    header_bytes_raw = bits_to_bytes(header_bits)[:config.HEADER_TOTAL_BYTES]
    header_data = ecc.rs_decode(header_bytes_raw, config.HEADER_ECC_BYTES)
    rs_total_len, ecc_len, encrypted_flag = struct.unpack(">HBB", header_data)

    # --- Step 2: compute how many payload symbols follow, then read them ---
    payload_bit_len = rs_total_len * 8
    payload_symbols = -(-payload_bit_len // config.BITS_PER_SYMBOL)  # ceil div

    payload_bits = _read_symbols(x, payload_symbols, start_symbol=config.HEADER_SYMBOLS)
    rs_payload = bits_to_bytes(payload_bits)[:rs_total_len]

    # --- Step 3: Reed-Solomon correct ---
    raw_bytes = ecc.rs_decode(rs_payload, ecc_len)

    # --- Step 4: decrypt if needed ---
    if encrypted_flag:
        if not password:
            print("IamGroot decode failed: This message is password-protected, but no password was given")
            return
            # raise ValueError(
            #     "IamGroot decode failed: this message is password-protected "
            #     "but no password was given."
            # )
        raw_bytes = crypto.decrypt(raw_bytes, password)
    elif password:
        # A password was given but the message wasn't encrypted with one --
        # not an error, just ignore it (message decodes fine either way).
        pass
    if raw_bytes:
        return raw_bytes.decode("utf-8", errors="strict")
    return
