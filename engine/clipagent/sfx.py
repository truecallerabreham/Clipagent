"""Sound design, synthesized: no sample files, so every sound is royalty-free by construction.

build_sfx_track() lays sound effects on the output timeline (Beats, Insert
transitions, chapter cards, clicks, shortcut badges). build_music() writes a
Look-matched music bed; the renderer ducks it under the voice.
"""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

SR = 48000


def _env(n, attack=0.004, release=0.12):
    t = np.arange(n) / SR
    a = np.clip(t / max(attack, 1e-4), 0, 1)
    r = np.exp(-t / max(release, 1e-4))
    return a * r


def _noise(n, seed):
    return np.random.default_rng(seed).standard_normal(n).astype(np.float32)


def _lowpass(x, alpha):
    y = np.empty_like(x)
    acc = 0.0
    for i, v in enumerate(x):  # small buffers only (< 1 s)
        acc += alpha * (v - acc)
        y[i] = acc
    return y


def synth(name: str) -> np.ndarray:
    """One sound effect as float32 mono at 48 kHz, peak ~0.9."""
    if name == "whoosh":
        n = int(0.42 * SR)
        x = _noise(n, 1)
        t = np.linspace(0, 1, n)
        sweep = _lowpass(x, 0.02) * 0.5 + _lowpass(x, 0.12) * np.sin(np.pi * t) * 0.6
        y = sweep * np.sin(np.pi * t) ** 1.5
    elif name == "swoosh":
        n = int(0.6 * SR)
        x = _noise(n, 2)
        t = np.linspace(0, 1, n)
        y = _lowpass(x, 0.05) * np.sin(np.pi * t ** 0.7) ** 2
    elif name == "pop":
        n = int(0.14 * SR)
        t = np.arange(n) / SR
        f = 900 * np.exp(-t * 28) + 280
        y = np.sin(2 * np.pi * np.cumsum(f) / SR) * _env(n, 0.002, 0.04)
    elif name == "tick":
        n = int(0.05 * SR)
        t = np.arange(n) / SR
        y = (np.sin(2 * np.pi * 2400 * t) * 0.6 + _noise(n, 3) * 0.25) * _env(n, 0.0005, 0.008)
    elif name == "ding":
        n = int(0.9 * SR)
        t = np.arange(n) / SR
        y = (np.sin(2 * np.pi * 1318.5 * t) + 0.5 * np.sin(2 * np.pi * 1975.5 * t) + 0.25 * np.sin(2 * np.pi * 2637 * t)) * _env(n, 0.002, 0.28) / 1.75
    elif name == "marker":
        n = int(0.32 * SR)
        x = _noise(n, 4)
        t = np.linspace(0, 1, n)
        band = _lowpass(x, 0.35) - _lowpass(x, 0.06)
        y = band * (0.6 + 0.4 * np.sin(2 * np.pi * 18 * t)) * np.sin(np.pi * t)
    elif name == "type":
        n = int(0.035 * SR)
        y = _noise(n, 5) * _env(n, 0.0003, 0.006)
    elif name == "alert":
        n = int(0.5 * SR)
        t = np.arange(n) / SR
        y = np.sign(np.sin(2 * np.pi * 440 * t)) * 0.3 * (np.sin(2 * np.pi * 8 * t) > 0) * _env(n, 0.005, 0.3)
    else:  # "soft" default
        n = int(0.2 * SR)
        t = np.arange(n) / SR
        y = np.sin(2 * np.pi * 660 * t) * _env(n, 0.003, 0.06)
    y = y.astype(np.float32)
    peak = float(np.abs(y).max()) or 1.0
    return y / peak * 0.9


GAIN = {"whoosh": 0.32, "swoosh": 0.3, "pop": 0.28, "tick": 0.18, "ding": 0.26, "marker": 0.2, "type": 0.12,
        "alert": 0.18, "soft": 0.22}


def build_sfx_track(cues: list[tuple[float, str]], duration: float, path: Path) -> int:
    """cues: [(output seconds, sound name)]. Writes a 48 kHz mono WAV. Returns cue count."""
    n = int((duration + 1.0) * SR)
    track = np.zeros(n, np.float32)
    cache = {}
    last = {}
    placed = 0
    for t, name in sorted(cues):
        if name in last and t - last[name] < 0.12:  # don't machine-gun the same sound
            continue
        last[name] = t
        if name not in cache:
            cache[name] = synth(name) * GAIN.get(name, 0.2)
        s = cache[name]
        i = int(max(0.0, t) * SR)
        j = min(n, i + len(s))
        if j > i:
            track[i:j] += s[: j - i]
            placed += 1
    write_wav(path, track)
    return placed


# ---------------------------------------------------------------- music

STYLES = {
    # root midi, chord degrees (semitones), bpm, timbre
    "dark-pulse": (45, [[0, 3, 7, 10], [-4, 0, 3, 7], [-2, 2, 5, 9], [-5, -1, 2, 5]], 96, "pulse"),
    "bright-pluck": (57, [[0, 4, 7, 11], [-3, 0, 4, 7], [5, 9, 12, 16], [7, 11, 14, 17]], 104, "pluck"),
    "ambient-pad": (52, [[0, 4, 7, 11], [5, 9, 12, 16], [-3, 0, 4, 7], [7, 11, 14, 18]], 72, "pad"),
}


def _midi(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def build_music(style: str, duration: float, path: Path):
    root, prog, bpm, timbre = STYLES.get(style, STYLES["ambient-pad"])
    n = int((duration + 2.0) * SR)
    out = np.zeros(n, np.float32)
    bar = 4 * 60.0 / bpm
    t_bar = int(bar * SR)
    tt = np.arange(t_bar) / SR
    k = 0
    while k * t_bar < n:
        chord = prog[k % len(prog)]
        seg = np.zeros(t_bar, np.float32)
        for d in chord:
            f = _midi(root + 12 + d)
            if timbre == "pad":
                seg += (np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(2 * np.pi * f * 2.003 * tt)) * 0.12
            elif timbre == "pulse":
                gate = (np.sin(2 * np.pi * (bpm / 60.0) * 2 * tt) > -0.2).astype(np.float32)
                seg += np.sin(2 * np.pi * f * tt) * 0.09 * (0.55 + 0.45 * gate)
            else:  # pluck: arpeggiated eighths
                step = int(SR * 60.0 / bpm / 2)
                for i in range(0, t_bar, step):
                    if (i // step) % len(chord) == chord.index(d):
                        m = min(step * 2, t_bar - i)
                        e = np.exp(-np.arange(m) / SR * 7)
                        seg[i:i + m] += np.sin(2 * np.pi * f * np.arange(m) / SR) * e * 0.22
        bass = np.sin(2 * np.pi * _midi(root + chord[0]) * tt) * 0.16
        seg += bass
        fade = np.minimum(1, np.minimum(tt / 0.25, (bar - tt) / 0.25)).astype(np.float32)
        a = k * t_bar
        b = min(n, a + t_bar)
        out[a:b] += (seg * fade)[: b - a]
        k += 1
    # gentle master: soft-clip, fade in/out
    out = np.tanh(out * 1.4) * 0.5
    fade_in = np.minimum(1, np.arange(n) / (2.0 * SR))
    fade_out = np.minimum(1, (n - np.arange(n)) / (3.0 * SR))
    write_wav(path, (out * fade_in * fade_out).astype(np.float32))


def write_wav(path: Path, data: np.ndarray):
    pcm = (np.clip(data, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def collect_cues(edl: dict, tl, look: dict, manifest: dict, specs: dict) -> list[tuple[float, str]]:
    """Every sound cue in output time."""
    m = look.get("sfx", {})
    cues = []
    for ins in manifest.get("inserts", []):
        if ins["status"] not in ("rendered", "cached"):
            continue
        tr = m.get("transition", "whoosh")
        if ins["mode"] == "full":
            cues.append((ins["out_start"] - 0.12, tr))
            cues.append((ins["out_end"] - 0.3, tr))
        else:
            cues.append((ins["out_start"], m.get("overlay", "pop")))
        for b in (specs.get(ins["id"]) or {}).get("beats", []):
            name = m.get(b.get("action", ""))
            if name:
                cues.append((ins["out_start"] + b["at"], name))
    for c in edl.get("chapters", []):
        cues.append((tl.to_out(c["at"]), m.get("chapter", "swoosh")))
    for c in edl.get("clicks", []):
        if any(a <= c["t"] <= b for a, b, _ in tl.segments):
            cues.append((tl.to_out(c["t"]), m.get("click", "tick")))
    for s in edl.get("shortcuts", []):
        cues.append((tl.to_out(s["at"]), m.get("shortcut", "tick")))
    return cues
