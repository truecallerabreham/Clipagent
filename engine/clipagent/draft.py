"""Turn transcript.json + analysis.json into a first-draft edl.json.

The draft is mechanical: it trims dead air, drops filler words, turns silent
stretches where the screen is busy (typing, builds, installs) into speed-ups,
and proposes zooms where activity concentrates. Claude then does the editorial
pass (retakes, titles, chapters, callouts, verifying zooms by eye).

usage: uv run draft_edl.py WORKDIR --screen S.mp4 [--camera C.mp4] [--format landscape|vertical]
       [--max-gap 0.5] [--no-fillers]
"""
import argparse
import os
import sys
from pathlib import Path

from . import events as EV
from .common import load_json, save_json
from .looks import apply_look_style, load_look

PAD_BEFORE, PAD_AFTER = 0.12, 0.22


def activity_between(activity, a, b):
    xs = [s["change"] for s in activity if a <= s["t"] <= b]
    return sum(xs) / len(xs) if xs else 0.0


def build_segments(words, activity, duration, max_gap, drop_fillers):
    """Walk the words, closing a segment at every long gap; busy gaps become speed-ups."""
    kept, fillers_before = [], {}
    for w in words:
        if drop_fillers and w.get("filler"):
            if kept:
                fillers_before.setdefault(len(kept), []).append(w)
        else:
            kept.append(w)
    words = kept
    if not words:
        return [{"start": 0.0, "end": round(duration, 3), "speed": 1}], []
    segs, removed = [], []
    cur_s = max(0.0, words[0]["s"] - PAD_BEFORE)
    for i, (prev, nxt) in enumerate(zip(words, words[1:]), start=1):
        gap = nxt["s"] - prev["e"]
        fl = fillers_before.get(i)
        if gap <= max_gap and not fl:
            continue
        end = prev["e"] + PAD_AFTER
        start_next = nxt["s"] - PAD_BEFORE
        if fl:  # cut tightly around the filler(s) so no "um" survives in the padding
            end, start_next = min(end, fl[0]["s"]), max(start_next, fl[-1]["e"])
        segs.append({"start": round(cur_s, 3), "end": round(end, 3), "speed": 1})
        busy = activity_between(activity, end, start_next)
        if gap > 2.5 and busy > 0.002:
            speed = min(8, max(2, round(gap / 2.5)))
            segs.append({"start": round(end, 3), "end": round(start_next, 3), "speed": speed,
                         "note": f"silent but screen busy ({gap:.1f}s)"})
        else:
            removed.append([round(end, 2), round(start_next, 2)])
        cur_s = start_next
    segs.append({"start": round(cur_s, 3), "end": round(min(duration, words[-1]["e"] + PAD_AFTER + 0.3), 3), "speed": 1})
    return segs, removed


def fit_aspect(rect, aspect, min_w=0.38):
    """Grow rect to the output aspect (in source-normalized units), keep inside [0,1]."""
    x, y, w, h = rect
    cx, cy = x + w / 2, y + h / 2
    w, h = max(w * 1.3, min_w), h * 1.3
    if w / h < aspect:
        w = h * aspect
    else:
        h = w / aspect
    if w > 1 or h > 1:
        return None
    x = min(max(cx - w / 2, 0), 1 - w)
    y = min(max(cy - h / 2, 0), 1 - h)
    return [round(x, 3), round(y, 3), round(w, 3), round(h, 3)]


def suggest_zooms(activity, src_aspect, window=3.0):
    """Windows where the changing region is small and stable -> zoom candidates."""
    out = []
    samples = [s for s in activity if s["box"]]
    i = 0
    while i < len(samples):
        t0 = samples[i]["t"]
        group = [s for s in samples[i:] if s["t"] < t0 + window]
        xs0 = min(s["box"][0] for s in group); ys0 = min(s["box"][1] for s in group)
        xs1 = max(s["box"][0] + s["box"][2] for s in group); ys1 = max(s["box"][1] + s["box"][3] for s in group)
        union = [xs0, ys0, xs1 - xs0, ys1 - ys0]
        rect = fit_aspect(union, 1.0) if union[2] * union[3] < 0.25 else None
        # rect is in normalized coords; normalized aspect 1.0 == source aspect
        if rect and rect[2] < 0.8:
            if out and out[-1]["end"] >= t0 - 1.0 and _iou(out[-1]["rect"], rect) > 0.4:
                out[-1]["end"] = round(group[-1]["t"] + 0.5, 2)
            else:
                out.append({"start": round(t0, 2), "end": round(group[-1]["t"] + 0.5, 2), "rect": rect,
                            "note": "auto: activity concentrated here - verify with frames.py"})
        i += len(group)
    return [z for z in out if z["end"] - z["start"] >= 2.5]


def _iou(a, b):
    ax1, ay1, bx1, by1 = a[0] + a[2], a[1] + a[3], b[0] + b[2], b[1] + b[3]
    iw = max(0, min(ax1, bx1) - max(a[0], b[0])); ih = max(0, min(ay1, by1) - max(a[1], b[1]))
    inter = iw * ih
    return inter / (a[2] * a[3] + b[2] * b[3] - inter + 1e-9)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("workdir")
    ap.add_argument("--screen", required=True)
    ap.add_argument("--camera")
    ap.add_argument("--camera-rect")
    ap.add_argument("--format", default="landscape", choices=["landscape", "vertical"])
    ap.add_argument("--max-gap", type=float, default=0.5)
    ap.add_argument("--no-fillers", action="store_true", help="keep filler words")
    ap.add_argument("--events", help="work/events.json from ingest (clicks, shortcuts, Scratch Markers)")
    ap.add_argument("--look", help="Look id; styles the whole video (default: architecture-flow until the agent picks)")
    ap.add_argument("--camera-offset", type=float, help="known camera offset (live webcam: 0)")
    ap.add_argument("--mic", default="earphones", choices=["earphones", "phone", "laptop", "studio"],
                    help="mic feeding the screen recording; picks the EQ profile")
    args = ap.parse_args(argv)

    work = Path(args.workdir)
    tr = load_json(work / "transcript.json")
    an = load_json(work / "analysis.json")
    words = [w for s in tr["segments"] for w in s["words"]]
    dur = an["screen"]["duration"]
    segs, removed = build_segments(words, an["activity"], dur, args.max_gap, not args.no_fillers)
    v = an["screen"]["video"]
    zooms = suggest_zooms(an["activity"], v["width"] / v["height"])
    ev = load_json(args.events) if args.events and Path(args.events).exists() else {"events": []}
    look = load_look(args.look or "architecture-flow")
    zscale = tuple(look.get("screen_treatment", {}).get("zoom_scale", [1.2, 1.6]))
    clk = EV.clicks(ev["events"], an["activity"])
    czooms = EV.click_zooms(clk, scale=zscale)
    # click zooms are the strongest signal of where the viewer should look: they win over activity guesses
    zooms = sorted(czooms + [z for z in zooms if not any(_iou(z["rect"], c["rect"]) > 0.2 and
                                                           z["start"] < c["end"] and c["start"] < z["end"] for c in czooms)],
                   key=lambda z: z["start"])
    segs, scratched = EV.apply_scratches(segs, words, EV.scratch_markers(ev["events"]), EV.spoken_scratches(words))
    cam_q = (an.get("camera_look") or {}).get("quality", {})
    # the mic with the best signal-to-noise wins (earphones on the laptop vs. the phone's own mic)
    voices = {k: x for k, x in (an.get("voice") or {}).items() if x}
    mic = max(voices, key=lambda k: voices[k]["snr_db"]) if voices else ("screen" if an["screen"]["audio"] else "camera")

    edl = {
        "version": 1,
        "inputs": {
            "screen": str(Path(args.screen).resolve()),
            "camera": str(Path(args.camera).resolve()) if args.camera else None,
            "camera_offset": args.camera_offset if args.camera_offset is not None else (an.get("sync") or {}).get("camera_offset", 0.0),
            "camera_rect": [float(x) for x in args.camera_rect.split(",")] if args.camera_rect else None,
            "audio": mic,
        },
        "voice": {"denoise": (voices.get(mic) or {}).get("denoise", "normal"), "mic": args.mic if mic == "screen" else "phone"},
        "output": {"path": str((work / "final.mp4").resolve()), "format": args.format, "fps": 30},
        "style": {
            "accent": "#D97757",
            "background": ["#14141f", "#2b1d3a"],
            "screen_inset": 0.035,
            "radius": 18,
            "font": "Inter",
            "captions": {"enabled": True, "words_per_line": 4, "highlight": "#D97757"},
            "badge": "Made with ClipAgent",
        },
        "camera": {"source": "webcam" if args.camera_offset is not None else "phone", "grade": "auto", "shape": "circle",
                   "size": 0.23 if cam_q.get("rating", "good") != "poor" else 0.17, "corner": "br", "mirror": False,
                   "quality": cam_q.get("rating"), "allow_full": cam_q.get("rating", "good") != "poor"},
        "glossary": {"cloud code": "Claude Code", "clod code": "Claude Code"},
        "caption_edits": [],
        "segments": segs,
        "layouts": [],
        "zooms": zooms,
        "titles": [],
        "chapters": [],
        "callouts": [],
        "outro": {"text": "Made with ClipAgent", "sub": "", "duration": 4},
        "look": look["id"],
        "concepts": {},
        "inserts": [],
        "annotations": [],
        "shortcuts": EV.shortcuts(ev["events"]),
        "clicks": clk,
        "typing": EV.typing_spans(ev["events"]),
        "sound": {"sfx": True, "music": False},
        "shorts": [],
        "thumbnail": None,
        "publish": {},
        "mismatches": [],
        "_draft_removed_gaps": removed,
        "_draft_scratched": scratched,
    }
    if ev.get("overlay_rect"):  # recorder bar could not be hidden from capture (Linux): blur it out
        edl["redact"] = [{"rect": ev["overlay_rect"], "note": "recorder control bar"}]
    apply_look_style(edl, look)
    save_json(edl, work / "edl.json")
    kept = sum((s["end"] - s["start"]) / s["speed"] for s in segs)
    print(f"draft edl: {len(segs)} segments ({sum(1 for s in segs if s['speed'] > 1)} speed-ups), "
          f"{len(removed)} gaps cut, {len(scratched)} scratched, {len(zooms)} zoom suggestions ({len(czooms)} from clicks)")
    print(f"raw {dur:.1f}s -> about {kept:.1f}s")
    print(f"wrote {work / 'edl.json'}")


if __name__ == "__main__":
    main()
