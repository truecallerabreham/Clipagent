"""Self-check: the run is hands-off, so the agent checks its own work before rendering.

Automatic checks (no judgment needed):
  - Beats whose words were cut, Inserts dropped by the resolver, Inserts overlapping in time
  - text inside each HTML Insert: clipped by the frame, outside the safe margin, or overlapping other text
  - Inserts covering code while the speaker is typing
  - a poor camera used full-frame
  - palette drift: Insert frames far from the Look's reference frames

Visual check (the agent's judgment): work/qa/<insert>.png puts each Insert's
frames next to the Look's reference frame; the agent looks at them, fixes the
scene, and re-runs (2 retries, then the Insert is dropped and reported).
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from .common import load_json, save_json
from .inserts.build import load_manifest
from .looks import load_look

TEXT_PROBE = """
() => {
  const W = window.innerWidth, H = window.innerHeight, m = 0.02;
  const boxes = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const n = walker.currentNode;
    if (!n.textContent.trim()) continue;
    const el = n.parentElement;
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none' || parseFloat(cs.opacity) < 0.05) continue;
    let o = el, hidden = false;
    while (o && o !== document.body) { if (parseFloat(getComputedStyle(o).opacity) < 0.05) { hidden = true; break; } o = o.parentElement; }
    if (hidden) continue;
    const r = document.createRange(); r.selectNodeContents(n);
    const b = r.getBoundingClientRect();
    if (b.width < 2 || b.height < 2) continue;
    boxes.push({text: n.textContent.trim().slice(0, 40), x: b.left, y: b.top, w: b.width, h: b.height});
  }
  const issues = [];
  for (const b of boxes) {
    if (b.h < 12) issues.push({kind: 'tiny', text: b.text});
    if (b.x < 0 || b.y < 0 || b.x + b.w > W || b.y + b.h > H) issues.push({kind: 'clipped', text: b.text});
    else if (b.x < W * m || b.y < H * m || b.x + b.w > W * (1 - m) || b.y + b.h > H * (1 - m)) issues.push({kind: 'margin', text: b.text});
  }
  for (let i = 0; i < boxes.length; i++) for (let j = i + 1; j < boxes.length; j++) {
    const a = boxes[i], c = boxes[j];
    const ix = Math.min(a.x + a.w, c.x + c.w) - Math.max(a.x, c.x);
    const iy = Math.min(a.y + a.h, c.y + c.h) - Math.max(a.y, c.y);
    if (ix > 3 && iy > 3 && ix * iy > 0.25 * Math.min(a.w * a.h, c.w * c.h)) issues.push({kind: 'overlap', text: a.text + ' / ' + c.text});
  }
  return issues;
}
"""


def probe_text(spec_path: Path, times: list[float]) -> list[dict]:
    """Open the Insert in headless Chromium and look for clipped/overlapping text."""
    from .inserts import html_render as HR
    issues = []
    try:
        with HR.open_page(spec_path) as page:
            for t in times:
                page.evaluate(f"window.clipagent.seek({t})")
                for it in page.evaluate(TEXT_PROBE):
                    it["t"] = round(t, 2)
                    issues.append(it)
    except Exception as e:  # missing browser etc.: report instead of failing QA
        issues.append({"kind": "probe-error", "text": str(e)[:200], "t": 0})
    seen, out = set(), []
    for it in issues:
        key = (it["kind"], it["text"])
        if key not in seen:
            seen.add(key)
            out.append(it)
    return out


def palette_distance(img: np.ndarray, ref: np.ndarray) -> float:
    """Distance between color histograms (0 same .. 1 unrelated)."""
    def hist(a):
        a = cv2.resize(a[..., :3], (160, 90))
        h = cv2.calcHist([a], [0, 1, 2], None, [8, 8, 8], [0, 256] * 3)
        return cv2.normalize(h, h).flatten()
    return float(cv2.compareHist(hist(img), hist(ref), cv2.HISTCMP_BHATTACHARYYA))


def side_by_side(frames: list[np.ndarray], ref: np.ndarray | None, path: Path, title: str):
    h = 360
    tiles = []
    if ref is not None:
        r = cv2.resize(ref[..., :3], (int(ref.shape[1] * h / ref.shape[0]), h))
        cv2.putText(r, "LOOK REFERENCE", (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 255), 2, cv2.LINE_AA)
        tiles.append(r)
    for i, f in enumerate(frames):
        if f.shape[2] == 4:  # transparent overlay: show it on a checkerboard
            bg = np.indices(f.shape[:2]).sum(0) // 24 % 2 * 60 + 70
            a = f[..., 3:4] / 255.0
            f = (f[..., :3] * a + bg[..., None] * (1 - a)).astype(np.uint8)
        t = cv2.resize(f, (int(f.shape[1] * h / f.shape[0]), h))
        cv2.putText(t, f"{title} #{i + 1}", (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2, cv2.LINE_AA)
        tiles.append(t)
    sheet = np.concatenate([np.pad(t, ((4, 4), (4, 4), (0, 0))) for t in tiles], axis=1)
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), sheet)


def run_qa(work: Path, edl: dict, analysis: dict | None = None, text_probe: bool = True) -> dict:
    manifest = load_manifest(work)
    look = load_look(edl.get("look") or "architecture-flow")
    refs = sorted(Path(look["_dir"], "reference").glob("*.png"))
    ref = cv2.imread(str(refs[0]), cv2.IMREAD_UNCHANGED) if refs else None
    typing = edl.get("typing", [])
    result = {"look": look["id"], "inserts": [], "global": list(manifest.get("warnings", []))}

    cam = edl.get("camera", {})
    if cam.get("allow_full") is False and any(l.get("camera") == "full" for l in edl.get("layouts", [])):
        result["global"].append("camera quality is poor but a layout uses the full-frame camera: use bubble/side")

    for ins in manifest["inserts"]:
        rep = {"id": ins["id"], "status": ins["status"], "issues": []}
        if ins["status"] in ("failed", "skipped"):
            rep["issues"].append({"kind": "not-rendered", "text": ins["status"]})
            result["inserts"].append(rep)
            continue
        frames = sorted(Path(ins["frames"]).glob("*.png"))
        if not frames:
            rep["issues"].append({"kind": "no-frames", "text": "frames missing"})
            result["inserts"].append(rep)
            continue
        picks = [frames[int(len(frames) * q)] for q in (0.3, 0.65, 0.97)]
        imgs = [cv2.imread(str(p), cv2.IMREAD_UNCHANGED) for p in picks]
        if ins["duration"] < 2.0:
            rep["issues"].append({"kind": "short", "text": f"only {ins['duration']:.1f}s on screen: hard to read"})
        s0, s1 = ins["src"]
        for a, b in typing:
            if a < s1 and s0 < b and ins["mode"] in ("full", "split", "overlay"):
                rep["issues"].append({"kind": "covers-typing", "text": f"covers typing at {a:.1f}-{b:.1f}s (source)"})
                break
        # blank frames: an Insert that renders nothing is broken
        last = imgs[-1]
        if last.shape[2] == 4 and int(last[..., 3].max()) == 0:
            rep["issues"].append({"kind": "blank", "text": "final frame is fully transparent"})
        elif last.shape[2] >= 3 and float(last[..., :3].std()) < 2.0:
            rep["issues"].append({"kind": "blank", "text": "final frame is a flat color"})
        if ref is not None and ins["mode"] == "full":
            d = palette_distance(imgs[1], ref)
            rep["palette_distance"] = round(d, 3)
            if d > 0.75:
                rep["issues"].append({"kind": "palette", "text": f"colors far from the Look reference ({d:.2f})"})
        if text_probe and Path(ins["spec"]).exists() and load_json(ins["spec"]).get("engine", "html") == "html":
            dur = ins["duration"]
            rep["issues"] += probe_text(Path(ins["spec"]), [dur * 0.5, max(0.0, dur - 0.1)])
        sheet = work / "qa" / f"{ins['id']}.png"
        side_by_side(imgs, ref, sheet, ins["id"])
        rep["sheet"] = str(sheet)
        rep["pass"] = not any(i["kind"] in ("clipped", "overlap", "blank", "no-frames", "not-rendered") for i in rep["issues"])
        result["inserts"].append(rep)
    result["pass"] = all(r.get("pass", False) for r in result["inserts"]) if result["inserts"] else True
    save_json(result, work / "qa.json")
    return result


def print_qa(res: dict):
    print(f"QA ({res['look']}): {'PASS' if res['pass'] else 'NEEDS FIXES'}")
    for g in res["global"]:
        print(f"  ! {g}")
    for r in res["inserts"]:
        mark = "ok " if r.get("pass") else "FIX"
        print(f"  [{mark}] {r['id']} ({r['status']})" + (f"  sheet: {r['sheet']}" if r.get("sheet") else ""))
        for i in r["issues"]:
            print(f"        - {i['kind']}: {i['text']}" + (f" @ {i['t']}s" if "t" in i else ""))
