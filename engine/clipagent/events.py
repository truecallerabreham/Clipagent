"""What the input-event log tells the edit: click zooms, shortcut badges, Scratch Markers."""
from __future__ import annotations


def clicks(events: list[dict], activity: list[dict] | None = None) -> list[dict]:
    """Clicks with a position. Clicks logged without coordinates (evdev on Wayland
    only sees relative motion) get the centre of the screen change right after them."""
    out = []
    for e in events:
        if e["type"] != "click":
            continue
        x, y = e.get("x"), e.get("y")
        if x is None or y is None:
            box = _box_after(activity or [], e["t"])
            if not box:
                continue
            x, y = box[0] + box[2] / 2, box[1] + box[3] / 2
            out.append({"t": e["t"], "x": round(x, 4), "y": round(y, 4), "estimated": True})
        else:
            out.append({"t": e["t"], "x": x, "y": y})
    return out


def _box_after(activity, t, within=1.5):
    for a in activity:
        if t <= a["t"] <= t + within and a.get("box"):
            return a["box"]
    return None


def click_zooms(clk: list[dict], scale=(1.2, 1.6), hold=2.5, merge_gap=3.0, src_aspect=16 / 9) -> list[dict]:
    """Group nearby clicks into zooms centred on them (scale 1.2-1.6x per the Look)."""
    zooms = []
    for c in clk:
        if zooms and c["t"] - zooms[-1]["_last"] <= merge_gap and \
                abs(c["x"] - zooms[-1]["_cx"]) < 0.25 and abs(c["y"] - zooms[-1]["_cy"]) < 0.25:
            z = zooms[-1]
            z["_pts"].append((c["x"], c["y"]))
            z["_last"] = c["t"]
            z["end"] = round(c["t"] + hold, 2)
            continue
        zooms.append({"start": round(max(0.0, c["t"] - 0.6), 2), "end": round(c["t"] + hold, 2),
                      "_cx": c["x"], "_cy": c["y"], "_last": c["t"], "_pts": [(c["x"], c["y"])]})
    out = []
    for z in zooms:
        xs = [p[0] for p in z["_pts"]]
        ys = [p[1] for p in z["_pts"]]
        spread = max(max(xs) - min(xs), max(ys) - min(ys))
        s = max(scale[0], min(scale[1], 1.0 / max(0.35, spread + 0.45)))
        w = h = 1.0 / s           # normalized units: aspect 1.0 == source aspect
        cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
        x = min(max(cx - w / 2, 0.0), 1 - w)
        y = min(max(cy - h / 2, 0.0), 1 - h)
        out.append({"start": z["start"], "end": z["end"], "rect": [round(x, 3), round(y, 3), round(w, 3), round(h, 3)],
                    "note": f"auto: {len(xs)} click(s) here"})
    return out


def shortcuts(events: list[dict]) -> list[dict]:
    return [{"at": e["t"], "keys": e["keys"]} for e in events if e["type"] == "shortcut" and e.get("keys")]


def typing_spans(events: list[dict], gap=1.5, min_len=2.0) -> list[list[float]]:
    """Stretches of continuous typing (used to keep Inserts off code being written)."""
    ts = [e["t"] for e in events if e["type"] == "typing"]
    spans = []
    for t in ts:
        if spans and t - spans[-1][1] <= gap:
            spans[-1][1] = t
        else:
            spans.append([t, t])
    return [[round(a, 2), round(b + 0.5, 2)] for a, b in spans if b - a >= min_len]


def scratch_markers(events: list[dict]) -> list[float]:
    return [e["t"] for e in events if e["type"] == "marker" and e.get("kind", "scratch") == "scratch"]


def spoken_scratches(words: list[dict]) -> list[float]:
    """Saying "cut that" / "scratch that" works like the hotkey."""
    out = []
    norm = [w["w"].strip(" ,.!?").lower() for w in words]
    for i in range(len(norm) - 1):
        if norm[i] in ("cut", "scratch") and norm[i + 1] == "that":
            # only when it stands alone as its own sentence: a pause or a sentence end before it,
            # or "that" closes a sentence ("Cut that.")
            pause_before = i == 0 or words[i]["s"] - words[i - 1]["e"] > 0.35 or \
                words[i - 1]["w"].rstrip().endswith((".", "?", "!", ","))
            standalone = words[i + 1]["w"].rstrip().endswith((".", "!"))
            if pause_before or standalone:
                out.append((words[i]["s"], words[i + 1]["e"]))
    return out


def apply_scratches(segments: list[dict], words: list[dict], marks: list[float], spoken: list) -> tuple[list[dict], list[list[float]]]:
    """Cut from the start of the sentence before each mark through the mark.

    The sentence start is the first word after the last pause > 0.45 s (or a
    sentence-ending punctuation) before the mark. Returns (segments, removed spans)."""
    removed = []
    # a hotkey mark cuts the sentence before it; a spoken "cut that" also cuts itself
    spans = sorted([(m, m) for m in marks] + [tuple(x) for x in spoken])
    for anchor, m in spans:
        before = [w for w in words if w["e"] <= anchor + 0.05]
        if not before:
            continue
        start = before[0]["s"]
        for a, b in zip(reversed(before[:-1]), reversed(before)):
            if b["s"] - a["e"] > 0.45 or a["w"].rstrip().endswith((".", "?", "!")):
                start = b["s"]
                break
        cut = [round(max(0.0, start - 0.05), 3), round(m + 0.15, 3)]
        removed.append(cut)
        segments = subtract(segments, cut)
    return segments, removed


def subtract(segments: list[dict], cut: list[float]) -> list[dict]:
    a, b = cut
    out = []
    for s in segments:
        if s["end"] <= a or s["start"] >= b:
            out.append(s)
            continue
        if s["start"] < a:
            out.append({**s, "end": round(a, 3)})
        if s["end"] > b:
            out.append({**s, "start": round(b, 3)})
    return [s for s in out if s["end"] - s["start"] > 0.08]
