"""Grab frames from the raw screen recording so Claude can *look* at it.

Each image gets a labeled 0-1 coordinate grid, so zoom/callout rects can be
read straight off the picture as [x, y, w, h].

usage:
  uv run frames.py VIDEO OUTDIR --at 12.5 40 73.2        # specific source times
  uv run frames.py VIDEO OUTDIR --every 30               # contact sheets, one frame per 30s
  uv run frames.py VIDEO OUTDIR --at 40 --rect 0.1,0.2,0.4,0.3   # preview a zoom rect
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

from .common import FFMPEG, probe

WIDTH = 1280


def grab_img(video, t, width=WIDTH):
    out = subprocess.run([FFMPEG, "-v", "error", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1",
                          "-vf", f"scale={width}:-2", "-f", "image2pipe", "-vcodec", "png", "-"],
                         capture_output=True).stdout
    if not out:
        return None
    return cv2.imdecode(np.frombuffer(out, np.uint8), cv2.IMREAD_COLOR)


def draw_grid(img, label):
    h, w = img.shape[:2]
    over = img.copy()
    for i in range(1, 10):
        x, y = int(w * i / 10), int(h * i / 10)
        cv2.line(over, (x, 0), (x, h), (0, 255, 255), 1)
        cv2.line(over, (0, y), (w, y), (0, 255, 255), 1)
    img = cv2.addWeighted(over, 0.35, img, 0.65, 0)
    for i in range(1, 10):
        x, y = int(w * i / 10), int(h * i / 10)
        for (px, py, txt) in ((x + 3, 16, f".{i}"), (3, y - 4, f".{i}")):
            cv2.putText(img, txt, (px, py), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 3, cv2.LINE_AA)
            cv2.putText(img, txt, (px, py), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1, cv2.LINE_AA)
    cv2.rectangle(img, (w - 150, h - 30), (w, h), (0, 0, 0), -1)
    cv2.putText(img, label, (w - 144, h - 9), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
    return img


def draw_rect(img, rect):
    h, w = img.shape[:2]
    x, y, rw, rh = rect
    cv2.rectangle(img, (int(x * w), int(y * h)), (int((x + rw) * w), int((y + rh) * h)), (87, 119, 217), 3)
    return img


def fmt(t):
    return f"{int(t // 60):02d}m{t % 60:04.1f}s"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("outdir")
    ap.add_argument("--at", type=float, nargs="*")
    ap.add_argument("--every", type=float)
    ap.add_argument("--rect", help="x,y,w,h to outline (0-1)")
    args = ap.parse_args(argv)
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    rect = [float(v) for v in args.rect.split(",")] if args.rect else None

    if args.at:
        for t in args.at:
            img = grab_img(args.video, t)
            if img is None:
                print(f"no frame at {t}")
                continue
            if rect:
                img = draw_rect(img, rect)
            p = out / f"frame_{t:08.2f}.png"
            cv2.imwrite(str(p), draw_grid(img, fmt(t)))
            print(p)
    elif args.every:
        dur = probe(args.video)["duration"]
        times = list(np.arange(args.every / 2, dur, args.every))
        tiles = [draw_grid(i, fmt(t)) for t in times if (i := grab_img(args.video, t, 640)) is not None]
        for k in range(0, len(tiles), 6):  # 3x2 sheets, each tile 640 wide
            chunk = tiles[k:k + 6]
            while len(chunk) < 6:
                chunk.append(np.zeros_like(tiles[0]))
            sheet = np.vstack([np.hstack(chunk[r * 3:r * 3 + 3]) for r in range(2)])
            p = out / f"sheet_{k // 6:02d}.png"
            cv2.imwrite(str(p), sheet)
            print(p)


if __name__ == "__main__":
    main()
