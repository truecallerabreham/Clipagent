"""Resolve the agent's Inserts (word-anchored) into render-ready specs and render them.

In edl.json an Insert looks like:

    {"id": "ins-01", "start": "w120", "end": "w161",       # word ids (or source seconds)
     "mode": "full" | "split" | "overlay", "engine": "html" | "manim",
     "rect": [x, y, w, h],                                  # overlay only: canvas fractions
     "concepts": ["JWT", "session id"],
     "scene": {...},                                        # Look-specific, see looks/<look>/PRIMITIVES.md
     "beats": [{"word": "w123", "action": "send", "target": "jwt", "args": {}, "lead": -0.1}]}

Beats are anchored to words, never to seconds: after retakes and dead air are
cut, the same word lands at a new output time and the Beat follows it.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from ..common import Timeline, load_json, save_json
from ..looks import concept_colors, load_look

PRE_ROLL, POST_ROLL = 0.25, 0.45
OVERLAY_DEFAULT = [0.56, 0.1, 0.4, 0.42]


class InsertError(ValueError):
    pass


def word_index(transcript: dict) -> dict:
    return {w["id"]: w for s in transcript["segments"] for w in s["words"] if "id" in w}


def canvas_size(fmt: str) -> tuple[int, int]:
    return (1920, 1080) if fmt == "landscape" else (1080, 1920)


def insert_box(mode: str, W: int, H: int, rect=None, fmt="landscape") -> tuple[int, int, int, int]:
    """Where an Insert sits on the canvas (pixels). Shared by the renderer and the compositor."""
    if mode == "full":
        if fmt == "landscape":  # leave the bottom band for captions and the camera bubble
            return 0, 0, W, round(H * 0.86) // 2 * 2
        return 0, 0, W, H
    if mode == "split":
        if fmt == "landscape":
            # two 16:10 panels side by side: the Insert keeps a landscape layout
            m = round(H * 0.045)
            w = (W - 3 * m) // 2 // 2 * 2
            h = round(w * 10 / 16) // 2 * 2
            return W - m - w, (H - h) // 2, w, h
        m = round(W * 0.045)
        h = (H - 3 * m) // 2
        return m, m, W - 2 * m, h
    x, y, w, h = rect or OVERLAY_DEFAULT
    return round(x * W), round(y * H), round(w * W) // 2 * 2, round(h * H) // 2 * 2


def _src_time(ref, words, edge: str) -> float:
    if isinstance(ref, (int, float)):
        return float(ref)
    w = words.get(str(ref))
    if not w:
        raise InsertError(f"unknown word id {ref!r} (see work/words.txt)")
    return w["s"] if edge == "start" else w["e"]


def kept(tl: Timeline, t: float) -> bool:
    return any(a <= t <= b for a, b, _ in tl.segments)


def resolve(edl: dict, transcript: dict, tl: Timeline) -> tuple[list[dict], list[str]]:
    """-> (resolved specs, warnings)."""
    words = word_index(transcript)
    look = load_look(edl.get("look") or "architecture-flow")
    fmt = edl.get("output", {}).get("format", "landscape")
    fps = edl.get("output", {}).get("fps", 30)
    W, H = canvas_size(fmt)
    colors = concept_colors(edl, look)
    specs, warnings = [], []
    for i, ins in enumerate(edl.get("inserts", [])):
        iid = ins.get("id") or f"ins-{i + 1:02d}"
        try:
            s0 = _src_time(ins["start"], words, "start") - PRE_ROLL
            s1 = _src_time(ins["end"], words, "end") + POST_ROLL
        except (KeyError, InsertError) as e:
            warnings.append(f"{iid}: {e}; skipped")
            continue
        o0, o1 = tl.to_out(s0, "next"), tl.to_out(s1, "prev")
        if o1 - o0 < 1.0:
            warnings.append(f"{iid}: its words were cut from the edit (only {o1 - o0:.2f}s left); skipped")
            continue
        mode = ins.get("mode", "full")
        if mode not in ("full", "split", "overlay"):
            warnings.append(f"{iid}: unknown mode {mode!r}, using full")
            mode = "full"
        x, y, w, h = insert_box(mode, W, H, ins.get("rect"), fmt)
        beats = []
        for b in ins.get("beats", []):
            ref = b.get("word", b.get("at_src"))
            if ref is None:
                warnings.append(f"{iid}: beat {b.get('action')} has no word; skipped")
                continue
            try:
                st = _src_time(ref, words, "start")
            except InsertError as e:
                warnings.append(f"{iid}: {e}")
                continue
            if not kept(tl, st):
                warnings.append(f"{iid}: beat '{b.get('action')}' on {ref} falls in a cut; it plays at the next kept word")
            at = tl.to_out(st, "next") - o0 + float(b.get("lead", 0.0))
            beats.append({"at": round(max(0.0, min(at, o1 - o0 - 0.1)), 3),
                          **{k: v for k, v in b.items() if k not in ("word", "at_src", "lead")}})
        beats.sort(key=lambda b: b["at"])
        names = ins.get("concepts") or []
        spec = {
            "id": iid,
            "look": look["id"],
            "engine": ins.get("engine", "html"),
            "mode": mode,
            "size": [w, h],
            "transparent": mode == "overlay",
            "fps": fps,
            "format": fmt,
            "duration": round(o1 - o0, 3),
            "concepts": {n: colors.get(n, look["accent"]) for n in (names if isinstance(names, list) else names.keys())} | colors,
            "scene": ins.get("scene", {}),
            "beats": beats,
            "_placement": {"out_start": round(o0, 3), "out_end": round(o1, 3), "box": [x, y, w, h],
                           "src": [round(s0, 3), round(s1, 3)], "transition": ins.get("transition"),
                           "backdrop": ins.get("backdrop", True)},
        }
        specs.append(spec)
    _check_overlaps(specs, warnings)
    return specs, warnings


def _check_overlaps(specs, warnings):
    seq = sorted(specs, key=lambda s: s["_placement"]["out_start"])
    for a, b in zip(seq, seq[1:]):
        if b["_placement"]["out_start"] < a["_placement"]["out_end"] - 0.05:
            shift = a["_placement"]["out_end"] - b["_placement"]["out_start"]
            # back-to-back Inserts share only the lead-in/tail padding (0.25 + 0.45 s): a hard cut, not a problem
            if shift > 0.75:
                warnings.append(f"{a['id']} and {b['id']} overlap in time; {b['id']} starts when {a['id']} ends")
            b["_placement"]["out_start"] = a["_placement"]["out_end"]
            b["duration"] = round(b["duration"] - shift, 3)
            for bt in b["beats"]:
                bt["at"] = round(max(0.0, bt["at"] - shift), 3)


def spec_hash(spec: dict) -> str:
    look_dir = Path(load_look(spec["look"])["_dir"])
    h = hashlib.sha256(json.dumps({k: v for k, v in spec.items() if k != "_placement"}, sort_keys=True).encode())
    for f in sorted(look_dir.rglob("*")):
        if f.is_file() and f.suffix in (".js", ".css", ".json", ".py", ".svg", ".html") and "reference" not in f.parts:
            h.update(f.name.encode() + str(f.stat().st_mtime_ns).encode())
    rt = look_dir.parent / "_runtime"
    if rt.exists():
        for f in sorted(rt.rglob("*")):
            if f.is_file():
                h.update(f.name.encode() + str(f.stat().st_mtime_ns).encode())
    return h.hexdigest()[:16]


def render_all(work: Path, edl: dict, transcript: dict, tl: Timeline, only=None, workers=0, force=False) -> dict:
    """Resolve + render every Insert into work/inserts/<id>/frames/. Returns the manifest."""
    specs, warnings = resolve(edl, transcript, tl)
    root = work / "inserts"
    root.mkdir(exist_ok=True)
    manifest = {"inserts": [], "warnings": warnings}
    for spec in specs:
        d = root / spec["id"]
        d.mkdir(exist_ok=True)
        spec_path = d / "spec.json"
        save_json({k: v for k, v in spec.items() if k != "_placement"}, spec_path)
        frames = d / "frames"
        key = spec_hash(spec)
        stamp = d / "rendered.txt"
        n_expected = int(round(spec["duration"] * spec["fps"]))
        fresh = stamp.exists() and stamp.read_text().strip() == key and frames.exists() and \
            len(list(frames.glob("*.png"))) >= n_expected
        if (only and spec["id"] not in only) or (fresh and not force):
            status = "cached" if fresh else "skipped"
        else:
            if frames.exists():
                shutil.rmtree(frames)
            frames.mkdir()
            print(f"insert {spec['id']}: {spec['engine']} {spec['mode']} {spec['size'][0]}x{spec['size'][1]} "
                  f"{spec['duration']:.1f}s ({n_expected} frames)", flush=True)
            try:
                render_one(spec, spec_path, frames, workers)
                stamp.write_text(key)
                status = "rendered"
            except Exception as e:  # one broken Insert must not sink the video: report it, drop it
                status = "failed"
                manifest["warnings"].append(f"{spec['id']}: render failed: {e}")
                print(f"insert {spec['id']} FAILED: {e}", flush=True)
        manifest["inserts"].append({"id": spec["id"], "status": status, "frames": str(frames), "spec": str(spec_path),
                                    "mode": spec["mode"], "fps": spec["fps"], "duration": spec["duration"],
                                    "transparent": spec["transparent"], **spec["_placement"]})
    save_json(manifest, root / "manifest.json")
    for w in manifest["warnings"]:
        print("warning:", w)
    return manifest


def render_one(spec: dict, spec_path: Path, frames: Path, workers: int):
    if spec["engine"] == "manim":
        from .manim_render import render_manim
        render_manim(spec_path, frames)
    else:
        from .html_render import render_insert
        render_insert(spec_path, frames, workers=workers)


def load_manifest(work: Path) -> dict:
    f = work / "inserts" / "manifest.json"
    return load_json(f) if f.exists() else {"inserts": [], "warnings": []}
