"""Transcribe a recording with word timestamps.

Writes <workdir>/transcript.json (segments + words, source seconds) and
<workdir>/transcript.txt (one line per segment, `[mm:ss.s-mm:ss.s] text`)
which is the file Claude reads to plan the edit. Words Whisper was unsure of
are marked `[[word?]]` in the .txt so they get checked for caption fixes.

usage: uv run transcribe.py INPUT WORKDIR [--model large-v3-turbo] [--language en]
                            [--vocab "LangGraph, FastAPI, Abreham"]
"""
import argparse
import os
import sys
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


def fmt(t):
    return f"{int(t // 60):02d}:{t % 60:04.1f}"


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
    # transcribe a denoised copy: Whisper mishears less without the earphone hiss
    run([FFMPEG, "-y", "-i", args.input, "-vn", "-ac", "1", "-ar", "16000",
         "-af", "highpass=f=90,afftdn=nr=12:nf=-40:tn=1,loudnorm=I=-18", str(wav)])

    from faster_whisper import WhisperModel

    vocab = BASE_VOCAB + (", " + args.vocab if args.vocab else "")
    print(f"loading {args.model} (first run downloads it)...", flush=True)
    model = WhisperModel(args.model, device="cpu", compute_type="int8", cpu_threads=os.cpu_count() or 4)
    # hand Whisper the samples directly; its own file decoder breaks across PyAV versions
    with wave.open(str(wav)) as f:
        audio = np.frombuffer(f.readframes(f.getnframes()), np.int16).astype(np.float32) / 32768
    segments, info = model.transcribe(
        audio,
        language=None if args.language == "auto" else args.language,
        word_timestamps=True,
        initial_prompt=f"{FILLER_PROMPT} Terms: {vocab}.",
        hotwords=vocab,
        beam_size=5,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 400},
        condition_on_previous_text=False,
    )

    out_segs, lines, unsure, idx = [], [], 0, 0
    for s in segments:
        words = [
            {"id": f"w{idx + k}", "w": w.word.strip(), "s": round(w.start, 3), "e": round(w.end, 3), "p": round(w.probability, 2),
             **({"filler": True} if w.word.strip(" ,.!?").lower() in FILLERS else {})}
            for k, w in enumerate(s.words or [])
        ]
        idx += len(words)
        out_segs.append({"s": round(s.start, 3), "e": round(s.end, 3), "text": s.text.strip(), "words": words})
        shown = " ".join(f"[[{w['w']}?]]" if w["p"] < LOW_CONF and not w.get("filler") else w["w"] for w in words)
        unsure += sum(1 for w in words if w["p"] < LOW_CONF and not w.get("filler"))
        lines.append(f"[{fmt(s.start)}-{fmt(s.end)}] {shown or s.text.strip()}")
        print(lines[-1], flush=True)

    save_json({"language": info.language, "duration": info.duration, "model": args.model, "segments": out_segs},
              work / "transcript.json")
    (work / "transcript.txt").write_text("\n".join(lines) + "\n")
    write_word_index(out_segs, work / "words.txt")
    wav.unlink(missing_ok=True)
    print(f"\nwrote {work/'transcript.json'} and {work/'transcript.txt'} ({len(out_segs)} segments, "
          f"{unsure} low-confidence words marked [[word?]])")


def write_word_index(segments, path):
    """words.txt: the transcript with a word id before every word, so Beats can be
    anchored to exact words: `[01:12.4] w310:the w311:gateway w312:checks`."""
    lines = [f"[{fmt(s['s'])}] " + " ".join(f"{w['id']}:{w['w']}" for w in s["words"]) for s in segments]
    Path(path).write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
