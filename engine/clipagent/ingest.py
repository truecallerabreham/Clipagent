"""Turn a Take (recorder output) into edit-ready media.

MediaRecorder writes variable-frame-rate WebM with no duration index and three
separate streams. Ingest aligns them on the Take clock and writes:

  work/screen.mp4   screen video, constant 30 fps, with the mic muxed in (the "screen" audio)
  work/camera.mp4   webcam video aligned to the screen clock (camera_offset 0), when recorded live
  work/events.json  normalized input events + Scratch Markers + the overlay rect to hide
"""
from __future__ import annotations

import json
from pathlib import Path

from .common import FFMPEG, probe, run, save_json
from .session import Session, take_manifest

FPS = 30


def _offset_args(offset: float) -> list[str]:
    return ["-itsoffset", f"{offset:.3f}"] if offset and abs(offset) > 1e-3 else []


def ingest_take(s: Session, fps: int = FPS) -> dict:
    tk = take_manifest(s)
    dur = float(tk.get("duration") or 0)
    streams = tk.get("streams", {})
    work = s.work
    work.mkdir(exist_ok=True)
    out = {"duration": dur}

    scr = streams.get("screen")
    if not scr:
        raise SystemExit("take has no screen stream")
    mic = streams.get("mic")
    cmd = [FFMPEG, "-y", "-v", "error", *_offset_args(scr.get("start_offset", 0)), "-i", str(s.take / scr["file"])]
    if mic and (s.take / mic["file"]).exists():
        cmd += [*_offset_args(mic.get("start_offset", 0)), "-i", str(s.take / mic["file"])]
    vf = f"fps={fps},scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p"
    cmd += ["-map", "0:v:0"] + (["-map", "1:a:0", "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-ac", "1"] if mic else [])
    cmd += ["-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-g", str(fps * 2)]
    if dur:
        cmd += ["-t", f"{dur:.3f}"]
    cmd += [str(work / "screen.mp4")]
    print("ingest: screen + mic -> work/screen.mp4", flush=True)
    run(cmd)
    out["screen"] = str(work / "screen.mp4")

    cam = streams.get("camera")
    if cam and (s.take / cam["file"]).exists():
        print("ingest: camera -> work/camera.mp4", flush=True)
        cmd = [FFMPEG, "-y", "-v", "error", *_offset_args(cam.get("start_offset", 0)), "-i", str(s.take / cam["file"]),
               "-vf", f"fps={fps},scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p", "-an",
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-g", str(fps * 2)]
        if dur:
            cmd += ["-t", f"{dur:.3f}"]
        run(cmd + [str(work / "camera.mp4")])
        out["camera"] = str(work / "camera.mp4")
        out["camera_offset"] = 0.0

    meta = s.meta()
    if meta.get("camera_file"):  # phone / DSLR file, synced by audio in analyze
        out["camera"] = meta["camera_file"]
        out.pop("camera_offset", None)

    events = load_events(s.take / "events.jsonl")
    save_json({"source": tk.get("input", {}).get("source", "none"),
               "warning": tk.get("input", {}).get("warning"),
               "display": tk.get("display"),
               "overlay_rect": tk.get("overlay_rect"),
               "events": events}, work / "events.json")
    out["events"] = str(work / "events.json")
    save_json(out, work / "media.json")
    s.update(status="ingested")
    return out


def import_media(s: Session, screen: str, camera: str | None = None) -> dict:
    """Use an existing recording instead of a live Take (no input events)."""
    work = s.work
    out = {"screen": str(Path(screen).resolve()), "duration": probe(screen)["duration"]}
    if camera:
        out["camera"] = str(Path(camera).resolve())
    save_json({"source": "none", "warning": "imported recording: no input events", "display": None,
               "overlay_rect": None, "events": []}, work / "events.json")
    out["events"] = str(work / "events.json")
    save_json(out, work / "media.json")
    s.update(status="ingested", imported=True)
    return out


def load_events(path: Path) -> list[dict]:
    if not path.exists():
        return []
    ev = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue  # a crash can leave a half-written last line
        if "t" in e and "type" in e:
            e.pop("char", None)  # privacy: plain characters are never kept, even if a recorder emitted one
            e.pop("text", None)
            ev.append(e)
    ev.sort(key=lambda e: e["t"])
    return ev
