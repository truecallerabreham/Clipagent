"""Shared helpers for the edit-recording scripts: ffmpeg/ffprobe access and the
source-time -> output-time mapping that every EDL event goes through."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent  # engine/clipagent (assets live here)
FONTS_DIR = SKILL_DIR / "assets" / "fonts"


def tool(name):
    """Locate ffmpeg/ffprobe: $FFMPEG_DIR, then PATH, then ~/.local/bin."""
    cands = []
    if os.environ.get("FFMPEG_DIR"):
        cands.append(Path(os.environ["FFMPEG_DIR"]) / name)
    found = shutil.which(name)
    if found:
        cands.append(Path(found))
    cands.append(Path.home() / ".local" / "bin" / name)
    for c in cands:
        if c.exists():
            return str(c)
    print(f"warning: {name} not found; run scripts/setup.sh", file=sys.stderr)
    return name


FFMPEG = tool("ffmpeg")
FFPROBE = tool("ffprobe")


def run(cmd, quiet=True):
    """Run a command, raising with stderr on failure."""
    p = subprocess.run(cmd, capture_output=quiet, text=True)
    if p.returncode != 0:
        msg = (p.stderr or "")[-4000:] if quiet else ""
        raise RuntimeError(f"command failed ({p.returncode}): {' '.join(map(str, cmd))[:400]}\n{msg}")
    return p


def probe(path):
    """Return a compact dict: duration, video (w,h,fps), audio (rate, channels)."""
    out = run([FFPROBE, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)]).stdout
    d = json.loads(out)
    info = {"path": str(path), "duration": float(d["format"].get("duration", 0)), "video": None, "audio": None}
    for s in d["streams"]:
        if s["codec_type"] == "video" and info["video"] is None and s.get("disposition", {}).get("attached_pic", 0) == 0:
            num, den = (s.get("avg_frame_rate") or s.get("r_frame_rate") or "30/1").split("/")
            fps = float(num) / float(den) if float(den) else 30.0
            rot = 0
            for sd in s.get("side_data_list", []) or []:
                if "rotation" in sd:
                    rot = int(sd["rotation"])
            w, h = s["width"], s["height"]
            if abs(rot) in (90, 270):
                w, h = h, w
            info["video"] = {"width": w, "height": h, "fps": round(fps, 3), "codec": s.get("codec_name"),
                             "transfer": s.get("color_transfer")}
        elif s["codec_type"] == "audio" and info["audio"] is None:
            info["audio"] = {"rate": int(s.get("sample_rate", 48000)), "channels": s.get("channels", 2), "codec": s.get("codec_name")}
    return info


def load_json(path):
    with open(path) as f:
        return json.load(f)


def save_json(obj, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, indent=2)


class Timeline:
    """Maps source seconds to output seconds through the EDL `segments`
    (kept ranges, each with a playback speed).

    Everything in an EDL is written in *source* time (the transcript's clock),
    so Claude never has to do cut arithmetic; the renderer remaps here."""

    def __init__(self, segments, fps, src_duration=None):
        self.fps = fps
        snap = lambda t: round(t * fps) / fps  # frame-align so audio and video cut identically
        segs = []
        for s in sorted(segments, key=lambda s: s["start"]):
            a, b, sp = snap(s["start"]), snap(s["end"]), max(1, int(round(s.get("speed", 1))))
            if src_duration:
                b = min(b, snap(src_duration - 1.0 / fps))
            if segs and a < segs[-1][1]:
                a = segs[-1][1]  # overlapping ranges: later one yields
            frames = round((b - a) * fps) // sp * sp  # whole output frames per segment
            if frames >= sp:
                segs.append((a, a + frames / fps, sp))
        self.segments = segs
        self.offsets = []
        acc = 0.0
        for a, b, sp in segs:
            self.offsets.append(acc)
            acc += (b - a) / sp
        self.duration = acc

    def to_out(self, t, snap="next"):
        """Source time -> output time. Times inside a cut snap to the next kept
        segment's start (or the previous end with snap='prev')."""
        for (a, b, sp), off in zip(self.segments, self.offsets):
            if t < a:
                return off if snap == "next" else max(0.0, off - 1e-6)
            if t <= b:
                return off + (t - a) / sp
        return self.duration

    def speed_at(self, t_out):
        for (a, b, sp), off in zip(self.segments, self.offsets):
            if off <= t_out < off + (b - a) / sp:
                return sp
        return 1

    def span(self, start, end):
        """Map a source [start, end] span; None if it was cut away entirely."""
        s, e = self.to_out(start, "next"), self.to_out(end, "prev")
        return (s, e) if e - s > 0.05 else None
