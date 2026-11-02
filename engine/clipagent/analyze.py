"""Analyze raw footage so the edit can be planned from data, not guesses.

- probes every input (resolution, fps, duration, audio)
- screen activity: every 0.5s, how much of the screen changed and where
  (normalized bbox) -> tells Claude where the action is for zooms, and which
  silent stretches are "typing/doing" (speed up) vs dead air (cut)
- camera sync: offset between screen and camera files via audio envelope
  cross-correlation (only when both have audio)
- camera look: average brightness / color cast / face position, used by the
  renderer's auto grade

usage: uv run analyze.py WORKDIR --screen S.mp4 [--camera C.mp4] [--camera-rect x,y,w,h]
writes WORKDIR/analysis.json
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

from .common import FFMPEG, probe, save_json


def frames(path, fps, width, gray=True, start=0.0, dur=None, crop=None):
    """Yield (t, frame) decoded by ffmpeg at a fixed fps and width."""
    info = probe(path)["video"]
    vf = []
    if crop:
        x, y, w, h = crop
        vf.append(f"crop=iw*{w}:ih*{h}:iw*{x}:ih*{y}")
    vf += [f"fps={fps}", f"scale={width}:-2"]
    cw, ch = (info["width"] * (crop[2] if crop else 1), info["height"] * (crop[3] if crop else 1))
    height = int(round(width * ch / cw / 2) * 2)
    pix, chans = ("gray", 1) if gray else ("bgr24", 3)
    cmd = [FFMPEG, "-v", "error", "-ss", str(start), *(["-t", str(dur)] if dur else []), "-i", str(path),
           "-vf", ",".join(vf), "-f", "rawvideo", "-pix_fmt", pix, "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    n, size = 0, width * height * chans
    while True:
        buf = p.stdout.read(size)
        if len(buf) < size:
            break
        f = np.frombuffer(buf, np.uint8).reshape(height, width, chans) if chans > 1 else np.frombuffer(buf, np.uint8).reshape(height, width)
        yield start + n / fps, f
        n += 1
    p.wait()


def screen_activity(path, step=0.5, width=480):
    out, prev = [], None
    for t, f in frames(path, 1 / step, width):
        if prev is not None:
            diff = cv2.absdiff(f, prev) > 14
            frac = float(diff.mean())
            box = None
            if frac > 0.0005:
                h, w = diff.shape
                rows = np.where(diff.sum(1) > 1)[0]
                cols = np.where(diff.sum(0) > 1)[0]
                if len(rows) and len(cols):
                    # trim 2% outliers on each side (blinking cursors, clocks in a corner)
                    r0, r1 = np.percentile(rows, [2, 98])
                    c0, c1 = np.percentile(cols, [2, 98])
                    box = [round(c0 / w, 3), round(r0 / h, 3), round((c1 - c0 + 1) / w, 3), round((r1 - r0 + 1) / h, 3)]
            out.append({"t": round(t, 2), "change": round(frac, 4), "box": box})
        prev = f
    return out


def audio_envelope(path, seconds=240, rate=200):
    cmd = [FFMPEG, "-v", "error", "-t", str(seconds), "-i", str(path), "-vn", "-ac", "1", "-ar", "8000",
           "-f", "s16le", "-"]
    raw = subprocess.run(cmd, capture_output=True).stdout
    a = np.frombuffer(raw, np.int16).astype(np.float32)
    if len(a) < 8000:
        return None
    hop = 8000 // rate
    env = np.abs(a[: len(a) // hop * hop]).reshape(-1, hop).mean(1)
    env = np.log1p(env)
    return (env - env.mean()) / (env.std() + 1e-6)


def sync_offset(screen, camera, rate=200):
    a, b = audio_envelope(screen, rate=rate), audio_envelope(camera, rate=rate)
    if a is None or b is None:
        return None
    n = 1 << int(np.ceil(np.log2(len(a) + len(b))))
    r = np.fft.irfft(np.fft.rfft(a, n) * np.conj(np.fft.rfft(b, n)), n)
    k = int(np.argmax(r))
    conf = float((r[k] - r.mean()) / (r.std() + 1e-9))
    if k > n // 2:
        k -= n
    # r[k] peaks where screen[t + k] matches camera[t]  =>  camera_time = screen_time - k
    return {"camera_offset": round(-k / rate, 3), "confidence": round(conf, 1)}


def voice_stats(path):
    """Noise floor vs. speech level of a file's audio, to pick the mic and how
    hard to denoise. Levels in dBFS over 50 ms windows."""
    cmd = [FFMPEG, "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"]
    a = np.frombuffer(subprocess.run(cmd, capture_output=True).stdout, np.int16).astype(np.float32) / 32768
    if len(a) < 16000:
        return None
    win = a[: len(a) // 800 * 800].reshape(-1, 800)
    db = 20 * np.log10(np.sqrt((win ** 2).mean(1)) + 1e-9)
    noise, speech = float(np.percentile(db, 10)), float(np.percentile(db, 95))
    snr = speech - noise
    return {"noise_db": round(noise, 1), "speech_db": round(speech, 1), "snr_db": round(snr, 1),
            "clipping": round(float((np.abs(a) > 0.99).mean()), 5),
            "denoise": "light" if snr > 38 else "normal" if snr > 24 else "strong"}


def camera_look(path, crop=None, samples=12):
    info = probe(path)
    dur = info["duration"] or 10
    faces = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    lum, bgr, centers, sizes, sharp, noise = [], [], [], [], [], []
    for i in range(samples):
        t = dur * (i + 0.5) / samples
        for _, f in frames(path, 1, 640, gray=False, start=t, dur=1.0, crop=crop):
            yuv = cv2.cvtColor(f, cv2.COLOR_BGR2YCrCb)
            lum.append(float(yuv[..., 0].mean()))
            bgr.append(f.reshape(-1, 3).mean(0))
            g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
            sharp.append(float(cv2.Laplacian(g, cv2.CV_64F).var()))
            # noise: high-frequency energy left after a median filter, on flat areas
            resid = cv2.absdiff(g, cv2.medianBlur(g, 3)).astype(np.float32)
            flat = cv2.Laplacian(cv2.GaussianBlur(g, (5, 5), 0), cv2.CV_64F) ** 2 < 25
            noise.append(float(resid[flat].mean()) if flat.any() else float(resid.mean()))
            det = faces.detectMultiScale(g, 1.1, 5, minSize=(60, 60))
            if len(det):
                x, y, w, h = max(det, key=lambda d: d[2] * d[3])
                centers.append(((x + w / 2) / f.shape[1], (y + h / 2) / f.shape[0]))
                sizes.append(h / f.shape[0])
            break
    b, g, r = np.mean(bgr, 0)
    look = {"luma": round(float(np.mean(lum)), 1), "rgb_mean": [round(float(r), 1), round(float(g), 1), round(float(b), 1)]}
    look["quality"] = camera_quality(float(np.median(sharp)) if sharp else 0.0,
                                     float(np.median(noise)) if noise else 0.0, look["luma"], bool(centers))
    if centers:
        cx, cy = np.median(centers, 0)
        look["face_center"] = [round(float(cx), 3), round(float(cy), 3)]
        look["face_height"] = round(float(np.median(sizes)), 3)
    return look


def camera_quality(sharpness, noise, luma, face_found):
    """Score a camera 0-100 from sharpness (Laplacian variance at 640px), residual
    noise and exposure. "good" cameras may fill the frame; "poor" ones stay a small
    bubble (Camera Source quality rule)."""
    s_sharp = min(1.0, sharpness / 180.0)
    s_noise = max(0.0, 1.0 - max(0.0, noise - 1.2) / 3.0)
    s_light = max(0.0, 1.0 - abs(luma - 118) / 90.0)
    score = round(100 * (0.45 * s_sharp + 0.30 * s_noise + 0.25 * s_light) * (1.0 if face_found else 0.85))
    return {"score": score, "rating": "good" if score >= 60 else "fair" if score >= 40 else "poor",
            "sharpness": round(sharpness, 1), "noise": round(noise, 2)}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("workdir")
    ap.add_argument("--screen", required=True)
    ap.add_argument("--camera")
    ap.add_argument("--camera-rect", help="x,y,w,h (0-1) of a webcam baked into the screen recording")
    args = ap.parse_args(argv)

    res = {"screen": probe(args.screen)}
    print("probing + scanning screen activity...", flush=True)
    res["activity"] = screen_activity(args.screen)
    print("measuring voice quality...", flush=True)
    res["voice"] = {}
    if res["screen"]["audio"]:
        res["voice"]["screen"] = voice_stats(args.screen)
    if args.camera:
        res["camera"] = probe(args.camera)
        if res["camera"]["audio"]:
            res["voice"]["camera"] = voice_stats(args.camera)
        if res["screen"]["audio"] and res["camera"]["audio"]:
            print("syncing camera to screen by audio...", flush=True)
            res["sync"] = sync_offset(args.screen, args.camera)
        print("measuring camera look...", flush=True)
        res["camera_look"] = camera_look(args.camera)
    elif args.camera_rect:
        rect = [float(v) for v in args.camera_rect.split(",")]
        res["camera_look"] = camera_look(args.screen, crop=rect)

    save_json(res, Path(args.workdir) / "analysis.json")
    s = res["screen"]
    print(f"screen: {s['video']['width']}x{s['video']['height']} @ {s['video']['fps']}fps, {s['duration']:.1f}s, audio={'yes' if s['audio'] else 'no'}")
    for src, v in res["voice"].items():
        if v:
            print(f"voice ({src}): speech {v['speech_db']} dB, noise floor {v['noise_db']} dB, SNR {v['snr_db']} dB "
                  f"-> denoise '{v['denoise']}'" + (f", CLIPPING {v['clipping']:.2%}" if v["clipping"] > 0.0005 else ""))
    if "sync" in res:
        print(f"camera sync: {res['sync']}  (confidence < 8 means: verify by eye)")
    if "camera_look" in res:
        print(f"camera look: {res['camera_look']}")
    print(f"wrote {Path(args.workdir) / 'analysis.json'}")


if __name__ == "__main__":
    main()
