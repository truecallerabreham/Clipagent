"""Per-frame compositor: background, inset screen with rounded corners and
shadow, smooth zoom/pan, camera bubble with layout transitions, spotlight
callouts, title dimming, chapter punch-ins, fades. Pure numpy/OpenCV; all
geometry is in canvas pixels derived from fractions, so it works at any size."""
import math
from functools import lru_cache

import cv2
import numpy as np

FULL = (0.0, 0.0, 1.0, 1.0)
ZOOM_T = 0.75      # seconds to ease into / out of a zoom
LAYOUT_T = 0.65    # seconds for a camera layout transition


def ease(p):
    p = min(1.0, max(0.0, p))
    return 4 * p ** 3 if p < 0.5 else 1 - (-2 * p + 2) ** 3 / 2


def hex_bgr(h):
    h = h.lstrip("#")
    return (int(h[4:6], 16), int(h[2:4], 16), int(h[0:2], 16))


def lerp(a, b, p):
    return tuple(x + (y - x) * p for x, y in zip(a, b))


def lerp_rect(a, b, p):
    """Interpolate rects by center (linear) and size (log) so zooms feel even."""
    ca, cb = (a[0] + a[2] / 2, a[1] + a[3] / 2), (b[0] + b[2] / 2, b[1] + b[3] / 2)
    cx, cy = ca[0] + (cb[0] - ca[0]) * p, ca[1] + (cb[1] - ca[1]) * p
    w = math.exp(math.log(a[2]) + (math.log(b[2]) - math.log(a[2])) * p)
    h = math.exp(math.log(a[3]) + (math.log(b[3]) - math.log(a[3])) * p)
    return (cx - w / 2, cy - h / 2, w, h)


# ---------------------------------------------------------------- zoom track

class ZoomTrack:
    """Keyframed zoom rect (source-normalized) over output time."""

    def __init__(self, zooms):
        keys = [(0.0, FULL, "hold")]
        zs = []
        for z in sorted(zooms, key=lambda z: z["s"]):
            if zs and z["s"] < zs[-1]["e"]:
                z = {**z, "s": zs[-1]["e"]}  # overlapping zooms: later one waits
            if z["e"] - z["s"] >= 0.6:
                zs.append(z)
        for i, z in enumerate(zs):
            s, e, r = z["s"], z["e"], tuple(z["rect"])
            t_in = min(ZOOM_T, (e - s) / 3)
            prev_end = keys[-1][0]
            if keys[-1][1] == FULL or s - prev_end > 0.01:
                keys.append((max(s, prev_end), keys[-1][1], "ease"))
            keys.append((s + t_in, r, "drift"))
            keys.append((e - t_in, _drift(r), "ease"))
            nxt = zs[i + 1] if i + 1 < len(zs) else None
            if not (nxt and nxt["s"] - e < 1.2):
                keys.append((e, FULL, "hold"))
            # else: next zoom pans straight from this rect
        self.keys = keys

    def at(self, t):
        k = self.keys
        for (t0, r0, mode), (t1, r1, _) in zip(k, k[1:]):
            if t0 <= t < t1:
                p = (t - t0) / max(1e-6, t1 - t0)
                if mode == "hold":
                    return r0
                if mode == "drift":  # slow push-in while holding a zoom
                    return lerp_rect(r0, r1, p)
                return lerp_rect(r0, r1, ease(p))
        return k[-1][1]


def _drift(r, amt=0.035):
    x, y, w, h = r
    return (x + w * amt / 2, y + h * amt / 2, w * (1 - amt), h * (1 - amt))


# ---------------------------------------------------------------- layouts

def layout_geometry(mode, W, H, fmt, src_aspect, cam_cfg, inset):
    """Return dict(screen=(x,y,w,h), cam=(x,y,w,h), radius, cam_alpha, cam_frame).
    cam_frame: crop height in face-heights (None = whole camera frame)."""
    m = inset * (H if fmt == "landscape" else W)

    def fit(bx, by, bw, bh):
        w = min(bw, bh * src_aspect)
        h = w / src_aspect
        return (bx + (bw - w) / 2, by + (bh - h) / 2, w, h)

    if fmt == "landscape":
        screen = fit(m, m, W - 2 * m, H - 2 * m)
        d = cam_cfg.get("size", 0.23) * H
        corner = cam_cfg.get("corner", "br")
        cx = W - m * 0.6 - d if "r" in corner else m * 0.6
        cy = H - m * 0.6 - d if "b" in corner else m * 0.6
        bubble = (cx, cy, d, d)
        if mode == "side":
            screen = fit(m, m, W * 0.66 - m, H - 2 * m)
            x0 = W * 0.66 + m * 0.4
            cw = W - x0 - m
            ch = min(H - 2 * m, cw * 1.3)
            return dict(screen=screen, cam=(x0, (H - ch) / 2, cw, ch), radius=28 * H / 1080, cam_alpha=1, cam_frame=4.2)
    else:
        sw = W - 2 * m
        screen = (m, H * 0.16, sw, sw / src_aspect)
        d = cam_cfg.get("size_vertical", 0.42) * W
        bubble = ((W - d) / 2, H * 0.72 - d / 2, d, d)
        if mode == "side":
            return dict(screen=screen, cam=(m, H * 0.585, W - 2 * m, H * 0.34), radius=32 * W / 1080, cam_alpha=1, cam_frame=4.2)

    if mode == "full":
        return dict(screen=screen, cam=(0, 0, W, H), radius=0, cam_alpha=1, cam_frame=None)
    if mode == "hidden":
        x, y, w, h = bubble
        return dict(screen=screen, cam=(x + w * 0.3, y + h * 0.3, w * 0.4, h * 0.4), radius=w * 0.2, cam_alpha=0, cam_frame=2.7)
    shape_r = bubble[2] / 2 if cam_cfg.get("shape", "circle") == "circle" else bubble[2] * 0.18
    return dict(screen=screen, cam=bubble, radius=shape_r, cam_alpha=1, cam_frame=2.7)


class LayoutTrack:
    def __init__(self, changes, geom):
        """changes: [(t_out, mode)], geom: mode -> geometry dict."""
        self.changes = sorted(changes) or [(0.0, "bubble")]
        if self.changes[0][0] > 0:
            self.changes.insert(0, (0.0, "bubble"))
        self.geom = geom

    def at(self, t):
        prev, cur, t0 = None, self.changes[0][1], 0.0
        for tc, mode in self.changes:
            if tc <= t:
                prev, cur, t0 = (cur if tc > 0 else None), mode, tc
        g = self.geom[cur]
        if prev is None or prev == cur or t - t0 >= LAYOUT_T:
            return g, 1.0, g
        p = ease((t - t0) / LAYOUT_T)
        a = self.geom[prev]
        mix = dict(screen=lerp(a["screen"], g["screen"], p), cam=lerp(a["cam"], g["cam"], p),
                   radius=a["radius"] + (g["radius"] - a["radius"]) * p,
                   cam_alpha=a["cam_alpha"] + (g["cam_alpha"] - a["cam_alpha"]) * p, cam_frame=g["cam_frame"])
        return mix, p, a


# ---------------------------------------------------------------- drawing primitives

@lru_cache(maxsize=64)
def rounded_mask(w, h, r):
    """Anti-aliased rounded-rect alpha (float32 0..1), supersampled 4x."""
    s = 4
    m = np.zeros((h * s, w * s), np.uint8)
    r = int(min(r, w / 2, h / 2) * s)
    if r <= 0:
        return np.ones((h, w), np.float32)
    cv2.rectangle(m, (r, 0), (w * s - r - 1, h * s - 1), 255, -1)
    cv2.rectangle(m, (0, r), (w * s - 1, h * s - r - 1), 255, -1)
    for cx, cy in ((r, r), (w * s - r - 1, r), (r, h * s - r - 1), (w * s - r - 1, h * s - r - 1)):
        cv2.circle(m, (cx, cy), r, 255, -1, cv2.LINE_AA)
    return cv2.resize(m, (w, h), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0


def blend_into(canvas, img, x, y, mask=None, alpha=1.0):
    """Paste img at integer (x, y) with optional float mask, clipped to canvas."""
    H, W = canvas.shape[:2]
    h, w = img.shape[:2]
    x0, y0, x1, y1 = max(0, x), max(0, y), min(W, x + w), min(H, y + h)
    if x1 <= x0 or y1 <= y0:
        return
    sub = img[y0 - y:y1 - y, x0 - x:x1 - x]
    if mask is None and alpha >= 0.999:
        canvas[y0:y1, x0:x1] = sub
        return
    a = (mask[y0 - y:y1 - y, x0 - x:x1 - x] if mask is not None else np.ones(sub.shape[:2], np.float32)) * alpha
    dst = canvas[y0:y1, x0:x1]
    a3 = a[..., None]
    canvas[y0:y1, x0:x1] = (sub * a3 + dst * (1 - a3)).astype(np.uint8)


def paste_rounded(canvas, img, x, y, r, alpha=1.0):
    """Fast rounded paste: straight copy of the body, mask only the corners."""
    h, w = img.shape[:2]
    if alpha < 0.999 or r > min(w, h) * 0.3:
        blend_into(canvas, img, x, y, rounded_mask(w, h, int(r)), alpha)
        return
    ri = int(math.ceil(r)) + 1
    mask = rounded_mask(w, h, int(r))
    H, W = canvas.shape[:2]
    if x < 0 or y < 0 or x + w > W or y + h > H:
        blend_into(canvas, img, x, y, mask, alpha)
        return
    canvas[y:y + h, x:x + w][ri:h - ri, :] = img[ri:h - ri, :]
    canvas[y:y + h, x:x + w][:, ri:w - ri] = img[:, ri:w - ri]
    for (yy, xx) in ((0, 0), (0, w - ri), (h - ri, 0), (h - ri, w - ri)):
        blend_into(canvas, img[yy:yy + ri, xx:xx + ri], x + xx, y + yy, mask[yy:yy + ri, xx:xx + ri])


def drop_shadow(canvas, rects, strength=0.55, spread=0.025):
    """Soft shadow under rounded rects, blurred at quarter resolution."""
    H, W = canvas.shape[:2]
    q = 4
    sh = np.zeros((H // q, W // q), np.uint8)
    for (x, y, w, h, r) in rects:
        off = int(H * 0.012 / q)
        cv2.rectangle(sh, (int(x / q), int(y / q) + off), (int((x + w) / q), int((y + h) / q) + off), 255, -1)
    k = int(H * spread / q) * 2 + 1
    sh = cv2.GaussianBlur(sh, (k, k), 0)
    sh = cv2.resize(sh, (W, H), interpolation=cv2.INTER_LINEAR).astype(np.float32) / 255.0 * strength
    return (canvas * (1 - sh[..., None])).astype(np.uint8)


def make_background(W, H, c1, c2, accent):
    """Diagonal gradient with a soft accent glow and fine grain (kills banding)."""
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    t = (xx / W * 0.6 + yy / H * 0.4)[..., None]
    bg = np.array(hex_bgr(c1), np.float32) * (1 - t) + np.array(hex_bgr(c2), np.float32) * t
    gx, gy = W * 0.82, H * 0.12
    glow = np.exp(-(((xx - gx) / (W * 0.45)) ** 2 + ((yy - gy) / (H * 0.55)) ** 2))[..., None] * 0.28
    bg = bg * (1 - glow) + np.array(hex_bgr(accent), np.float32) * glow
    bg += np.random.default_rng(7).normal(0, 1.6, bg.shape[:2])[..., None]
    return np.clip(bg, 0, 255).astype(np.uint8)


class Grade:
    """Camera color grade, applied to the (usually small) visible camera crop.
    White balance, exposure, contrast, a film S-curve and warmth are folded
    into one per-channel lookup table; saturation and sharpening follow."""

    CURVE = ([0, 0.25, 0.5, 0.75, 1], [0.02, 0.22, 0.5, 0.79, 0.98])  # lifted blacks, gentle S

    def __init__(self, p):
        x = np.arange(256, dtype=np.float32) / 255
        warm = 0.035 * p.get("warmth", 1)
        chans = []
        for gain, tint in zip(p["gains"], (warm, 0.0, -warm)):  # r, g, b
            y = np.clip(x * gain, 0, 1) ** (1 / p["gamma"])
            y = np.clip((y - 0.5) * p["contrast"] + 0.5, 0, 1)
            y = np.interp(y, *self.CURVE)
            y = np.clip(y * (1 + tint * (1 - y)), 0, 1)  # warmth weighted to shadows/mids
            chans.append(np.round(y * 255).astype(np.uint8))
        r, g, b = chans
        self.lut = np.stack([b, g, r], axis=1).reshape(256, 1, 3)
        self.sat = p.get("saturation", 1.0)
        self.sharpen = p.get("sharpen", 0.0)

    def apply(self, img):
        out = cv2.LUT(img, self.lut)
        if abs(self.sat - 1) > 0.01:
            gray = cv2.cvtColor(cv2.cvtColor(out, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
            out = cv2.addWeighted(out, self.sat, gray, 1 - self.sat, 0)
        if self.sharpen > 0.01:
            blur = cv2.GaussianBlur(out, (0, 0), 1.2)
            out = cv2.addWeighted(out, 1 + self.sharpen, blur, -self.sharpen, 0)
        return out


def cam_crop(cam_shape, box_aspect, look, frame_mult):
    """Crop rect (px) in the camera frame for a box of the given aspect,
    framed on the detected face with a little headroom."""
    ch_, cw_ = cam_shape[:2]
    fx, fy = (look or {}).get("face_center", (0.5, 0.42))
    fh = (look or {}).get("face_height", 0.32)
    h = min(1.0, fh * frame_mult) * ch_ if frame_mult else ch_
    w = h * box_aspect
    if w > cw_:
        w, h = cw_, cw_ / box_aspect
    cx = fx * cw_
    cy = fy * ch_ + h * 0.08
    x = min(max(cx - w / 2, 0), cw_ - w)
    y = min(max(cy - h / 2, 0), ch_ - h)
    return (x, y, w, h)


def warp_crop(img, rect, out_w, out_h):
    """Sub-pixel crop of rect=(x,y,w,h) px from img, resized to out size."""
    x, y, w, h = rect
    if out_w <= 0 or out_h <= 0:
        return None
    sx, sy = w / out_w, h / out_h
    ih, iw = img.shape[:2]
    whole = abs(x) < 0.5 and abs(y) < 0.5 and abs(w - iw) < 1 and abs(h - ih) < 1
    if whole or (sx > 1.6 and sy > 1.6):
        # no zoom (the common case) or heavy downscale: a plain resize is ~6x
        # cheaper than warpAffine, and area-resampling keeps text crisp
        x0, y0 = int(x), int(y)
        sub = img if whole else img[y0:y0 + int(math.ceil(h)), x0:x0 + int(math.ceil(w))]
        return cv2.resize(sub, (out_w, out_h), interpolation=cv2.INTER_AREA if sx >= 1 else cv2.INTER_LINEAR)
    M = np.array([[sx, 0, x + 0.5 * sx - 0.5], [0, sy, y + 0.5 * sy - 0.5]], np.float32)
    interp = cv2.INTER_CUBIC if sx < 0.6 else cv2.INTER_LINEAR  # cubic only for big zoom-ins
    return cv2.warpAffine(img, M, (out_w, out_h), flags=interp | cv2.WARP_INVERSE_MAP, borderMode=cv2.BORDER_REPLICATE)


def soft_blur(img, amt):
    if amt <= 0.01:
        return img
    H, W = img.shape[:2]
    small = cv2.resize(img, (W // 8, H // 8), interpolation=cv2.INTER_AREA)
    small = cv2.GaussianBlur(small, (0, 0), 2.5)
    big = cv2.resize(small, (W, H), interpolation=cv2.INTER_LINEAR)
    return cv2.addWeighted(img, 1 - amt, big, amt, 0)


def punch(img, amount):
    if amount <= 0.001:
        return img
    H, W = img.shape[:2]
    M = cv2.getRotationMatrix2D((W / 2, H / 2), 0, 1 + amount)
    return cv2.warpAffine(img, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def spotlight(canvas, screen_box, hole, accent, p):
    """Dim the screen outside `hole` (canvas px) and outline it in the accent."""
    sx, sy, sw, sh = [int(round(v)) for v in screen_box]
    hx, hy, hw, hh = [int(round(v)) for v in hole]
    hx0, hy0 = max(hx, sx), max(hy, sy)
    hx1, hy1 = min(hx + hw, sx + sw), min(hy + hh, sy + sh)
    if hx1 <= hx0 or hy1 <= hy0:
        return
    keep = canvas[hy0:hy1, hx0:hx1].copy()
    region = canvas[sy:sy + sh, sx:sx + sw]
    canvas[sy:sy + sh, sx:sx + sw] = cv2.convertScaleAbs(region, alpha=1 - 0.5 * p)
    canvas[hy0:hy1, hx0:hx1] = keep
    th = max(2, int(canvas.shape[0] / 300))
    over = canvas.copy()
    cv2.rectangle(over, (hx0 - th, hy0 - th), (hx1 + th, hy1 + th), hex_bgr(accent), th, cv2.LINE_AA)
    cv2.addWeighted(over, p, canvas, 1 - p, 0, dst=canvas)
