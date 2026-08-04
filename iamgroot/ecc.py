"""
ecc.py
======
Thin wrapper around `reedsolo` for adding/removing error-correction
redundancy. Reed-Solomon lets the decoder repair a limited number of
corrupted BYTES even when it doesn't know in advance which bytes are bad --
essential here because pitch/loudness/timbre extraction from real-world
audio (mic playback, mp3 compression, etc.) will always introduce some
bit errors.
"""
import math
from reedsolo import RSCodec, ReedSolomonError

from . import config


def compute_ecc_len(data_len: int) -> int:
    """How many parity bytes to use for a payload of `data_len` bytes."""
    ecc = max(config.MIN_ECC_BYTES, math.ceil(data_len * config.PAYLOAD_ECC_RATIO))
    if data_len + ecc > config.MAX_RS_BLOCK:
        ecc = config.MAX_RS_BLOCK - data_len
    return ecc


def rs_encode(data: bytes, ecc_len: int) -> bytes:
    rsc = RSCodec(ecc_len)
    return bytes(rsc.encode(data))


def rs_decode(data: bytes, ecc_len: int) -> bytes:
    """Raises ValueError with a clear message if the block is unrecoverable."""
    rsc = RSCodec(ecc_len)
    try:
        decoded, _, _ = rsc.decode(data)
        return bytes(decoded)
    except ReedSolomonError as e:
        raise ValueError(
            "IamGroot decode failed: too much acoustic corruption to recover "
            "the message (Reed-Solomon could not fix the errors). Try a "
            "cleaner recording / less-compressed audio."
        ) from e
