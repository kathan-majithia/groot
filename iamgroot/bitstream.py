"""
bitstream.py
============
Tiny helpers to turn bytes into a flat list of bits (MSB-first) and back.
Used to slice a byte-string into fixed-width chunks that get mapped onto
acoustic "symbols" in acoustic.py.
"""
from typing import List


def bytes_to_bits(data: bytes) -> List[int]:
    bits = []
    for byte in data:
        for i in range(7, -1, -1):
            bits.append((byte >> i) & 1)
    return bits


def bits_to_bytes(bits: List[int]) -> bytes:
    # pad on the right with zeros to a multiple of 8 if needed
    pad = (-len(bits)) % 8
    bits = list(bits) + [0] * pad
    out = bytearray()
    for i in range(0, len(bits), 8):
        byte = 0
        for b in bits[i:i + 8]:
            byte = (byte << 1) | b
        out.append(byte)
    return bytes(out)


def bits_to_int(bits: List[int]) -> int:
    value = 0
    for b in bits:
        value = (value << 1) | b
    return value


def int_to_bits(value: int, n_bits: int) -> List[int]:
    return [(value >> i) & 1 for i in range(n_bits - 1, -1, -1)]


def chunk(bits: List[int], size: int) -> List[List[int]]:
    return [bits[i:i + size] for i in range(0, len(bits), size)]
