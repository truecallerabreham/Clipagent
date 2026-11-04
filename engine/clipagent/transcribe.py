"""Transcribe a recording with word timestamps.

Writes <workdir>/transcript.json (segments + words, source seconds) and
<workdir>/transcript.txt (one line per segment, `[mm:ss.s-mm:ss.s] text`)
which is the file Claude reads to plan the edit. Words Whisper was unsure of
are marked `[[word?]]` in the .txt so they get checked for caption fixes.

Two ways in:
  - `main` transcribes a finished file in one go (imports, `prepare --retranscribe`).
  - `live` follows the recorder's growing mic.webm while the user is still talking
    and transcribes each finished stretch (cut at a pause), so when they stop only
    the last few seconds are left. `clipagent wait` runs it.

usage: uv run transcribe.py INPUT WORKDIR [--model large-v3-turbo] [--language en]
                            [--vocab "LangGraph, FastAPI, Abreham"]
"""
import argparse
import os
import subprocess
import sys
import time
import wave
from pathlib import Path

import numpy as np

from .common import FFMPEG, run, save_json

# Whisper copies the style and spelling of the prompt: fillers written out so
# they become cuttable words, and the tech vocabulary this channel uses so
# accented pronunciations land on the right spelling.
BASE_VOCAB = ("Claude, Claude Code, Anthropic, MCP, API, LLM, agent, subagent, prompt, repo, GitHub, "
              "Python, TypeScript, JSON, npm, uv, CLI, terminal, Docker, OAuth, JWT, CVE, XSS, SQL injection")
FILLER_PROMPT = "Umm, so, uh, let me, like, you know, I mean, we're gonna build this. Hmm, okay."
FILLERS = {"um", "umm", "uh", "uhh", "hmm", "mm", "erm", "ah", "eh"}
LOW_CONF = 0.45
SR = 16000
# transcribe a denoised copy: Whisper mishears less without the earphone hiss
# (speechnorm levels the voice like loudnorm did, ~5x cheaper: 3 s vs 15 s per 5 min)
SPEECH_AF = "highpass=f=90,afftdn=nr=12:nf=-40:tn=1,speechnorm=e=6:r=0.0005:l=1"


def fmt(t):
    return f"{int(t // 60):02d}:{t % 60:04.1f}"


def load_model(name, threads=None):
    from faster_whisper import WhisperModel
    return WhisperModel(name, device="cpu", compute_type="int8", cpu_threads=threads or os.cpu_count() or 4)


def transcribe_chunk(model, audio, offset, vocab, language="en"):
    """Transcribe float32 16 kHz samples; times are shifted by `offset` seconds.
    -> (segments [{s, e, text, words: [{w, s, e, p, filler?}]}], detected language)"""
    segments, info = model.transcribe(
        audio,
        language=None if language == "auto" else language,
        word_timestamps=True,
        initial_prompt=f"{FILLER_PROMPT} Terms: {vocab}.",
        hotwords=vocab,
        beam_size=5,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 400},
        condition_on_previous_text=False,
    )
    out = []
    for s in segments:
        words = [{"w": w.word.strip(), "s": round(w.start + offset, 3), "e": round(w.end + offset, 3), "p": round(w.probability, 2),
                  **({"filler": True} if w.word.strip(" ,.!?").lower() in FILLERS else {})}
                 for w in (s.words or [])]
        out.append({"s": round(s.start + offset, 3), "e": round(s.end + offset, 3), "text": s.text.strip(), "words": words})
    return out, info.language


def write_outputs(work, segments, language, duration, model_name, quiet=False):
    """Number the words (w0, w1, ...) and write transcript.json / .txt / words.txt."""
    work = Path(work)
    lines, unsure, idx = [], 0, 0
    for s in segments:
        for w in s["words"]:
            w.pop("id", None)
        s["words"] = [{"id": f"w{idx + k}", **w} for k, w in enumerate(s["words"])]
        idx += len(s["words"])
        words = s["words"]
        shown = " ".join(f"[[{w['w']}?]]" if w["p"] < LOW_CONF and not w.get("filler") else w["w"] for w in words)
        unsure += sum(1 for w in words if w["p"] < LOW_CONF and not w.get("filler"))
        lines.append(f"[{fmt(s['s'])}-{fmt(s['e'])}] {shown or s['text']}")
        if not quiet:
            print(lines[-1], flush=True)
    save_json({"language": language, "duration": duration, "model": model_name, "segments": segments},
              work / "transcript.json")
    (work / "transcript.txt").write_text("\n".join(lines) + "\n")
    write_word_index(segments, work / "words.txt")
    print(f"\nwrote {work/'transcript.json'} and {work/'transcript.txt'} ({len(segments)} segments, "
          f"{unsure} low-confidence words marked [[word?]])")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("workdir")
    ap.add_argument("--model", default=os.environ.get("WHISPER_MODEL", "large-v3-turbo"),
                    help="large-v3-turbo (best for accents, default), small.en (fast draft)")
    ap.add_argument("--language", default="en")
    ap.add_argument("--vocab", default="", help="extra names/terms the speaker uses, comma separated")
    args = ap.parse_args(argv)

    work = Path(args.workdir)
    work.mkdir(parents=True, exist_ok=True)
    wav = work / "speech16k.wav"
    run([FFMPEG, "-y", "-i", args.input, "-vn", "-ac", "1", "-ar", str(SR), "-af", SPEECH_AF, str(wav)])

    vocab = BASE_VOCAB + (", " + args.vocab if args.vocab else "")
    print(f"loading {args.model} (first run downloads it)...", flush=True)
    model = load_model(args.model)
    # hand Whisper the samples directly; its own file decoder breaks across PyAV versions
    with wave.open(str(wav)) as f:
        audio = np.frombuffer(f.readframes(f.getnframes()), np.int16).astype(np.float32) / 32768
    segs, lang = transcribe_chunk(model, audio, 0.0, vocab, args.language)
    write_outputs(work, segs, lang, len(audio) / SR, args.model)
    wav.unlink(missing_ok=True)


# ---------------------------------------------------------------- live (while recording)

def _decode_from(path, start):
    """16 kHz mono float32 samples of a (possibly still growing) WebM from `start` s.
    A half-written last cluster just ends the stream early, which is fine."""
    p = subprocess.run([FFMPEG, "-v", "quiet", "-ss", f"{start:.3f}", "-i", str(path), "-vn", "-ac", "1", "-ar", str(SR),
                        "-f", "s16le", "-"], capture_output=True)
    return np.frombuffer(p.stdout, np.int16).astype(np.float32) / 32768


def _filtered(audio):
    """The same denoise/level chain the one-shot path applies, on raw samples."""
    if not len(audio):
        return audio
    p = subprocess.run([FFMPEG, "-v", "quiet", "-f", "s16le", "-ar", str(SR), "-ac", "1", "-i", "-", "-af", SPEECH_AF,
                        "-ar", str(SR), "-f", "s16le", "-"], input=(np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes(),
                       capture_output=True)
    out = np.frombuffer(p.stdout, np.int16).astype(np.float32) / 32768
    return out if len(out) else audio


def quiet_cut(audio, lo, hi, win=0.4):
    """Seconds into `audio` at the centre of its quietest `win`-second stretch between lo and hi:
    cutting there never splits a word."""
    hop = int(0.02 * SR)
    a, b = int(lo * SR), int(hi * SR)
    seg = audio[a:b]
    n = len(seg) // hop
    if n < 3:
        return None
    rms = np.sqrt((seg[: n * hop].reshape(n, hop) ** 2).mean(axis=1) + 1e-12)
    k = max(1, int(win / 0.02))
    if n <= k:
        return None
    run_ = np.convolve(rms, np.ones(k) / k, mode="valid")
    i = int(np.argmin(run_))
    return lo + (i + k / 2) * 0.02


def live(mic, is_done, vocab="", model_name="large-v3-turbo", language="en",
         min_chunk=25.0, max_chunk=60.0, poll=3.0, log=print):
    """Transcribe `mic` (growing WebM) chunk by chunk until is_done() and the file is drained.
    Times are mic-file seconds. -> (segments, language, seconds transcribed)"""
    try:
        os.nice(10)  # the recorder and the user's apps come first
    except (AttributeError, OSError):
        pass
    vocab = BASE_VOCAB + (", " + vocab if vocab else "")
    ncpu = os.cpu_count() or 4
    model = load_model(model_name, threads=max(2, ncpu // 2))
    log(f"live transcription: {model_name} loaded, following {Path(mic).name}")
    done_t, segs, lang = 0.0, [], language
    while True:
        finished = is_done()
        raw = _decode_from(mic, done_t) if Path(mic).exists() else np.zeros(0, np.float32)
        avail = len(raw) / SR
        if finished:
            if avail - 0.05 > 0:
                if avail > 30:  # long backlog after stop: use every core for the rest
                    model = load_model(model_name)
                chunk, cut = raw, avail
            else:
                break
        else:
            if avail < min_chunk + 2.0:
                time.sleep(poll)
                continue
            # cut in a pause near the end of what is on disk, keeping the last 1.5 s
            # (the next cluster may still be half written)
            cut = quiet_cut(raw, max(min_chunk * 0.6, avail - 12.0), avail - 1.5)
            if cut is None:
                time.sleep(poll)
                continue
            cut = min(cut, max_chunk + 12.0)
            chunk = raw[: int(cut * SR)]
        t0 = time.time()
        new, lang = transcribe_chunk(model, _filtered(chunk), done_t, vocab, language)
        segs += new
        log(f"live transcription: {done_t:6.1f}-{done_t + cut:6.1f}s in {time.time() - t0:4.1f}s")
        done_t += cut
        if finished:
            break
    return segs, lang, done_t


def shift(segments, dt):
    """Move every time by dt seconds (mic clock -> Take clock)."""
    if abs(dt) < 1e-4:
        return segments
    for s in segments:
        s["s"], s["e"] = round(s["s"] + dt, 3), round(s["e"] + dt, 3)
        for w in s["words"]:
            w["s"], w["e"] = round(w["s"] + dt, 3), round(w["e"] + dt, 3)
    return segments


def write_word_index(segments, path):
    """words.txt: the transcript with a word id before every word, so Beats can be
    anchored to exact words: `[01:12.4] w310:the w311:gateway w312:checks`."""
    lines = [f"[{fmt(s['s'])}] " + " ".join(f"{w['id']}:{w['w']}" for w in s["words"]) for s in segments]
    Path(path).write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
