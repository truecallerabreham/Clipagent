"""Render HTML-engine Inserts to PNG frames with headless Chromium (Playwright).

Contract (docs/design.md, Contract 2): ``looks/_runtime/player.html?spec=<url>`` builds the scene
and exposes ``window.clipagent = {ready, duration, seek(t)}``; ``seek`` is a pure function of t.
This module serves the Look folder and the spec over a tiny localhost HTTP server (fetch() is
blocked on file:// URLs), opens the player at ``spec.size`` with deviceScaleFactor 1, waits for
``ready``, then for each frame i calls ``seek(i / fps)`` and screenshots ``out_dir/{i+1:05d}.png``
(1-based, 5 digits). Work is split across ``workers`` pages by contiguous frame ranges.

CLI::

    uv run python -m clipagent.inserts.html_render SPEC OUT_DIR [--workers N] [--still T ...]

``--still`` renders only single PNGs at the given times (reference frames and QA).
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import http.server
import json
import math
import os
import posixpath
import socketserver
import sys
import threading
import time
import urllib.parse
from pathlib import Path
from typing import Iterator

REPO_LOOKS = Path(__file__).resolve().parents[3] / "looks"
CHROME_ARGS = [
    "--font-render-hinting=none",
    "--force-color-profile=srgb",
    "--hide-scrollbars",
    "--disable-gpu",
    "--disable-partial-raster",
    "--disable-lcd-text",
    "--enable-unsafe-swiftshader",  # keep software WebGL (three.js Inserts) available with --disable-gpu
]
# /@file/<absolute path> serves local images referenced by absolute path in a spec (e.g. Screenshot src)
FILE_ROUTE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif"}
INSTALL_HINT = (
    "No usable Chromium for Playwright: Google Chrome is not installed and the bundled Chromium is "
    "missing. Run `clipagent setup --only browser` and retry."
)


def looks_dir() -> Path:
    """The folder holding one sub-folder per Look plus ``_runtime/`` (env CLIPAGENT_LOOKS_DIR overrides)."""
    env = os.environ.get("CLIPAGENT_LOOKS_DIR")
    return Path(env).expanduser().resolve() if env else REPO_LOOKS


def load_spec(spec_path: Path) -> dict:
    spec = json.loads(Path(spec_path).read_text())
    if spec.get("engine", "html") != "html":
        raise ValueError(f"{spec_path}: engine is {spec.get('engine')!r}, html_render only renders 'html' Inserts")
    for key in ("look", "size", "fps", "duration"):
        if key not in spec:
            raise ValueError(f"{spec_path}: resolved spec is missing {key!r}")
    look = looks_dir() / spec["look"]
    if not (look / "look.json").is_file():
        raise FileNotFoundError(f"Look {spec['look']!r} not found at {look} (set CLIPAGENT_LOOKS_DIR?)")
    return spec


def frame_count(spec: dict) -> int:
    return max(1, int(round(float(spec["duration"]) * float(spec["fps"]))))


# --------------------------------------------------------------------------- local http server
class _Handler(http.server.SimpleHTTPRequestHandler):
    """Serves /looks/* from the looks dir (with /looks/_runtime falling back to the repo runtime),
    /spec/* from the spec's folder, and /@file/<absolute path> for local image files only."""

    roots: dict[str, Path] = {}

    def translate_path(self, path: str) -> str:
        path = urllib.parse.unquote(urllib.parse.urlsplit(path).path)
        parts = [p for p in posixpath.normpath(path).split("/") if p and p not in (".", "..")]
        if not parts:
            return "/nonexistent"
        head, rest = parts[0], parts[1:]
        if head == "@file":
            target = Path("/", *rest)
            return str(target) if target.suffix.lower() in FILE_ROUTE_EXTS and target.is_file() else "/nonexistent"
        if head == "looks" and rest[:1] == ["_runtime"] and not (self.roots["looks"] / "_runtime").is_dir():
            base = REPO_LOOKS
        else:
            base = self.roots.get(head)
        if base is None:
            return "/nonexistent"
        return str(base.joinpath(*rest))

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, *args) -> None:  # quiet
        pass


class _Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


@contextlib.contextmanager
def _serve(spec_path: Path) -> Iterator[str]:
    """Start a localhost server and yield the player URL for this spec."""
    spec_path = Path(spec_path).resolve()
    handler = type("H", (_Handler,), {"roots": {"looks": looks_dir(), "spec": spec_path.parent}})
    srv = _Server(("127.0.0.1", 0), handler)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    try:
        port = srv.server_address[1]
        spec_url = f"/spec/{urllib.parse.quote(spec_path.name)}"
        yield f"http://127.0.0.1:{port}/looks/_runtime/player.html?spec={urllib.parse.quote(spec_url)}"
    finally:
        srv.shutdown()
        srv.server_close()


# --------------------------------------------------------------------------- browser
def _launch_sync(pw):
    try:
        return pw.chromium.launch(channel="chrome", args=CHROME_ARGS)
    except Exception:
        pass
    try:
        return pw.chromium.launch(args=CHROME_ARGS)
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"{INSTALL_HINT}\n({e})") from e


async def _launch_async(pw):
    try:
        return await pw.chromium.launch(channel="chrome", args=CHROME_ARGS)
    except Exception:
        pass
    try:
        return await pw.chromium.launch(args=CHROME_ARGS)
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"{INSTALL_HINT}\n({e})") from e


_READY_JS = """async () => {
  if (!window.clipagent) throw new Error('window.clipagent missing: runtime.js did not load');
  await window.clipagent.ready;
  return window.clipagent.duration;
}"""


def _ready_error(e: Exception, logs: list[str]) -> RuntimeError:
    tail = "\n".join(logs[-15:])
    return RuntimeError(f"Insert failed to load: {e}\n{tail}".rstrip())


@contextlib.contextmanager
def open_page(spec_path: Path):
    """Yield a Playwright (sync API) page at spec.size with the Insert loaded and ready awaited.

    Use ``page.evaluate("t => window.clipagent.seek(t)", t)`` to move in time. Browser and server
    are cleaned up on exit."""
    from playwright.sync_api import sync_playwright

    spec = load_spec(spec_path)
    w, h = (int(v) for v in spec["size"])
    with _serve(spec_path) as url, sync_playwright() as pw:
        browser = _launch_sync(pw)
        try:
            page = browser.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
            logs: list[str] = []
            page.on("console", lambda m: logs.append(f"[console.{m.type}] {m.text}"))
            page.on("pageerror", lambda e: logs.append(f"[pageerror] {e}"))
            page.goto(url, wait_until="load")
            try:
                page.evaluate(_READY_JS)
            except Exception as e:  # noqa: BLE001
                raise _ready_error(e, logs) from e
            yield page
        finally:
            browser.close()


# --------------------------------------------------------------------------- rendering
def _chunks(n: int, k: int) -> list[range]:
    k = max(1, min(k, n))
    size = math.ceil(n / k)
    return [range(i, min(n, i + size)) for i in range(0, n, size)]


async def _render_async(spec: dict, url: str, jobs: list[tuple[float, Path]], workers: int) -> None:
    from playwright.async_api import async_playwright

    w, h = (int(v) for v in spec["size"])
    transparent = bool(spec.get("transparent"))
    async with async_playwright() as pw:
        browser = await _launch_async(pw)
        try:

            async def work(part: list[tuple[float, Path]]) -> None:
                page = await browser.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
                logs: list[str] = []
                page.on("console", lambda m: logs.append(f"[console.{m.type}] {m.text}"))
                page.on("pageerror", lambda e: logs.append(f"[pageerror] {e}"))
                await page.goto(url, wait_until="load")
                try:
                    await page.evaluate(_READY_JS)
                except Exception as e:  # noqa: BLE001
                    raise _ready_error(e, logs) from e
                for t, path in part:
                    await page.evaluate("t => window.clipagent.seek(t)", t)
                    await page.screenshot(path=str(path), type="png", omit_background=transparent, animations="allow")
                await page.close()

            parts = [[jobs[i] for i in r] for r in _chunks(len(jobs), workers)]
            await asyncio.gather(*(work(p) for p in parts))
        finally:
            await browser.close()


def render_insert(spec_path: Path, out_dir: Path, workers: int = 2) -> Path:
    """Render every frame of an HTML Insert to ``out_dir/00001.png`` ... (frame i is at t=(i-1)/fps).

    Returns out_dir."""
    spec_path, out_dir = Path(spec_path), Path(out_dir)
    spec = load_spec(spec_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    fps = float(spec["fps"])
    n = frame_count(spec)
    jobs = [(i / fps, out_dir / f"{i + 1:05d}.png") for i in range(n)]
    with _serve(spec_path) as url:
        asyncio.run(_render_async(spec, url, jobs, workers))
    return out_dir


def render_stills(spec_path: Path, times: list[float], out_dir: Path, workers: int = 1) -> list[Path]:
    """Render single PNGs at the given times to ``out_dir/still_<t>s.png``."""
    spec_path, out_dir = Path(spec_path), Path(out_dir)
    spec = load_spec(spec_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    jobs = [(float(t), out_dir / f"still_{float(t):05.2f}s.png") for t in times]
    with _serve(spec_path) as url:
        asyncio.run(_render_async(spec, url, jobs, workers))
    return [p for _, p in jobs]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m clipagent.inserts.html_render", description="Render an HTML Insert spec to PNG frames.")
    ap.add_argument("spec", type=Path, help="resolved Insert spec (.json)")
    ap.add_argument("out_dir", type=Path, help="output folder for frames (00001.png ...) or stills")
    ap.add_argument("--workers", type=int, default=2, help="parallel pages (default 2)")
    ap.add_argument("--still", type=float, nargs="+", metavar="T", help="render only stills at these times (seconds)")
    a = ap.parse_args(argv)
    t0 = time.time()
    if a.still:
        paths = render_stills(a.spec, a.still, a.out_dir, workers=min(a.workers, len(a.still)))
        for p in paths:
            print(p)
        n = len(paths)
    else:
        render_insert(a.spec, a.out_dir, workers=a.workers)
        n = frame_count(load_spec(a.spec))
        print(f"{n} frames -> {a.out_dir}")
    dt = time.time() - t0
    print(f"{dt:.1f}s total, {dt / max(1, n):.3f}s/frame", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
