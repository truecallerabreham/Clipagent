"""Look screen treatment drawn by the compositor: window chrome, click effects,
annotations (marching ants, dashed arrows, chevrons, pill labels), Insert
compositing and the transitions into and out of Inserts."""
from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

from .compose import blend_into, ease, hex_bgr, rounded_mask

FONT_DIR = Path(__file__).resolve().parent / "assets" / "fonts"


# ---------------------------------------------------------------- text (Pillow, Inter)

@lru_cache(maxsize=256)
def text_image(text: str, size: int, fg: str, bg: str | None, pad: int = 0, weight: str = "SemiBold", radius: int = 0):
    """BGRA image of `text` in Inter, optionally on a rounded pill."""
    from PIL import Image, ImageDraw, ImageFont
    font = ImageFont.truetype(str(FONT_DIR / f"Inter-{weight}.ttf"), size)
    x0, y0, x1, y1 = font.getbbox(text)
    w, h = x1 - x0 + 2 * pad, int(size * 1.25) + 2 * pad
    im = Image.new("RGBA", (max(2, w), max(2, h)), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if bg:
        d.rounded_rectangle([0, 0, w - 1, h - 1], radius=radius or h // 2, fill=_rgba(bg))
    d.text((pad - x0, pad + (int(size * 1.25) - (y1 + y0)) // 2), text, font=font, fill=_rgba(fg))
    a = np.array(im)
    return cv2.cvtColor(a, cv2.COLOR_RGBA2BGRA)


def _rgba(h):
    h = h.lstrip("#")
    if len(h) == 6:
        h += "FF"
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4, 6))


def paste_bgra(canvas, img, x, y, alpha=1.0):
    h, w = img.shape[:2]
    H, W = canvas.shape[:2]
    x0, y0, x1, y1 = max(0, x), max(0, y), min(W, x + w), min(H, y + h)
    if x1 <= x0 or y1 <= y0:
        return
    src = img[y0 - y:y1 - y, x0 - x:x1 - x]
    a = (src[..., 3:4].astype(np.float32) / 255.0) * alpha
    roi = canvas[y0:y1, x0:x1]
    roi[:] = (src[..., :3] * a + roi * (1 - a)).astype(np.uint8)


# ---------------------------------------------------------------- window chrome

def macos_chrome(canvas, box, radius, dark=True):
    """Window title bar with traffic lights above the screen box. Returns the bar height."""
    sx, sy, sw, sh = (int(round(v)) for v in box)
    H = canvas.shape[0]
    bar = max(18, int(H * 0.032))
    color = (46, 42, 42) if dark else (236, 236, 236)
    full = np.full((sh + bar, sw, 3), color, np.uint8)
    blend_into(canvas, full, sx, sy - bar, rounded_mask(sw, sh + bar, int(radius)))
    r = max(4, bar // 5)
    for i, c in enumerate(((95, 95, 255), (46, 189, 254), (64, 200, 40))):  # BGR red, yellow, green
        cv2.circle(canvas, (sx + int(bar * 0.6) + i * int(r * 3.2), sy - bar // 2), r, c, -1, cv2.LINE_AA)
    return bar


# ---------------------------------------------------------------- click effects

def click_effect(canvas, kind, x, y, age, scale, color="#FFFFFF", accent="#FF2A2A"):
    """Draw one click effect `age` seconds after the click at canvas (x, y)."""
    if kind == "ripple":
        if age > 0.6:
            return
        p = ease(age / 0.6)
        r = int((8 + 40 * p) * scale)
        over = canvas.copy()
        cv2.circle(over, (int(x), int(y)), r, (190, 190, 190), -1, cv2.LINE_AA)
        a = 0.45 * (1 - p)
        cv2.addWeighted(over, a, canvas, 1 - a, 0, canvas)
        cv2.circle(canvas, (int(x), int(y)), r, (235, 235, 235), max(1, int(2 * scale)), cv2.LINE_AA)
    elif kind == "pointer_hand":
        if age > 0.9:
            return
        bounce = 1.0 - 0.15 * math.sin(math.pi * min(1.0, age / 0.25)) if age < 0.25 else 1.0
        fade = 1.0 if age < 0.6 else 1 - (age - 0.6) / 0.3
        draw_pointer(canvas, x, y, 64 * scale * bounce, fade)
    elif kind == "red_arrow":
        if age > 1.2:
            return
        p = ease(min(1.0, age / 0.2))
        fade = 1.0 if age < 1.0 else 1 - (age - 1.0) / 0.2
        L = 90 * scale
        tail = (x - L * 0.72 * p - 12 * scale, y - L * 0.72 * p - 12 * scale)
        over = canvas.copy()
        cv2.arrowedLine(over, (int(tail[0]), int(tail[1])), (int(x - 6 * scale), int(y - 6 * scale)), hex_bgr(accent),
                        max(3, int(9 * scale)), cv2.LINE_AA, tipLength=0.38)
        cv2.addWeighted(over, fade, canvas, 1 - fade, 0, canvas)
    else:  # glow
        if age > 0.7:
            return
        p = ease(age / 0.7)
        over = canvas.copy()
        cv2.circle(over, (int(x), int(y)), int((10 + 34 * p) * scale), hex_bgr(color), max(2, int(4 * scale)), cv2.LINE_AA)
        cv2.addWeighted(over, 0.8 * (1 - p), canvas, 1 - 0.8 * (1 - p), 0, canvas)


def draw_pointer(canvas, x, y, size, alpha=1.0):
    """Oversized vector pointing hand (index finger at x, y)."""
    s = size / 64.0
    finger = np.array([[0, 0], [7, -2], [10, 4], [10, 22], [12, 22]], np.float32)
    hand = np.array([[-4, 2], [0, -1], [5, 0], [8, 5], [8, 20], [15, 18], [22, 21], [28, 23], [34, 27], [36, 40],
                     [33, 54], [25, 63], [8, 63], [0, 56], [-12, 38], [-14, 30], [-9, 27], [-3, 32], [-4, 2]], np.float32)
    pts = (hand * s + [x, y]).astype(np.int32)
    over = canvas.copy()
    cv2.fillPoly(over, [pts], (255, 255, 255), cv2.LINE_AA)
    cv2.polylines(over, [pts], True, (20, 20, 20), max(2, int(3 * s)), cv2.LINE_AA)
    for k in (0, 1, 2):  # knuckle lines
        cx = x + (14 + k * 7) * s
        cv2.line(over, (int(cx), int(y + 21 * s)), (int(cx), int(y + 30 * s)), (20, 20, 20), max(1, int(2 * s)), cv2.LINE_AA)
    del finger
    cv2.addWeighted(over, alpha, canvas, 1 - alpha, 0, canvas)


# ---------------------------------------------------------------- annotations

def dashed_polyline(canvas, pts, color, thick, dash, gap, offset):
    """Dashed open polyline. Dashes are laid out along the total arc length, so
    they stay continuous around corners; `offset` slides them (marching ants)."""
    period = dash + gap
    acc = 0.0
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        L = math.hypot(x1 - x0, y1 - y0)
        if L <= 0:
            continue
        # dash k covers arc [k*period - offset, k*period - offset + dash]
        k = math.floor((acc + offset) / period) - 1
        while True:
            a = k * period - offset - acc
            if a >= L:
                break
            b = a + dash
            a0, b0 = max(0.0, a), min(L, b)
            if b0 > a0:
                p0 = (x0 + (x1 - x0) * a0 / L, y0 + (y1 - y0) * a0 / L)
                p1 = (x0 + (x1 - x0) * b0 / L, y0 + (y1 - y0) * b0 / L)
                cv2.line(canvas, (int(p0[0]), int(p0[1])), (int(p1[0]), int(p1[1])), color, thick, cv2.LINE_AA)
            k += 1
        acc += L


def marching_box(canvas, rect, color, t, scale, appear=1.0):
    x, y, w, h = rect
    pad = 6 * scale
    x, y, w, h = x - pad, y - pad, w + 2 * pad, h + 2 * pad
    pts = [(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)]
    if appear < 1:  # draw-on: only part of the perimeter
        per = 2 * (w + h) * appear
        out, acc = [pts[0]], 0.0
        for a, b in zip(pts, pts[1:]):
            L = math.hypot(b[0] - a[0], b[1] - a[1])
            if acc + L >= per:
                f = (per - acc) / L
                out.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f))
                break
            out.append(b)
            acc += L
        pts = out
    dashed_polyline(canvas, pts, hex_bgr(color), max(2, int(3 * scale)), 14 * scale, 9 * scale, t * 40 * scale)


def curved_arrow(canvas, p0, p1, color, scale, appear=1.0, dashed=True):
    (x0, y0), (x1, y1) = p0, p1
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    nx, ny = -(y1 - y0), (x1 - x0)
    c = (mx + nx * 0.25, my + ny * 0.25)
    n = 40
    pts = [((1 - u) ** 2 * x0 + 2 * (1 - u) * u * c[0] + u ** 2 * x1, (1 - u) ** 2 * y0 + 2 * (1 - u) * u * c[1] + u ** 2 * y1)
           for u in (i / n * appear for i in range(n + 1))]
    col = hex_bgr(color)
    th = max(2, int(4 * scale))
    if dashed:
        dashed_polyline(canvas, pts, col, th, 16 * scale, 10 * scale, 0)
    else:
        cv2.polylines(canvas, [np.array(pts, np.int32)], False, col, th, cv2.LINE_AA)
    if appear > 0.9:
        (ax, ay), (bx, by) = pts[-3], pts[-1]
        ang = math.atan2(by - ay, bx - ax)
        L = 18 * scale
        for d in (2.6, -2.6):
            cv2.line(canvas, (int(bx), int(by)), (int(bx + L * math.cos(ang + d)), int(by + L * math.sin(ang + d))), col, th, cv2.LINE_AA)


def chevrons(canvas, x, y, color, scale, t, direction="right"):
    col = hex_bgr(color)
    th = max(3, int(5 * scale))
    sgn = 1 if direction in ("right", "down") else -1
    for k in range(3):
        phase = (t * 2.2 - k * 0.22) % 1.0
        a = 0.35 + 0.65 * (1 - abs(phase - 0.5) * 2)
        off = (k * 22 - 44) * scale * sgn
        s = 14 * scale
        if direction in ("right", "left"):
            pts = np.array([[x + off - s * sgn * 0.6, y - s], [x + off + s * sgn * 0.6, y], [x + off - s * sgn * 0.6, y + s]], np.int32)
        else:
            pts = np.array([[x - s, y + off - s * sgn * 0.6], [x, y + off + s * sgn * 0.6], [x + s, y + off - s * sgn * 0.6]], np.int32)
        over = canvas.copy()
        cv2.polylines(over, [pts], False, col, th, cv2.LINE_AA)
        cv2.addWeighted(over, a, canvas, 1 - a, 0, canvas)


def pill_label(canvas, x, y, text, scale, bg="#1E1E1E", fg="#FFFFFF", alpha=1.0, arrows=False):
    label = f"⟷  {text}" if arrows else text
    img = text_image(label, max(12, int(26 * scale)), fg, bg, pad=max(6, int(12 * scale)))
    paste_bgra(canvas, img, int(x - img.shape[1] / 2), int(y - img.shape[0] / 2), alpha)


# ---------------------------------------------------------------- Inserts

@lru_cache(maxsize=8)
def _read_frame(path: str, w: int, h: int):
    img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if img is None:
        return None
    if img.shape[1] != w or img.shape[0] != h:
        img = cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA)
    return img


def insert_frame(frames_dir: str, idx: int, n: int, w: int, h: int):
    idx = max(0, min(idx, n - 1))
    return _read_frame(f"{frames_dir}/{idx + 1:05d}.png", w, h)


def diagonal_wipe(old, new, p, colors, angle=0.32):
    """Angled multi-band color wipe from old to new (p 0 -> 1)."""
    H, W = old.shape[:2]
    xs = np.arange(W, dtype=np.float32)[None, :]
    ys = np.arange(H, dtype=np.float32)[:, None]
    u = (xs + ys * angle) / (W + H * angle)            # 0..1 along the wipe direction
    bands = len(colors)
    span = 1.0 + 0.12 * (bands + 1)
    front = p * span
    out = np.where((u < front - 0.12 * bands)[..., None], new, old).copy()
    for k, c in enumerate(colors):
        lead = front - 0.12 * k
        mask = (u < lead) & (u >= lead - 0.12)
        out[mask] = hex_bgr(c)
    return out


def radial_zoom_blur(old, new, p):
    """0.25 s radial zoom-blur bridge (tab switches in the stickman Look)."""
    src = old if p < 0.5 else new
    q = 1 - abs(p - 0.5) * 2                                 # 0 -> 1 -> 0
    H, W = src.shape[:2]
    acc = src.astype(np.float32)
    n = 6
    for i in range(1, n):
        z = 1 + 0.06 * q * i
        M = cv2.getRotationMatrix2D((W / 2, H / 2), 0, z)
        acc += cv2.warpAffine(src, M, (W, H), borderMode=cv2.BORDER_REFLECT)
    return (acc / n).astype(np.uint8)


def transition(old, new, p, kind, colors):
    p = min(1.0, max(0.0, p))
    if kind == "cut" or p >= 1:
        return new if p >= 0.5 or kind != "cut" else old
    if kind == "diagonal_wipe":
        return diagonal_wipe(old, new, ease(p), colors or ["#5E17EB", "#111111", "#FFFFFF"])
    if kind == "radial_blur":
        return radial_zoom_blur(old, new, p)
    return cv2.addWeighted(new, ease(p), old, 1 - ease(p), 0)


TRANSITION_T = {"diagonal_wipe": 0.4, "radial_blur": 0.25, "crossfade": 0.35, "cut": 0.0}
