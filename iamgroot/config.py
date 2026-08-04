"""
config.py
=========
All tunable constants for the IamGroot steganographic codec live here.
Both the encoder and the decoder import this SAME file, so as long as you
don't change these values between encoding a message and decoding it, the
scheme stays self-consistent. Nothing here is a "secret key" -- these are
public, fixed algorithm parameters (like knowing MP3 uses 44.1kHz frames --
it's not a secret, it's just part of the format spec).

If you want to trade CAPACITY vs ROBUSTNESS, this is the file to tune:
  - Fewer levels per channel  -> fewer bits/symbol -> longer audio needed,
    but much more resistant to noise/compression/re-recording.
  - More levels per channel   -> more bits/symbol -> shorter audio for the
    same message, but more fragile to real-world audio degradation.
"""

# ---------------------------------------------------------------------------
# Audio format
# ---------------------------------------------------------------------------
SAMPLE_RATE = 22050          # Hz. All wav I/O is resampled to this.
ESPEAK_VOICE = "en"
ESPEAK_SPEED_WPM = 175       # base speaking rate for the seed "I am Groot"

# ---------------------------------------------------------------------------
# WORLD vocoder analysis frame (used internally during synthesis only)
# ---------------------------------------------------------------------------
PYWORLD_FRAME_PERIOD_MS = 5.0

# ---------------------------------------------------------------------------
# "Symbol" = one data-carrying slot of audio. We group several WORLD frames
# into one symbol so it survives compression better (bigger, coarser chunks
# of audio are more robust than tiny 5ms slivers).
# ---------------------------------------------------------------------------
SYMBOL_MS = 90.0
FRAMES_PER_SYMBOL = int(round(SYMBOL_MS / PYWORLD_FRAME_PERIOD_MS))  # = 18

# How much of each symbol's boundary gets smoothed into its neighbor
# (as a fraction of FRAMES_PER_SYMBOL). Empirically swept 0.12 - 0.65:
# bit-error-rate stayed flat (~5-7%) up to ~0.5, only degrading noticeably
# past ~0.65. Set below that danger zone with margin.
SMOOTHING_KERNEL_FRAC = 0.25

# ---------------------------------------------------------------------------
# Per-symbol acoustic channels. Each channel is an ABSOLUTE quantized value
# (not relative to anything), so the decoder can read it with zero side
# information -- everything needed is baked into the audio itself.
#
# NOTE on design history: an earlier draft used three channels (pitch,
# loudness, AND spectral-centroid/timbre). Empirical testing (see project
# notes) showed the timbre channel, implemented via frequency-axis warping
# of the WORLD spectral envelope, landed in the wrong quantization bin over
# 40% of the time -- it interacts too unpredictably with pitch and with the
# phonetic content being stretched. Rather than ship an unreliable channel,
# it was dropped. Pitch and loudness alone measured far more reliably.
# ---------------------------------------------------------------------------
# Channel A: pitch (F0), log-spaced across a natural human vocal range.
F0_BITS = 3
F0_LEVELS = 2 ** F0_BITS          # 8
F0_MIN_HZ = 100.0
F0_MAX_HZ = 320.0

# Channel B: loudness (RMS energy in dBFS of the symbol's audio segment).
ENERGY_BITS = 3
ENERGY_LEVELS = 2 ** ENERGY_BITS  # 8
# NOTE: the WORLD-synthesized voiced signal has a crest factor (peak/rms)
# of roughly 15 dB, so ENERGY_MAX_DB must leave enough headroom below 0 dBFS
# peak or the final peak-normalization step will rescale the WHOLE clip and
# silently shift every symbol's absolute loudness (breaking decodability).
ENERGY_MIN_DB = -38.0
ENERGY_MAX_DB = -18.0

BITS_PER_SYMBOL = F0_BITS + ENERGY_BITS  # 6 bits/symbol

# Levels are Gray-coded before being turned into bits, so that a real-world
# off-by-one quantization error (the dominant error mode measured) flips
# exactly ONE bit instead of potentially several -- this makes each acoustic
# mistake cost Reed-Solomon much less "damage" to repair.
USE_GRAY_CODE = True

# ---------------------------------------------------------------------------
# Self-contained header: tells the decoder how many payload bytes (after
# error-correction coding) follow, plus how much ECC redundancy was used.
# Protected by its OWN small Reed-Solomon block so it survives noise too.
# ---------------------------------------------------------------------------
import math

HEADER_DATA_BYTES = 4     # uint16 rs_total_len + uint8 ecc_len + uint8 encrypted_flag
HEADER_ECC_BYTES = 6      # RS parity bytes protecting the header itself
HEADER_TOTAL_BYTES = HEADER_DATA_BYTES + HEADER_ECC_BYTES
HEADER_SYMBOLS = math.ceil((HEADER_TOTAL_BYTES * 8) / BITS_PER_SYMBOL)

# ---------------------------------------------------------------------------
# Payload Reed-Solomon: redundancy as a fraction of message bytes.
# reedsolo works over GF(256): data + ecc must be <= 255 bytes per block.
# ---------------------------------------------------------------------------
PAYLOAD_ECC_RATIO = 1.6   # ~160% extra parity bytes -- measured acoustic bit
                            # error rate is ~5-7% on continuous multi-symbol
                            # audio (slightly higher with wider boundary
                            # smoothing enabled for naturalness). Re-validated
                            # empirically at 100/100 and 60/60 stress-test
                            # pass rate across two random seeds.
MIN_ECC_BYTES = 14
MAX_RS_BLOCK = 255         # hard ceiling imposed by reedsolo / GF(256)
