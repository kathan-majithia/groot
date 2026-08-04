"""
acoustic.py
===========
The core, novel part of IamGroot: converting between raw bits and absolute,
self-describing acoustic feature values -- and back. This module is used
IDENTICALLY by both encoder and decoder, so it must be perfectly
deterministic and symmetric (same math both directions).

Each "symbol" (one short slice of the "I am Groot" utterance, SYMBOL_MS long)
carries BITS_PER_SYMBOL bits across two independent, ABSOLUTE-valued
acoustic channels:

    bits:   [ F0_BITS bits ][ ENERGY_BITS bits ]
    channel:      pitch            loudness

"Absolute" is the key design choice that makes this scheme need NO key and
NO database: every channel is quantized against a fixed, public numeric
range (e.g. F0 always mapped into 100-320 Hz), so the decoder can read a
value out of the raw audio and know immediately which bit-pattern it
represents, without any reference to the original un-encoded audio.

A third channel (spectral centroid / timbre, controlled by warping the
WORLD spectral envelope) was prototyped and measured empirically -- it was
dropped because it landed in the wrong quantization bin over 40% of the
time and also degraded the pitch channel's accuracy by distorting the
harmonic structure. Two reliable channels beat three unreliable ones.
"""
from dataclasses import dataclass
from typing import List
import numpy as np

from . import config


def _quantize(value: float, vmin: float, vmax: float, n_levels: int, log: bool = False) -> int:
    """Map a continuous value into one of n_levels discrete bins (0..n_levels-1)."""
    if log:
        value = np.log(max(value, 1e-6))
        vmin_, vmax_ = np.log(vmin), np.log(vmax)
    else:
        vmin_, vmax_ = vmin, vmax
    value = min(max(value, vmin_), vmax_)
    frac = (value - vmin_) / (vmax_ - vmin_)
    level = int(round(frac * (n_levels - 1)))
    return min(max(level, 0), n_levels - 1)


def _dequantize(level: int, vmin: float, vmax: float, n_levels: int, log: bool = False) -> float:
    """Map a discrete bin index back to the CENTER value of that bin (used as
    the synthesis target, since the center is maximally robust to drift)."""
    if log:
        vmin_, vmax_ = np.log(vmin), np.log(vmax)
    else:
        vmin_, vmax_ = vmin, vmax
    frac = level / (n_levels - 1) if n_levels > 1 else 0.0
    value = vmin_ + frac * (vmax_ - vmin_)
    return float(np.exp(value)) if log else float(value)


@dataclass
class SymbolTarget:
    """The target acoustic values for one symbol, derived from bits."""
    f0_hz: float
    energy_db: float


@dataclass
class SymbolLevels:
    """The raw quantization levels for one symbol (0..n_levels-1 each)."""
    f0_level: int
    energy_level: int


def _bin_to_gray(n: int) -> int:
    return n ^ (n >> 1)


def _gray_to_bin(g: int) -> int:
    n = g
    shift = 1
    while (g >> shift):
        n ^= (g >> shift)
        shift += 1
    return n


def _level_to_code(level: int) -> int:
    return _bin_to_gray(level) if config.USE_GRAY_CODE else level


def _code_to_level(code: int) -> int:
    return _gray_to_bin(code) if config.USE_GRAY_CODE else code


def bits_to_symbol_levels(bits_n: List[int]) -> SymbolLevels:
    assert len(bits_n) == config.BITS_PER_SYMBOL
    f0_bits = bits_n[0:config.F0_BITS]
    en_bits = bits_n[config.F0_BITS:config.F0_BITS + config.ENERGY_BITS]
    from .bitstream import bits_to_int
    return SymbolLevels(
        f0_level=_code_to_level(bits_to_int(f0_bits)),
        energy_level=_code_to_level(bits_to_int(en_bits)),
    )


def symbol_levels_to_bits(levels: SymbolLevels) -> List[int]:
    from .bitstream import int_to_bits
    return (
        int_to_bits(_level_to_code(levels.f0_level), config.F0_BITS)
        + int_to_bits(_level_to_code(levels.energy_level), config.ENERGY_BITS)
    )


def levels_to_targets(levels: SymbolLevels) -> SymbolTarget:
    return SymbolTarget(
        f0_hz=_dequantize(levels.f0_level, config.F0_MIN_HZ, config.F0_MAX_HZ,
                           config.F0_LEVELS, log=True),
        energy_db=_dequantize(levels.energy_level, config.ENERGY_MIN_DB, config.ENERGY_MAX_DB,
                               config.ENERGY_LEVELS, log=False),
    )


def measure_segment(x: np.ndarray, sr: int) -> SymbolTarget:
    """Measure the acoustic features of a raw audio segment. Used by the
    DECODER (and by the encoder for self-verification)."""
    x = x.astype(np.float64)
    if len(x) < 32:
        return SymbolTarget(f0_hz=config.F0_MIN_HZ, energy_db=config.ENERGY_MIN_DB)

    # --- loudness: RMS in dBFS ---
    rms = float(np.sqrt(np.mean(x ** 2)) + 1e-9)
    energy_db = 20.0 * np.log10(rms)

    # --- pitch: YIN pitch tracker, bounded to our known synthesis range ---
    f0 = _estimate_f0_yin(x, sr)

    return SymbolTarget(f0_hz=f0, energy_db=energy_db)


def _estimate_f0_yin(x: np.ndarray, sr: int) -> float:
    import librosa

    x = x - np.mean(x)
    if np.max(np.abs(x)) < 1e-6:
        return config.F0_MIN_HZ
    frame_length = min(2048, max(64, len(x) - (len(x) % 2)))
    try:
        f0_track = librosa.yin(
            x.astype(np.float32),
            fmin=config.F0_MIN_HZ * 0.8,
            fmax=config.F0_MAX_HZ * 1.2,
            sr=sr,
            frame_length=frame_length,
        )
        f0_track = f0_track[np.isfinite(f0_track) & (f0_track > 0)]
        if len(f0_track) == 0:
            return config.F0_MIN_HZ
        return float(np.median(f0_track))
    except Exception:
        return config.F0_MIN_HZ


def target_to_levels(target: SymbolTarget) -> SymbolLevels:
    """Quantize a MEASURED target back into discrete levels (decoder side)."""
    return SymbolLevels(
        f0_level=_quantize(target.f0_hz, config.F0_MIN_HZ, config.F0_MAX_HZ,
                            config.F0_LEVELS, log=True),
        energy_level=_quantize(target.energy_db, config.ENERGY_MIN_DB, config.ENERGY_MAX_DB,
                                config.ENERGY_LEVELS, log=False),
    )
