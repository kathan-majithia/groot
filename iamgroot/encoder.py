"""
encoder.py
==========
Public entry point: encode(text, output_path, password=None).

Pipeline:
  text -> [optional: AES-GCM encrypt with password] -> utf8/cipher bytes ->
  Reed-Solomon(payload) -> header (len + ecc + encrypted flag) ->
  Reed-Solomon(header) -> bit sequence -> per-symbol acoustic targets ->
  WORLD-vocoder synthesis of a single, duration-flexed "I am Groot" -> wav

Everything the decoder needs (payload length, ECC amount, whether it's
encrypted) is written INSIDE the header symbols at the start of the audio.
No external key or database -- except the PASSWORD itself, which (by
design) is never stored anywhere and must be supplied again to decode.
"""
import struct
from typing import List, Optional

import soundfile as sf

from . import config, ecc, crypto
from .bitstream import bytes_to_bits, chunk
from .acoustic import bits_to_symbol_levels, levels_to_targets, SymbolTarget
from . import vocoder


def _build_bit_sequence(text: str, password: Optional[str]):
    raw_bytes = text.encode("utf-8")
    encrypted_flag = 0
    if password:
        raw_bytes = crypto.encrypt(raw_bytes, password)
        encrypted_flag = 1

    ecc_len = ecc.compute_ecc_len(len(raw_bytes))
    rs_payload = ecc.rs_encode(raw_bytes, ecc_len)

    if len(rs_payload) > 0xFFFF:
        raise ValueError("Message too long for this scheme (RS block > 65535 bytes).")

    header_data = struct.pack(">HBB", len(rs_payload), ecc_len, encrypted_flag)
    header_rs = ecc.rs_encode(header_data, config.HEADER_ECC_BYTES)

    header_bits = bytes_to_bits(header_rs)
    payload_bits = bytes_to_bits(rs_payload)

    # pad header bits to fill exactly HEADER_SYMBOLS * BITS_PER_SYMBOL
    header_slots = config.HEADER_SYMBOLS * config.BITS_PER_SYMBOL
    header_bits = header_bits + [0] * (header_slots - len(header_bits))

    all_bits = header_bits + payload_bits
    # pad payload tail to a whole number of symbols
    total_slots = config.BITS_PER_SYMBOL * (
        -(-len(all_bits) // config.BITS_PER_SYMBOL)  # ceil div
    )
    all_bits = all_bits + [0] * (total_slots - len(all_bits))
    return all_bits


def _bits_to_targets(all_bits: List[int]) -> List[SymbolTarget]:
    targets = []
    for bits_n in chunk(all_bits, config.BITS_PER_SYMBOL):
        levels = bits_to_symbol_levels(bits_n)
        targets.append(levels_to_targets(levels))
    return targets


def encode(text: str, output_path: str, password: Optional[str] = None) -> None:
    """
    text: the message to hide.
    output_path: where to write the wav.
    password: optional. If given, the message is AES-256-GCM encrypted
        with a key derived from this password BEFORE steganographic
        embedding. The same password must be given to decode() -- a wrong
        password makes decode() fail outright (no plaintext is produced).
    """
    if not isinstance(text, str) or len(text) == 0:
        raise ValueError("text must be a non-empty string")

    all_bits = _build_bit_sequence(text, password)
    targets = _bits_to_targets(all_bits)

    seed = vocoder.synthesize_seed()
    audio = vocoder.synthesize_from_symbols(seed, targets)

    sf.write(output_path, audio, config.SAMPLE_RATE)
