"""Looks: one production style for the whole video (see GLOSSARY.md)."""
from __future__ import annotations

import json
import os
from pathlib import Path

from .session import REPO_DIR

DEFAULT_TREATMENT = {
    "background": ["#0b0b10", "#16161d"],
    "frame": "plain",
    "radius": 14,
    "inset": 0.045,
    "zoom_scale": [1.2, 1.6],
    "click_effect": "ripple",
    "annotation_color": "#FFFFFF",
    "transition": "crossfade",
    "transition_colors": ["#38BDF8", "#A855F7", "#F59E0B"],
    "shortcut_badge": {"bg": "#1E1E1E", "fg": "#FFFFFF"},
}


def looks_dir() -> Path:
    env = os.environ.get("CLIPAGENT_LOOKS_DIR")
    if env:
        return Path(env)
    for cand in (REPO_DIR / "looks", Path(__file__).resolve().parent / "looks"):
        if cand.exists():
            return cand
    return REPO_DIR / "looks"


def list_looks() -> list[dict]:
    out = []
    root = looks_dir()
    if not root.exists():
        return out
    for d in sorted(root.iterdir()):
        f = d / "look.json"
        if d.name.startswith("_") or not f.exists():
            continue
        out.append(load_look(d.name))
    return out


def load_look(look_id: str) -> dict:
    f = looks_dir() / look_id / "look.json"
    if not f.exists():
        known = ", ".join(l["id"] for l in list_looks()) or "none installed"
        raise SystemExit(f"unknown Look '{look_id}' (available: {known})")
    look = json.loads(f.read_text())
    look.setdefault("id", look_id)
    look["screen_treatment"] = {**DEFAULT_TREATMENT, **look.get("screen_treatment", {})}
    look.setdefault("accent", "#D97757")
    look.setdefault("captions", {})
    look.setdefault("chapter_card", {"bg": "#000000", "fg": "#FFFFFF", "tracking": 0.3, "duration": 2.0})
    look.setdefault("sfx", {})
    look.setdefault("concept_palette", ["#FFFF00", "#83C167", "#FC6255", "#FF862F", "#58C4DD", "#A855F7"])
    look.setdefault("semantic", {})
    look["_dir"] = str(f.parent)
    return look


def apply_look_style(edl: dict, look: dict) -> dict:
    """Write the Look's screen treatment, captions and colors into edl.style."""
    st = look["screen_treatment"]
    cap = look.get("captions", {})
    style = edl.setdefault("style", {})
    style.update({
        "accent": look["accent"],
        "background": st["background"],
        "screen_inset": st["inset"],
        "radius": st["radius"],
        "frame": st["frame"],
        "click_effect": st["click_effect"],
        "annotation_color": st["annotation_color"],
        "transition": st["transition"],
        "transition_colors": st["transition_colors"],
        "shortcut_badge": st["shortcut_badge"],
        "dark": look.get("dark", True),
        "chapter_card": look["chapter_card"],
    })
    style["captions"] = {"enabled": cap.get("enabled", True), "words_per_line": cap.get("words_per_line", 4),
                         "highlight": cap.get("highlight", look["accent"]), "color": cap.get("color", "#FFFFFF")}
    if cap.get("background"):  # light Looks: dark words on a solid box instead of an outline
        style["captions"]["background"] = cap["background"]
    if cap.get("font"):  # e.g. Stickman Story: handwritten Patrick Hand captions
        style["captions"]["font"] = cap["font"]
    edl["look"] = look["id"]
    return edl


def concept_colors(edl: dict, look: dict) -> dict:
    """Concept Colors for the whole Session: the Look's semantic colors win, then
    edl.concepts (agent-assigned), then the Look palette in order of first use."""
    out = {}
    sem = {k.lower(): v for k, v in look.get("semantic", {}).items()}
    palette = list(look.get("concept_palette", []))
    used = set()
    for name, color in (edl.get("concepts") or {}).items():
        c = sem.get(name.lower()) or color
        out[name] = c
        used.add(c.lower())
    for ins in edl.get("inserts", []):
        for name in ins.get("concepts", []) if isinstance(ins.get("concepts"), list) else []:
            if name in out:
                continue
            c = sem.get(name.lower())
            if not c:
                free = [p for p in palette if p.lower() not in used] or palette
                c = free[0] if free else look["accent"]
            out[name] = c
            used.add(c.lower())
    return out
