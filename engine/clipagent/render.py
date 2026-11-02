"""Render an edl.json into the finished video.

Pass 1 (ffmpeg, cached): cut + speed-ramp the screen, camera and audio on the
EDL segments; grade the camera; master the voice. -> WORKDIR/render/*
Pass 2 (Python compositor -> x264): layouts, zooms, camera bubble, spotlights,
titles/captions (libass), fades.

usage:
  uv run render.py EDL.json                       # full quality -> output.path
  uv run render.py EDL.json --preview             # half-res, fast encode -> *_preview.mp4
  uv run render.py EDL.json --range 30 75         # only source seconds 30-75 (implies --preview)
  uv run render.py EDL.json --still 42.5 60 91    # composited PNG stills at source times (for QA)
  uv run render.py EDL.json --force-cut           # redo pass 1 even if cached
"""
import argparse
import collections
import hashlib
import json
import math
import multiprocessing as mp
import os
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np

from . import compose as C
from . import effects as FX
from .inserts.build import load_manifest
from . import overlays as O
from .common import FFMPEG, FONTS_DIR, SKILL_DIR, Timeline, load_json, probe, run

MAX_SCREEN_W = 2560
CAM_H = 1080  # phone footage: keep full HD so the full-screen intro stays sharp


# ---------------------------------------------------------------- camera grade

def grade_params(cfg, look, source="webcam"):
    """Resolve the camera grade: 'auto' derives exposure + white balance from
    analysis.json's camera_look; any key can be overridden in edl.camera.grade.
    Returns None for grade 'off'."""
    if cfg in ("off", None, False):
        return None
    g = cfg if isinstance(cfg, dict) else {}
    look = look or {}
    # phone footage is already processed in-camera: grade it gently, don't re-sharpen
    phone = {"denoise": 1.5, "sharpen": 0.15, "white_balance": 0.35, "contrast": 1.03, "saturation": 1.06}
    g = {**(phone if source == "phone" else {}), **g}
    luma = look.get("luma", 115.0)
    target = g.get("target_luma", 118.0)
    r, gr, b = look.get("rgb_mean", [128, 128, 128])
    avg = (r + gr + b) / 3
    wb = g.get("white_balance", 0.6)  # 0 = leave color cast, 1 = full gray-world neutralize
    return {
        "gains": [min(1.35, max(0.75, (avg / max(c, 1)) ** wb)) for c in (r, gr, b)],
        "gamma": g.get("gamma") or min(1.6, max(0.75, math.log(max(luma, 5) / 255) / math.log(target / 255))),
        "contrast": g.get("contrast", 1.06),
        "saturation": g.get("saturation", 1.12),
        "warmth": g.get("warmth", 1),
        "sharpen": g.get("sharpen", 0.5),
        "denoise": g.get("denoise", 3),
    }


def denoise_filter(p):
    """Temporal denoise is the one grade step that needs neighbouring frames,
    so it stays in ffmpeg; color is applied per frame by compose.Grade."""
    d = (p or {}).get("denoise", 0)
    return f"hqdn3d={d}:{d}:{d * 2}:{d * 2}," if d else ""


RNNOISE = SKILL_DIR / "assets" / "models" / "sh.rnnn"

# EQ per mic: earphone mics are thin and boxy, phone mics a bit harsh
MIC_EQ = {
    "earphones": "equalizer=f=170:t=q:w=0.9:g=3,equalizer=f=750:t=q:w=1.2:g=-2,equalizer=f=3500:t=q:w=1.3:g=2,"
                 "highshelf=f=9000:g=1.5",
    "phone": "equalizer=f=200:t=q:w=1:g=1.5,equalizer=f=2600:t=q:w=1.2:g=-1.5,equalizer=f=5000:t=q:w=1:g=1",
    "laptop": "equalizer=f=180:t=q:w=1:g=2.5,equalizer=f=1000:t=q:w=1.2:g=-2,equalizer=f=3500:t=q:w=1.2:g=2.5",
    "studio": "equalizer=f=220:t=q:w=1:g=-1.5,equalizer=f=3200:t=q:w=1.2:g=1.5",
}


def voice_chain(cfg):
    """Mono voice cleanup + mastering. denoise: light | normal | strong.
    strong = RNNoise neural denoiser at full mix + spectral cleanup + a soft
    gate that pushes leftover hiss down between words."""
    level = cfg.get("denoise", "normal")
    parts = ["highpass=f=85", "adeclick=w=55:o=75"]
    if RNNOISE.exists() and level in ("normal", "strong"):
        model = str(RNNOISE).replace("\\", "/").replace(":", "\\:")
        parts.append(f"arnndn=m='{model}':mix={0.8 if level == 'normal' else 1.0}")
    parts.append({"light": "afftdn=nr=8:nf=-45:tn=1", "normal": "afftdn=nr=8:nf=-42:tn=1",
                  "strong": "afftdn=nr=14:nf=-38:tn=1"}[level])
    if level == "strong":
        parts.append("agate=threshold=0.012:ratio=2:range=0.12:attack=6:release=220:knee=4")
    parts += [MIC_EQ.get(cfg.get("mic", "earphones"), MIC_EQ["earphones"]),
              "deesser=i=0.4", "acompressor=threshold=-22dB:ratio=3:attack=8:release=140:makeup=2",
              "loudnorm=I=-14:TP=-1.5:LRA=9", "aresample=48000", "pan=stereo|c0=c0|c1=c0"]
    return ",".join(parts)


# ---------------------------------------------------------------- pass 1

def hdr_to_sdr(info):
    """iPhones and many Androids shoot HDR (HLG/PQ); tone-map it or it looks washed out."""
    if (info.get("video") or {}).get("transfer") in ("arib-std-b67", "smpte2084"):
        return ("zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=hable:desat=0,"
                "zscale=t=bt709:m=bt709:r=tv,format=yuv420p,")
    return ""


def build_cut_graph(edl, tl, fps, scr, cam, look):
    inp = edl["inputs"]
    cam_cfg = edl.get("camera", {})
    n = len(tl.segments)
    off = float(inp.get("camera_offset") or 0.0)
    g = []

    # screen (an inline webcam baked into it is graded later, in compose)
    g.append(f"[0:v]fps={fps},scale='min({MAX_SCREEN_W},iw)':-2:flags=lanczos,format=yuv420p,split={n}" + "".join(f"[s{i}]" for i in range(n)))
    for i, (a, b, sp) in enumerate(tl.segments):
        g.append(f"[s{i}]trim=start={a:.4f}:end={b:.4f},setpts=(PTS-STARTPTS)/{sp}[v{i}]")
    g.append("".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0,fps={fps}[vout]")

    # camera: align to the screen clock, denoise, cut identically
    if cam:
        cam_dur = probe(inp["camera"])["duration"]
        shift = f"trim=start={off:.4f},setpts=PTS-STARTPTS" if off >= 0 else f"tpad=start_duration={-off:.4f}:start_mode=clone"
        tail = max(0.0, scr["duration"] - (cam_dur - off)) + 2
        mirror = ",hflip" if cam_cfg.get("mirror") else ""
        grade = grade_params(cam_cfg.get("grade", "auto"), look, cam_cfg.get("source", "phone"))
        g.append(f"[1:v]fps={fps},{shift},tpad=stop_mode=clone:stop_duration={tail:.2f},{hdr_to_sdr(cam)}"
                 f"scale=-2:'min({CAM_H},ih)'{mirror},{denoise_filter(grade)}format=yuv420p,split={n}" + "".join(f"[c{i}]" for i in range(n)))
        for i, (a, b, sp) in enumerate(tl.segments):
            g.append(f"[c{i}]trim=start={a:.4f}:end={b:.4f},setpts=(PTS-STARTPTS)/{sp}[cv{i}]")
        g.append("".join(f"[cv{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0,fps={fps}[cout]")

    # audio: choose the mic track, cut with 6ms fades (no clicks), master
    src = inp.get("audio", "screen")
    a_in = "[1:a]" if (src == "camera" and cam and cam.get("audio")) else ("[0:a]" if scr.get("audio") else None)
    if a_in:
        ashift = ""
        if a_in == "[1:a]":
            ashift = f",atrim=start={off:.4f},asetpts=PTS-STARTPTS" if off >= 0 else f",adelay={-off * 1000:.0f}:all=1"
        g.append(f"{a_in}aresample=48000,aformat=channel_layouts=mono{ashift},asplit={n}" + "".join(f"[a{i}]" for i in range(n)))
        for i, (a, b, sp) in enumerate(tl.segments):
            d = (b - a) / sp
            tempo = f",atempo={sp},volume=0.3" if sp > 1 else ""
            g.append(f"[a{i}]atrim=start={a:.4f}:end={b:.4f},asetpts=PTS-STARTPTS{tempo},"
                     f"afade=t=in:d=0.006,afade=t=out:st={max(0, d - 0.006):.4f}:d=0.006[A{i}]")
        g.append("".join(f"[A{i}]" for i in range(n)) + f"concat=n={n}:v=0:a=1,{voice_chain(edl.get('voice', {}))}[aout]")
    return ";\n".join(g), bool(a_in)


def pass1(edl, tl, fps, rdir, look, force):
    inp = edl["inputs"]
    scr = probe(inp["screen"])
    cam = probe(inp["camera"]) if inp.get("camera") else None
    graph, has_audio = build_cut_graph(edl, tl, fps, scr, cam, look)
    # the graph text encodes every cut/denoise/voice setting, so it is the cache key
    key = hashlib.sha1(json.dumps([inp, graph], sort_keys=True, default=str).encode()).hexdigest()
    stamp = rdir / "cut.key"
    outs = {"screen": rdir / "screen_cut.mp4", "camera": rdir / "camera_cut.mp4" if cam else None, "audio": rdir / "audio_cut.wav"}
    if not force and stamp.exists() and stamp.read_text() == key and all(p.exists() for p in outs.values() if p):
        print("pass 1: cached (cuts/denoise/audio unchanged)")
        return outs
    (rdir / "cut_graph.txt").write_text(graph)
    venc = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "13", "-g", str(int(fps)), "-pix_fmt", "yuv420p"]
    cmd = [FFMPEG, "-y", "-v", "error", "-stats", "-stats_period", "15", "-i", inp["screen"]]
    if cam:
        cmd += ["-i", inp["camera"]]
    ver = run([FFMPEG, "-hide_banner", "-version"]).stdout.split()[2]
    graph_opt = "-filter_complex_script" if ver[:1].isdigit() and int(ver.split(".")[0]) < 7 else "-/filter_complex"
    cmd += [graph_opt, str(rdir / "cut_graph.txt"), "-map", "[vout]", *venc, str(outs["screen"])]
    if cam:
        cmd += ["-map", "[cout]", *venc, str(outs["camera"])]
    if has_audio:
        cmd += ["-map", "[aout]", "-c:a", "pcm_s16le", str(outs["audio"])]
    print(f"pass 1: cutting {len(tl.segments)} segments, grading camera, mastering audio...", flush=True)
    t0 = time.time()
    subprocess.run(cmd, check=True)
    if not has_audio:
        run([FFMPEG, "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", f"{tl.duration:.3f}", str(outs["audio"])])
    stamp.write_text(key)
    (rdir / "audio_gain.txt").unlink(missing_ok=True)
    print(f"pass 1: done in {time.time() - t0:.0f}s")
    return outs


def loudness_gain(rdir, wav, target=-14.0):
    """dB to add so the final mix lands on the target loudness (single-pass
    loudnorm drifts by a few LU, especially on short clips). Cached."""
    cache = rdir / "audio_gain.txt"
    if cache.exists():
        return float(cache.read_text())
    out = subprocess.run([FFMPEG, "-hide_banner", "-i", str(wav), "-af", "ebur128=framelog=quiet", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    vals = [l.split("I:")[1].split()[0] for l in out.splitlines() if l.strip().startswith("I:")]
    gain = 0.0
    if vals and vals[-1] not in ("-inf", "-70.0"):
        gain = max(-12.0, min(12.0, target - float(vals[-1])))
    cache.write_text(f"{gain:.2f}")
    return gain


# ---------------------------------------------------------------- pass 2

class Reader:
    """Sequential raw-frame reader; repeats the last frame past EOF."""

    def __init__(self, path, start=0.0, width=None):
        v = probe(path)["video"]
        self.w = width or v["width"]
        self.h = int(round(v["height"] * self.w / v["width"] / 2) * 2)
        vf = [] if self.w == v["width"] else ["-vf", f"scale={self.w}:{self.h}:flags=lanczos"]
        self.p = subprocess.Popen([FFMPEG, "-v", "error", "-ss", f"{start:.3f}", "-i", str(path), *vf,
                                   "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], stdout=subprocess.PIPE, bufsize=10 ** 8)
        self.size = self.w * self.h * 3
        self.last = np.zeros((self.h, self.w, 3), np.uint8)

    def read(self):
        buf = self.p.stdout.read(self.size)
        if len(buf) == self.size:
            self.last = np.frombuffer(buf, np.uint8).reshape(self.h, self.w, 3)
        return self.last

    def close(self):
        self.p.kill()


class Editor:
    """Everything that depends only on the EDL + canvas size, precomputed once."""

    def __init__(self, edl, tl, W, H, fmt, look, has_cam, scr_info, work=None):
        self.edl, self.tl, self.W, self.H, self.fmt = edl, tl, W, H, fmt
        st = edl.get("style", {})
        self.accent = st.get("accent", "#D97757")
        bg = st.get("background", ["#14141f", "#2b1d3a"])
        self.bg = C.make_background(W, H, bg[0], bg[1], self.accent)
        self.inset = st.get("screen_inset", 0.035)
        self.radius = st.get("radius", 18) * (H if fmt == "landscape" else W) / 1080
        self.look = look
        cam_cfg_ = edl.get("camera", {})
        gp = grade_params(cam_cfg_.get("grade", "auto"), look,
                          cam_cfg_.get("source", "phone" if edl["inputs"].get("camera") else "webcam"))
        self.grade = C.Grade(gp) if gp else None
        self.inline_cam = edl["inputs"].get("camera_rect") if not edl["inputs"].get("camera") else None
        self.has_cam = has_cam
        self.src_aspect = scr_info["width"] / scr_info["height"]
        cam_cfg = edl.get("camera", {})
        self.geom = {m: C.layout_geometry(m, W, H, fmt, self.src_aspect, cam_cfg, self.inset)
                     for m in ("bubble", "side", "full", "hidden")}
        if not has_cam:
            for g in self.geom.values():
                g["cam_alpha"] = 0
        changes = [(tl.to_out(l["at"]), l["camera"]) for l in edl.get("layouts", [])]
        self.layouts = C.LayoutTrack(changes, self.geom)

        def span(item, dur_key="duration", default=3.0):
            s = tl.to_out(item.get("start", item.get("at", 0)))
            if "end" in item:
                e = tl.to_out(item["end"], "prev")
            else:
                e = s + item.get(dur_key, default)
            return s, max(e, s + 0.3)

        self.zooms = []
        for z in edl.get("zooms", []):
            sp = tl.span(z["start"], z["end"])
            if sp:
                self.zooms.append({"s": sp[0], "e": sp[1], "rect": z["rect"]})
        self.zoom = C.ZoomTrack(self.zooms)
        self.titles = [(*span(t, default=3.0), t) for t in edl.get("titles", [])]
        self.callouts = [(*span(c, default=3.0), c) for c in edl.get("callouts", [])]
        self.redactions = [(*span(r, default=1e9), r["rect"]) for r in edl.get("redact", [])]
        self.chapters = [(tl.to_out(c["at"]), i + 1, c) for i, c in enumerate(edl.get("chapters", []))]
        o = edl.get("outro") or {}
        self.outro = o.get("duration", 0) if o.get("text") else 0
        self.total = tl.duration + self.outro
        self._shadow_key, self._shadow_bg = None, None

        # Look screen treatment
        self.scale = (H if fmt == "landscape" else W) / 1080
        self.frame_kind = st.get("frame", "plain")
        self.dark = st.get("dark", True)
        self.click_kind = st.get("click_effect", "ripple")
        self.ann_color = st.get("annotation_color", "#FFFFFF")
        self.trans_kind = st.get("transition", "crossfade")
        self.trans_colors = st.get("transition_colors")
        self.badge = st.get("shortcut_badge", {"bg": "#1E1E1E", "fg": "#FFFFFF"})
        card = st.get("chapter_card") or {}
        self.card = card if card.get("enabled") else None
        self.clicks = [(tl.to_out(c["t"]), c["x"], c["y"]) for c in edl.get("clicks", [])
                       if any(a <= c["t"] <= b for a, b, _ in tl.segments)]
        self.annotations = [(*span(a, default=2.5), a) for a in edl.get("annotations", [])]
        # Inserts (rendered frames on disk), placed in output time
        self.inserts, self.split_geom = [], None
        if work is not None:
            base_w = 1920 if fmt == "landscape" else 1080
            k = W / base_w
            for ins in load_manifest(work)["inserts"]:
                if ins["status"] not in ("rendered", "cached"):
                    continue
                n = len(list(Path(ins["frames"]).glob("*.png")))
                if not n:
                    continue
                x, y, w, h = (int(round(v * k)) for v in ins["box"])
                tk = ins.get("transition") or (self.trans_kind if ins["mode"] == "full" else "crossfade")
                self.inserts.append({**ins, "n": n, "px": (x, y, max(2, w), max(2, h)), "tkind": tk,
                                     "T": FX.TRANSITION_T.get(tk, 0.35) or 0.0})
            self.inserts.sort(key=lambda i: i["out_start"])
            for i in self.inserts:
                if i["mode"] == "split":
                    x, y, w, h = i["px"]
                    if fmt == "landscape":
                        bx, by, bw, bh = W - x - w, y, w, h          # mirror of the Insert panel
                    else:
                        bx, by, bw, bh = x, y + h + (H - 2 * y - 2 * h), w, h
                    fw = min(bw, bh * self.src_aspect)
                    fh = fw / self.src_aspect
                    self.split_geom = (bx + (bw - fw) / 2, by + (bh - fh) / 2, fw, fh)
                    break

    def active_insert(self, t):
        """-> (insert, progress_in, progress_out) or (None, 0, 0)."""
        for ins in self.inserts:
            a, b, T = ins["out_start"], ins["out_end"], ins["T"]
            if a <= t < b:
                pin = 1.0 if T <= 0 else min(1.0, (t - a) / T)
                pout = 0.0 if T <= 0 else max(0.0, 1 - (b - t) / T)
                return ins, pin, pout
        return None, 0.0, 0.0

    def to_canvas(self, x, y, box, z):
        sx, sy, sw, sh = box
        return sx + (x - z[0]) / z[2] * sw, sy + (y - z[1]) / z[3] * sh

    # -- per frame
    def background_with_shadows(self, screen_box, cam_box, cam_alpha, radius):
        key = tuple(int(v) for v in (*screen_box, *cam_box)) + (round(cam_alpha, 2),)
        if key != self._shadow_key:
            rects = [(*screen_box, self.radius)]
            if cam_alpha > 0.5:
                rects.append((*cam_box, radius))
            self._shadow_bg = C.drop_shadow(self.bg, rects)
            self._shadow_key = key
        return self._shadow_bg

    def frame(self, t, scr, cam):
        W, H = self.W, self.H
        if t >= self.tl.duration:  # outro: last frame, blurred and dimmed under the card
            p = C.ease((t - self.tl.duration) / 0.6)
            # past the end the readers repeat their final frame, so this is deterministic per process
            if not hasattr(self, "_outro_base"):
                self._outro_base = self.frame(self.tl.duration - 1e-3, scr, cam)
            base = self._outro_base
            return cv2.convertScaleAbs(C.soft_blur(base, 0.9 * p), alpha=1 - 0.55 * p)

        g, p, prev_g = self.layouts.at(t)
        ins, pin, pout = self.active_insert(t)
        if ins is not None and ins["mode"] == "split" and self.split_geom:
            q = C.ease(pin) * (1 - C.ease(pout))
            g = dict(g, screen=C.lerp(g["screen"], self.split_geom, q))
        sx, sy, sw, sh = g["screen"]
        cx, cy, cw, ch = g["cam"]
        cam_alpha = g["cam_alpha"] if self.has_cam else 0
        canvas = self.background_with_shadows(g["screen"], g["cam"], cam_alpha, g["radius"]).copy()

        # screen with zoom
        covered = cam_alpha > 0.99 and cw >= W - 1 and ch >= H - 1
        z = self.zoom.at(t)
        if not covered:
            sh_, sw_ = scr.shape[:2]
            if self.inline_cam and self.grade:  # webcam baked into the screen: grade it in place
                scr = scr.copy()
                x, y, w, h = self.inline_cam
                x0, y0, x1, y1 = int(x * sw_), int(y * sh_), int((x + w) * sw_), int((y + h) * sh_)
                scr[y0:y1, x0:x1] = self.grade.apply(scr[y0:y1, x0:x1])
            live = [r for a, b, r in self.redactions if a <= t < b]
            if live:  # pixelate secrets in source space so they stay hidden through zooms
                scr = scr.copy()
                for rx, ry, rw, rh in live:
                    x0, y0 = int(rx * sw_), int(ry * sh_)
                    x1, y1 = min(sw_, int((rx + rw) * sw_)), min(sh_, int((ry + rh) * sh_))
                    if x1 > x0 and y1 > y0:
                        blk = cv2.resize(scr[y0:y1, x0:x1], (max(1, (x1 - x0) // 24), max(1, (y1 - y0) // 24)), interpolation=cv2.INTER_AREA)
                        scr[y0:y1, x0:x1] = cv2.GaussianBlur(cv2.resize(blk, (x1 - x0, y1 - y0), interpolation=cv2.INTER_NEAREST), (0, 0), 3)
            img = C.warp_crop(scr, (z[0] * sw_, z[1] * sh_, z[2] * sw_, z[3] * sh_), int(round(sw)), int(round(sh)))
            if self.frame_kind == "macos":
                FX.macos_chrome(canvas, (sx, sy, sw, sh), self.radius, self.dark)
            C.paste_rounded(canvas, img, int(round(sx)), int(round(sy)), self.radius)
            self.draw_annotations(canvas, t, (sx, sy, sw, sh), z)

            # spotlight callouts with a rect
            for a, b, c in self.callouts:
                if c.get("rect") and a <= t < b:
                    q = min(1, (t - a) / 0.3, (b - t) / 0.3)
                    rx, ry, rw, rh = c["rect"]
                    hole = (sx + (rx - z[0]) / z[2] * sw, sy + (ry - z[1]) / z[3] * sh, rw / z[2] * sw, rh / z[3] * sh)
                    C.spotlight(canvas, (sx, sy, sw, sh), hole, self.accent, C.ease(q))

        # Insert: full cutaway, split panel, or transparent overlay
        if ins is not None:
            canvas = self.draw_insert(canvas, ins, t, pin, pout)
            if ins["mode"] == "full" and cw >= W - 1 and ch >= H - 1:
                cam_alpha = 0  # a full-frame camera never hides a full Insert
            elif ins["mode"] == "full" and cw < W * 0.5:
                # shrink the bubble into its corner so it doesn't sit on the diagram
                q = 1 - 0.38 * C.ease(pin) * (1 - C.ease(pout))
                ax = cx + cw if cx + cw / 2 > W / 2 else cx
                ay = cy + ch if cy + ch / 2 > H / 2 else cy
                nw, nh = cw * q, ch * q
                cx = ax - nw if ax > cx else ax
                cy = ay - nh if ay > cy else ay
                cw, ch = nw, nh
                g = dict(g, radius=g["radius"] * q)

        # camera
        if cam_alpha > 0.01 and cw > 4:
            asp = cw / ch
            frame_now = g["cam_frame"]
            crop = C.cam_crop(cam.shape, asp, self.look, frame_now)
            if p < 1.0:
                crop_prev = C.cam_crop(cam.shape, asp, self.look, prev_g["cam_frame"])
                crop = C.lerp(crop_prev, crop, p)
            img = C.warp_crop(cam, crop, int(round(cw)), int(round(ch)))
            if self.grade:
                img = self.grade.apply(img)
            r = g["radius"]
            ring = max(2, int(H / 270)) if r > 0 and cw < W * 0.9 else 0
            if ring:
                accent = np.full((int(round(ch)) + 2 * ring, int(round(cw)) + 2 * ring, 3), C.hex_bgr(self.accent), np.uint8)
                C.blend_into(canvas, accent, int(round(cx)) - ring, int(round(cy)) - ring,
                             C.rounded_mask(accent.shape[1], accent.shape[0], int(r + ring)), cam_alpha)
            C.blend_into(canvas, img, int(round(cx)), int(round(cy)),
                         C.rounded_mask(img.shape[1], img.shape[0], int(r)) if r > 0 else None, cam_alpha)

        # title cards dim + blur what's behind them
        for a, b, _ in self.titles:
            if a <= t < b:
                q = C.ease(min(1, (t - a) / 0.25, (b - t) / 0.3))
                canvas = cv2.convertScaleAbs(C.soft_blur(canvas, 0.85 * q), alpha=1 - 0.45 * q)

        # chapter: Look chapter card (black frame) or punch-in
        for a, _, _ in self.chapters:
            if self.card:
                d = self.card.get("duration", 2.0)
                if a <= t < a + d:
                    q = min(1.0, (t - a) / 0.16, (a + d - t) / 0.2)
                    canvas = cv2.addWeighted(np.full_like(canvas, C.hex_bgr(self.card.get("bg", "#000000"))), q, canvas, 1 - q, 0)
            elif a <= t < a + 0.45:
                canvas = C.punch(canvas, 0.045 * math.sin(math.pi * (t - a) / 0.45))

        if t < 0.35:  # fade up from black
            canvas = cv2.convertScaleAbs(canvas, alpha=t / 0.35)
        return canvas

    def draw_annotations(self, canvas, t, box, z):
        sc = self.scale
        for a, b, ann in self.annotations:
            if not a <= t < b:
                continue
            age = t - a
            fade = min(1.0, (b - t) / 0.25)
            col = ann.get("color", self.ann_color)
            kind = ann.get("type", "box")
            layer = canvas.copy() if fade < 1 else canvas
            if kind == "box" and ann.get("rect"):
                rx, ry, rw, rh = ann["rect"]
                x0, y0 = self.to_canvas(rx, ry, box, z)
                x1, y1 = self.to_canvas(rx + rw, ry + rh, box, z)
                FX.marching_box(layer, (x0, y0, x1 - x0, y1 - y0), col, age, sc, min(1.0, age / 0.4))
                if ann.get("label"):
                    self.box_label(layer, ann["label"], x0, y0, x1, y1, box)
            elif kind == "arrow" and ann.get("to"):
                p1 = self.to_canvas(*ann["to"], box, z)
                p0 = self.to_canvas(*ann["from"], box, z) if ann.get("from") else (p1[0] - 220 * sc, p1[1] - 140 * sc)
                FX.curved_arrow(layer, p0, p1, col, sc, min(1.0, age / 0.45))
                if ann.get("label"):
                    FX.pill_label(layer, p0[0], p0[1] - 28 * sc, ann["label"], sc, **self._pill())
            elif kind == "chevron" and ann.get("at"):
                x, y = self.to_canvas(*ann["at"], box, z)
                FX.chevrons(layer, x, y, col, sc, age, ann.get("dir", "right"))
            elif kind == "pill" and ann.get("at"):
                x, y = self.to_canvas(*ann["at"], box, z)
                FX.pill_label(layer, x, y, ann.get("text", ""), sc, arrows=ann.get("arrows", False), **self._pill())
            elif kind == "pointer" and ann.get("at"):
                x, y = self.to_canvas(*ann["at"], box, z)
                FX.click_effect(layer, "red_arrow", x, y, min(age, 1.0), sc, accent=ann.get("color", "#FF2A2A"))
            if layer is not canvas:
                cv2.addWeighted(layer, fade, canvas, 1 - fade, 0, canvas)
        for ct, x, y in self.clicks:
            if ct <= t < ct + 1.2:
                cx, cy = self.to_canvas(x, y, box, z)
                FX.click_effect(canvas, self.click_kind, cx, cy, t - ct, sc, self.ann_color)

    def box_label(self, layer, text, x0, y0, x1, y1, box):
        """Label pill in the Look accent, beside the box (right, else left, else above)."""
        sc = self.scale * 1.25
        img = FX.text_image(text, max(14, int(26 * sc)), "#0B0B0F" if self.dark else "#FFFFFF",
                            self.accent, pad=max(8, int(12 * sc)))
        w, h = img.shape[1], img.shape[0]
        gap = int(16 * sc)
        sx, sy, sw, sh = box
        cy = int((y0 + y1) / 2 - h / 2)
        if x1 + gap + w < sx + sw:
            x = int(x1 + gap)
        elif x0 - gap - w > sx:
            x = int(x0 - gap - w)
        else:
            x, cy = int((x0 + x1) / 2 - w / 2), int(y0 - gap - h)
        FX.paste_bgra(layer, img, x, cy)

    def _pill(self):
        return {"bg": self.badge.get("bg", "#1E1E1E"), "fg": self.badge.get("fg", "#FFFFFF")}

    def draw_insert(self, canvas, ins, t, pin, pout):
        fps = ins.get("fps", 30)
        x, y, w, h = ins["px"]
        img = FX.insert_frame(ins["frames"], int((t - ins["out_start"]) * fps), ins["n"], w, h)
        if img is None:
            return canvas
        if ins["mode"] == "full":
            body = img[..., :3] if img.shape[2] == 4 else img
            if body.shape[:2] != canvas.shape[:2]:
                # Insert laid out above the caption band: extend its own background down
                full = np.empty_like(canvas)
                full[:] = body[2, 2]
                full[y:y + body.shape[0], x:x + body.shape[1]] = body[: canvas.shape[0] - y, : canvas.shape[1] - x]
            else:
                full = body
            if pin < 1:
                return FX.transition(canvas, full, pin, ins["tkind"], self.trans_colors)
            if pout > 0:
                return FX.transition(full, canvas, pout, ins["tkind"], self.trans_colors)
            return full.copy()
        alpha = C.ease(pin) * (1 - C.ease(pout))
        if ins["mode"] == "split":
            body = img[..., :3] if img.shape[2] == 4 else img
            r = int(self.radius)
            C.blend_into(canvas, body, x, y, C.rounded_mask(w, h, r), alpha)
            return canvas
        # overlay: transparent Insert on a glass backdrop, slight scale pop on entry
        if img.shape[2] == 3:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
        if ins.get("backdrop", True):
            pad = int(10 * self.scale)
            bx, by, bw, bh = x - pad, y - pad, w + 2 * pad, h + 2 * pad
            roi = canvas[max(0, by):by + bh, max(0, bx):bx + bw]
            if roi.size:
                glass = cv2.GaussianBlur(roi, (0, 0), 18)
                tint = np.full_like(glass, (14, 12, 12) if self.dark else (250, 250, 250))
                glass = cv2.addWeighted(glass, 0.25, tint, 0.75, 0)
                C.blend_into(canvas, glass, max(0, bx), max(0, by),
                             C.rounded_mask(glass.shape[1], glass.shape[0], int(18 * self.scale)), alpha * 0.92)
        if pin < 1:
            s = 0.92 + 0.08 * C.ease(pin)
            img = cv2.resize(img, (max(2, int(w * s)), max(2, int(h * s))))
            x, y = x + (w - img.shape[1]) // 2, y + (h - img.shape[0]) // 2
        FX.paste_bgra(canvas, img, x, y, alpha)
        return canvas

    # -- text layer
    def write_ass(self, path, words):
        W, H, fmt, acc = self.W, self.H, self.fmt, self.accent
        st = self.edl.get("style", {})
        lines = O.header(W, H, fmt, st.get("font", "Inter"), acc)
        cap = st.get("captions", {})
        if cap.get("enabled", True) and words:
            words = O.apply_caption_edits(words, self.edl.get("caption_edits", []))
            boxed = []  # full Inserts leave a caption band, so captions stay unboxed
            lines += O.caption_events(O.apply_glossary(words, self.edl.get("glossary", {})), self.tl, cap, W, H, fmt, acc,
                                      boxed=boxed)
        for a, b, t in self.titles:
            lines += O.title_events(a, b - a, t["text"], t.get("sub", ""), W, H, fmt, acc)
        for a, i, c in self.chapters:
            if self.card:
                lines += O.chapter_card_events(a, c["text"], W, H, self.card)
            else:
                lines += O.chapter_events(a, i, c["text"], W, H, fmt, acc)
        lines += O.shortcut_events(self.edl.get("shortcuts", []), self.tl, W, H, fmt, self.badge)
        for a, b, c in self.callouts:
            if c.get("text"):
                lines += O.callout_events(a, b - a, c["text"], W, H, fmt)
        lines += O.speed_events(self.tl, W, H, fmt)
        badge = st.get("badge")
        if badge:
            mode = st.get("badge_mode", "intro")
            spans = [(0.4, self.tl.duration)] if mode == "always" else [(0.4, min(6.0, self.tl.duration))]
            lines += O.brand_events(badge, spans, W, H, fmt, acc)
        o = self.edl.get("outro") or {}
        if self.outro:
            lines += O.outro_events(self.tl.duration, self.outro, o["text"], o.get("sub", ""), W, H, fmt, acc)
        Path(path).write_text("\n".join(lines) + "\n")


_EDITOR = None  # set before the worker pool forks; each worker inherits a copy


def _worker_init():
    cv2.setNumThreads(1)  # one process per core already; nested OpenCV threads just thrash


def _compose(t, scr, cam):
    return _EDITOR.frame(t, scr, cam).tobytes()


def ass_filter(path, shift=0.0, scale=None):
    p = str(path).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    fd = str(FONTS_DIR).replace(":", "\\:")
    pre = f"setpts=PTS+{shift:.4f}/TB," if shift else ""
    post = ",setpts=PTS-STARTPTS" if shift else ""
    return f"{pre}ass='{p}':fontsdir='{fd}'{post}"


def sound_design(edl, tl, ed, work, rdir, t0_out, fade_out, gain, voice):
    """Voice master + synthesized SFX + optional music bed ducked under the voice."""
    from . import sfx as SFX
    from .looks import load_look
    sound = edl.get("sound", {"sfx": True, "music": False})
    inputs = ["-ss", f"{t0_out:.3f}", "-i", str(voice)]
    chain = [f"[1:a]volume={gain:.2f}dB,alimiter=limit=0.84:level=false,apad[voice]"]
    mix = ["[voice]"]
    try:
        look = load_look(edl.get("look") or "architecture-flow")
    except SystemExit:
        look = {"sfx": {}, "music": "ambient-pad"}
    k = 2
    if sound.get("sfx", True):
        manifest = load_manifest(work)
        specs = {}
        for ins in manifest.get("inserts", []):
            try:
                specs[ins["id"]] = load_json(ins["spec"])
            except Exception:
                pass
        cues = SFX.collect_cues(edl, tl, look, manifest, specs)
        if cues:
            wav = rdir / "sfx.wav"
            SFX.build_sfx_track(cues, ed.total, wav)
            inputs += ["-ss", f"{t0_out:.3f}", "-i", str(wav)]
            chain.append(f"[{k}:a]aresample=48000,apad[sfx]")
            mix.append("[sfx]")
            k += 1
    if sound.get("music"):
        style = sound.get("music") if isinstance(sound.get("music"), str) else look.get("music", "ambient-pad")
        wav = rdir / f"music_{style}.wav"
        SFX.build_music(style, ed.total, wav)
        inputs += ["-ss", f"{t0_out:.3f}", "-i", str(wav)]
        chain[0] = chain[0].replace("[voice]", "[voice0]")
        chain.append("[voice0]asplit=2[voice][vkey]")
        level = float(sound.get("music_db", -20))
        chain.append(f"[{k}:a]aresample=48000,volume={level}dB,apad[mus0]")
        chain.append("[mus0][vkey]sidechaincompress=threshold=0.02:ratio=10:attack=15:release=450[mus]")
        mix.append("[mus]")
    if len(mix) > 1:
        chain.append(f"{''.join(mix)}amix=inputs={len(mix)}:normalize=0:duration=first,alimiter=limit=0.89:level=false,"
                     f"afade=t=out:st={fade_out:.3f}:d=0.6[aout]")
    else:
        chain.append(f"[voice]afade=t=out:st={fade_out:.3f}:d=0.6[aout]")
    return inputs, ";".join(chain)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("edl")
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--range", type=float, nargs=2, metavar=("SRC_START", "SRC_END"))
    ap.add_argument("--still", type=float, nargs="+", metavar="SRC_T")
    ap.add_argument("--force-cut", action="store_true")
    ap.add_argument("--workers", type=int, default=4, help="compositor processes (1 = no parallelism)")
    args = ap.parse_args(argv)

    edl_path = Path(args.edl).resolve()
    edl = load_json(edl_path)
    work = edl_path.parent
    rdir = work / "render"
    rdir.mkdir(exist_ok=True)
    out_cfg = edl.get("output", {})
    fps = out_cfg.get("fps", 30)
    fmt = out_cfg.get("format", "landscape")
    scr_info = probe(edl["inputs"]["screen"])
    tl = Timeline(edl["segments"], fps, scr_info["duration"])
    analysis = load_json(work / "analysis.json") if (work / "analysis.json").exists() else {}
    look = analysis.get("camera_look")
    words = []
    if (work / "transcript.json").exists():
        words = [w for s in load_json(work / "transcript.json")["segments"] for w in s["words"]]

    print(f"timeline: {len(tl.segments)} segments, {scr_info['duration']:.1f}s raw -> {tl.duration:.1f}s (+outro)")
    cut = pass1(edl, tl, fps, rdir, look, args.force_cut)
    has_cam = bool(cut["camera"])

    preview = args.preview or args.range is not None
    W, H = (1920, 1080) if fmt == "landscape" else (1080, 1920)
    if preview or args.still:
        W, H = W // 2, H // 2
    if args.still:
        W, H = W * 2, H * 2  # stills at full res for crisp review
    ed = Editor(edl, tl, W, H, fmt, look, has_cam, probe(cut["screen"])["video"], work=work)
    ass = rdir / f"text_{W}x{H}.ass"
    ed.write_ass(ass, words)
    scr_w = min(probe(cut["screen"])["video"]["width"], MAX_SCREEN_W if not preview else 1600)

    if args.still:
        for st in args.still:
            t = tl.to_out(st)
            sr, cr = Reader(cut["screen"], t, scr_w), (Reader(cut["camera"], t) if has_cam else None)
            img = ed.frame(t, sr.read(), cr.read() if cr else np.zeros((CAM_H, 1280, 3), np.uint8))
            sr.close(); cr and cr.close()
            raw = rdir / f"still_raw_{st:.2f}.png"
            out = work / "stills" / f"still_{st:08.2f}.png"
            out.parent.mkdir(exist_ok=True)
            cv2.imwrite(str(raw), img)
            run([FFMPEG, "-y", "-v", "error", "-i", str(raw), "-vf", ass_filter(ass, t), "-frames:v", "1", str(out)])
            raw.unlink()
            print(out)
        return

    t0_out, t1_out = 0.0, ed.total
    if args.range:
        t0_out, t1_out = tl.to_out(args.range[0]), min(ed.total, tl.to_out(args.range[1], "prev"))
    n_frames = int(round((t1_out - t0_out) * fps))
    final = Path(out_cfg.get("path", work / "final.mp4"))
    if preview:
        final = final.with_name(final.stem + ("_preview" if not args.range else f"_{args.range[0]:.0f}-{args.range[1]:.0f}") + final.suffix)
    final.parent.mkdir(parents=True, exist_ok=True)
    fade_out = max(0.0, t1_out - t0_out - 0.6)
    audio_in, afilter = sound_design(edl, tl, ed, work, rdir, t0_out, fade_out, loudness_gain(rdir, cut["audio"]), cut["audio"])
    enc = [FFMPEG, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
           *audio_in,
           "-vf", ass_filter(ass, t0_out), "-filter_complex", afilter,
           "-map", "0:v", "-map", "[aout]", "-t", f"{t1_out - t0_out:.3f}",
           "-c:v", "libx264", "-preset", "veryfast" if preview else "faster", "-crf", "24" if preview else "17",
           "-profile:v", "high", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(final)]
    encp = subprocess.Popen(enc, stdin=subprocess.PIPE)
    sr = Reader(cut["screen"], t0_out, scr_w)
    cr = Reader(cut["camera"], t0_out, None if not preview else 640) if has_cam else None
    blank = np.zeros((CAM_H, 1280, 3), np.uint8)
    print(f"pass 2: compositing {n_frames} frames at {W}x{H} -> {final}", flush=True)
    t0 = time.time()
    # frames are independent: composite them on several cores, keep at most
    # `depth` in flight so memory stays flat, write them back in order
    global _EDITOR
    _EDITOR = ed
    workers = max(1, min(args.workers, (os.cpu_count() or 2) - 1))
    depth = workers * 3
    pool = mp.get_context("fork").Pool(workers, _worker_init) if workers > 1 else None
    pending = collections.deque()

    def emit(res):
        encp.stdin.write(res.get() if pool else res)

    try:
        for i in range(n_frames):
            t = t0_out + i / fps
            job = (t, sr.read(), cr.read() if cr else blank)
            pending.append(pool.apply_async(_compose, job) if pool else _compose(*job))
            if len(pending) >= depth:
                emit(pending.popleft())
            if i and i % (fps * 10) == 0:
                el = time.time() - t0
                print(f"  {t:7.1f}s / {t1_out:.1f}s   {i / el:5.1f} fps   eta {el / i * (n_frames - i):5.0f}s", flush=True)
        while pending:
            emit(pending.popleft())
    finally:
        if pool:
            pool.terminate()
        encp.stdin.close()
        encp.wait()
        sr.close()
        cr and cr.close()
    if encp.returncode:
        sys.exit("encoder failed")
    print(f"done in {time.time() - t0:.0f}s -> {final}")


if __name__ == "__main__":
    main()
