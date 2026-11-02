"""Render Manim-engine Inserts (``"engine": "manim"``) to PNG frames.

Contract (docs/design.md): ``looks/<look>/manim/scene.py`` reads the resolved spec from env
``CLIPAGENT_SPEC`` and renders exactly ``duration`` seconds with each Beat at its ``at`` time.
This module runs ManimCE on it (PNG sequence, transparent when ``spec.transparent``) and writes
``frames_dir/00001.png ...`` (1-based, 5 digits), exactly ``round(duration * fps)`` frames: a short
render is padded with its last frame, a long one is trimmed.

Manim is optional: ``uv sync --project engine --extra manim``. Building it needs the cairo and
pango development packages (Debian/Ubuntu: ``sudo apt install libcairo2-dev libpango1.0-dev
pkg-config python3-dev``; macOS: ``brew install cairo pango pkg-config``). TeX needs a LaTeX
install (TeX Live minimal / MiKTeX / MacTeX); without one, the scene falls back to plain Text.

CLI::

    uv run python -m clipagent.inserts.manim_render SPEC OUT_DIR
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from ..looks import looks_dir

INSTALL_HINT = (
    "The Manim engine is not installed. Run `uv sync --project engine --extra manim` "
    "(it builds pycairo/manimpango, which need the cairo and pango development packages: "
    "Debian/Ubuntu `sudo apt install libcairo2-dev libpango1.0-dev pkg-config python3-dev`, "
    "macOS `brew install cairo pango pkg-config`). For Tex you also need LaTeX "
    "(TeX Live minimal on Linux, MiKTeX on Windows, MacTeX/BasicTeX on macOS); without it "
    "equations fall back to plain Text. Or set the Insert's engine to \"html\" (no extra installs)."
)


def manim_available() -> bool:
    return importlib.util.find_spec("manim") is not None


def latex_available() -> bool:
    return shutil.which("latex") is not None


def frame_count(spec: dict) -> int:
    return max(1, round(float(spec["duration"]) * float(spec["fps"])))


def _scene_file(spec: dict) -> Path:
    f = looks_dir() / spec["look"] / "manim" / "scene.py"
    if not f.exists():
        raise FileNotFoundError(f"Look '{spec['look']}' has no Manim scene ({f}); use engine \"html\" for it")
    return f


def render_manim(spec_path: Path, frames_dir: Path) -> Path:
    """Render one Manim Insert to ``frames_dir/%05d.png``. Returns frames_dir."""
    spec_path = Path(spec_path).resolve()
    spec = json.loads(spec_path.read_text())
    for key in ("look", "size", "fps", "duration"):
        if key not in spec:
            raise ValueError(f"{spec_path}: missing '{key}'")
    if not manim_available():
        raise RuntimeError(INSTALL_HINT)
    scene = _scene_file(spec)
    w, h = spec["size"]
    fps = spec["fps"]
    env = dict(os.environ, CLIPAGENT_SPEC=str(spec_path))
    if not latex_available():
        env["CLIPAGENT_NO_LATEX"] = "1"
        print("warning: LaTeX not found; Manim Tex falls back to plain Text "
              "(install TeX Live minimal / MiKTeX / MacTeX for real LaTeX)", file=sys.stderr)
    frames_dir = Path(frames_dir)
    frames_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="clipagent-manim-") as tmp:
        cmd = [sys.executable, "-m", "manim", "render", str(scene), "ClipAgentScene",
               "--format", "png", "--resolution", f"{w},{h}", "--frame_rate", str(fps),
               "--media_dir", tmp, "--disable_caching", "--progress_bar", "none", "-v", "WARNING"]
        if spec.get("transparent"):
            cmd.append("--transparent")
        t0 = time.time()
        r = subprocess.run(cmd, env=env, cwd=tmp, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"manim failed ({r.returncode}):\n{r.stderr[-4000:] or r.stdout[-4000:]}")
        pngs = sorted(Path(tmp).rglob("ClipAgentScene*.png"), key=lambda p: int(re.findall(r"(\d+)\.png$", p.name)[0]) if re.findall(r"(\d+)\.png$", p.name) else -1)
        if not pngs:
            raise RuntimeError(f"manim produced no PNG frames:\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}")
        n = frame_count(spec)
        for old in frames_dir.glob("*.png"):
            old.unlink()
        for i in range(n):
            src = pngs[min(i, len(pngs) - 1)]
            shutil.copyfile(src, frames_dir / f"{i + 1:05d}.png")
        print(f"{n} frames ({len(pngs)} rendered by manim) in {time.time() - t0:.1f}s -> {frames_dir}")
    return frames_dir


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m clipagent.inserts.manim_render", description="Render a Manim Insert spec to PNG frames.")
    ap.add_argument("spec", type=Path)
    ap.add_argument("out_dir", type=Path)
    a = ap.parse_args(argv)
    try:
        render_manim(a.spec, a.out_dir)
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
