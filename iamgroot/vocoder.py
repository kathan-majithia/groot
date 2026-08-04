"""
vocoder.py
==========
Generates the seed "I am Groot" utterance and resynthesizes it -- stretched
to whatever duration is needed -- with per-symbol pitch (F0) and loudness
targets baked in, using the WORLD vocoder (pyworld). This is where the
message actually gets turned into sound.
"""
import math
import subprocess
import tempfile
import os
from typing import List

import numpy as np
import pyworld as pw
import librosa
import soundfile as sf

from . import config
from .acoustic import SymbolTarget


def _find_espeak_ng() -> str:
    """Locate the espeak-ng executable. Checks PATH first, then falls back
    to common install locations (mainly for Windows, where the installer
    often doesn't add itself to PATH)."""
    import shutil

    found = shutil.which("espeak-ng") or shutil.which("espeak-ng.exe")
    if found:
        return found

    candidates = [
        r"C:\Program Files\eSpeak NG\espeak-ng.exe",
        r"C:\Program Files (x86)\eSpeak NG\espeak-ng.exe",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c

    raise FileNotFoundError(
        "Could not find 'espeak-ng'. Install it:\n"
        "  Windows: https://github.com/espeak-ng/espeak-ng/releases "
        "(then add its install folder to PATH, or leave it at the default "
        "'C:\\Program Files\\eSpeak NG\\')\n"
        "  Debian/Ubuntu: sudo apt install espeak-ng\n"
        "  macOS: brew install espeak-ng"
    )


def synthesize_seed() -> np.ndarray:
    """Use espeak-ng to say 'I am Groot' once, return mono float64 audio at
    config.SAMPLE_RATE."""
    espeak_path = _find_espeak_ng()
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        subprocess.run(
            [espeak_path, "-v", config.ESPEAK_VOICE, "-s", str(config.ESPEAK_SPEED_WPM),
             "-w", tmp_path, "I am Groot"],
            check=True, capture_output=True,
        )
        x, sr = sf.read(tmp_path)
        if x.ndim > 1:
            x = x.mean(axis=1)
        if sr != config.SAMPLE_RATE:
            x = librosa.resample(x.astype(np.float64), orig_sr=sr, target_sr=config.SAMPLE_RATE)
        return x.astype(np.float64)
    finally:
        os.unlink(tmp_path)


def _world_analyze(x: np.ndarray):
    f0, sp, ap = pw.wav2world(x, config.SAMPLE_RATE, frame_period=config.PYWORLD_FRAME_PERIOD_MS)
    return f0, sp, ap


def _trim_to_active_region(f0: np.ndarray, sp: np.ndarray, ap: np.ndarray):
    """espeak-ng (and most TTS engines) pad the wav with leading/trailing
    near-silence. If that dead air gets stretched into data-carrying
    symbols, their spectral envelope is near-zero and our per-symbol
    loudness normalization then blows up whatever tiny noise is left --
    corrupting pitch/timbre measurement. So: find the frames that actually
    have voiced/spoken energy and only use those as the stretch source."""
    frame_energy = np.sqrt(np.mean(sp, axis=1))
    threshold = max(frame_energy.max() * 0.05, 1e-6)
    active = np.where(frame_energy > threshold)[0]
    if len(active) < 4:
        return f0, sp, ap  # fallback: don't trim if detection fails
    lo, hi = active[0], active[-1] + 1
    return f0[lo:hi], sp[lo:hi], ap[lo:hi]


def _stretch_frames(arr: np.ndarray, n_out: int) -> np.ndarray:
    """Nearest-neighbour resample along the frame (time) axis so the
    phonetic shape of 'I am Groot' spans exactly n_out frames, however long
    or short that needs to be. This is what lets total duration flex with
    message length without repeating the phrase."""
    n_in = arr.shape[0]
    idx = np.floor(np.linspace(0, n_in - 1, n_out)).astype(int)
    idx = np.clip(idx, 0, n_in - 1)
    return arr[idx]


def synthesize_from_symbols(seed: np.ndarray, symbol_targets: List[SymbolTarget]) -> np.ndarray:
    """Build the final 'I am Groot' waveform encoding one SymbolTarget per
    audio symbol, using the seed utterance as the phonetic template.

    Each symbol's pitch/loudness target is held constant across most of the
    symbol's duration (this is what the decoder reads reliably), with only
    a SHORT transition smoothed at each boundary -- softening the robotic
    "staircase" without touching the interior region the decoder measures.
    """
    f0_seed, sp_seed, ap_seed = _world_analyze(seed)
    f0_seed, sp_seed, ap_seed = _trim_to_active_region(f0_seed, sp_seed, ap_seed)

    n_symbols = len(symbol_targets)
    n_frames = n_symbols * config.FRAMES_PER_SYMBOL

    sp = _stretch_frames(sp_seed, n_frames).copy()
    ap = _stretch_frames(ap_seed, n_frames).copy()
    f0 = np.zeros(n_frames, dtype=np.float64)

    for s, target in enumerate(symbol_targets):
        lo = s * config.FRAMES_PER_SYMBOL
        hi = lo + config.FRAMES_PER_SYMBOL
        f0[lo:hi] = target.f0_hz  # constant pitch within symbol (voiced)

    # Light smoothing: a small moving-average kernel only blurs frames right
    # at symbol boundaries (interior frames are already constant, so the
    # smoothing has no effect there) -- softens clicks/steps without
    # touching the flat region the decoder reads from.
    kernel_frames = max(1, int(round(config.FRAMES_PER_SYMBOL * config.SMOOTHING_KERNEL_FRAC)))
    if kernel_frames > 1:
        kernel = np.ones(kernel_frames) / kernel_frames
        pad = kernel_frames // 2
        f0_padded = np.pad(f0, (pad, pad), mode="edge")
        f0 = np.convolve(f0_padded, kernel, mode="valid")[:n_frames]

    sr = config.SAMPLE_RATE
    y = pw.synthesize(f0, sp, ap, sr, frame_period=config.PYWORLD_FRAME_PERIOD_MS)

    # --- per-symbol loudness normalization directly on the waveform ---
    samples_per_symbol = int(round(config.SYMBOL_MS / 1000.0 * sr))
    y_out = np.zeros(n_symbols * samples_per_symbol, dtype=np.float64)
    for s, target in enumerate(symbol_targets):
        lo = s * samples_per_symbol
        hi = lo + samples_per_symbol
        seg = y[lo:hi] if hi <= len(y) else np.pad(y[lo:], (0, hi - len(y)))
        rms = np.sqrt(np.mean(seg ** 2)) + 1e-9
        target_rms = 10 ** (target.energy_db / 20.0)
        gain = target_rms / rms
        y_out[lo:hi] = seg * gain

    # gentle fades at symbol boundaries to avoid clicking, without touching
    # the acoustic measurement point (fades applied only at extreme edges).
    # NOTE: keep this SMALL -- unlike the pitch kernel above (which only
    # blurs a couple of frames, leaving the interior flat), this fade
    # directly scales waveform AMPLITUDE, and the decoder measures RMS over
    # the FULL segment. A wide fade corrupts a large fraction of that
    # measurement and was empirically found to break decoding outright.
    fade = min(96, samples_per_symbol // 6)
    if fade > 0:
        ramp = np.linspace(0, 1, fade)
        for s in range(1, n_symbols):
            b = s * samples_per_symbol
            y_out[b:b + fade] *= ramp
            y_out[b - fade:b] *= ramp[::-1]

    # Safety-only hard clamp (NOT a global rescale): with ENERGY_MAX_DB given
    # enough headroom below 0 dBFS this should essentially never trigger. A
    # global rescale here would be wrong -- it would shift every symbol's
    # absolute loudness by a message-dependent amount, breaking the decoder's
    # ability to read absolute dB levels with no side information.
    y_out = np.clip(y_out, -0.98, 0.98)

    return y_out


def samples_per_symbol() -> int:
    return int(round(config.SYMBOL_MS / 1000.0 * config.SAMPLE_RATE))
