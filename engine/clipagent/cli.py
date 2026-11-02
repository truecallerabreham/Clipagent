"""clipagent: the mechanical half of ClipAgent. The coding agent is the editor.

  clipagent start [--context PATH|URL ...] [--web] [--look ID] [--camera webcam|external|none] [--title T]
  clipagent stop | status | wait                       control the current Take
  clipagent context add PATH|URL ... [--web]           amend the Context Pack after the Take
  clipagent camera FILE                                add a phone/DSLR camera file (synced by audio)
  clipagent import SCREEN.mp4 [--camera CAM.mp4]       start a Session from an existing recording
  clipagent prepare                                    ingest + transcribe + analyze + draft edl.json
  clipagent frames [--every 20 | --at T --rect x,y,w,h]
  clipagent inserts [--only ID ...] [--force]          resolve Beats + render Inserts
  clipagent qa                                         self-check: automatic checks + comparison sheets
  clipagent render [--preview | --still T ... | --range A B]
  clipagent deliver                                    shorts, thumbnail, captions, chapters, copy, report
  clipagent snap URL [--selector CSS]                  screenshot a web page for a telestration Insert
  clipagent looks                                      list Looks
  clipagent doctor                                     check the machine
  clipagent install-recorder                           download the recorder app for this OS

Every command acts on the latest Session unless --session is given.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from . import session as S
from .common import FFMPEG, Timeline, load_json, probe, save_json

VERSION = "0.1.0"
RELEASES = "https://github.com/truecallerabreham/Clipagent/releases/latest/download"


def _session(args) -> S.Session:
    return S.Session.resolve(getattr(args, "session", None))


def _edl(s: S.Session) -> Path:
    p = s.work / "edl.json"
    if not p.exists():
        raise SystemExit("no edl.json yet: run `clipagent prepare` first")
    return p


# ---------------------------------------------------------------- recording

def cmd_start(args):
    s = S.Session.create(title=args.title or "", context=args.context_paths, urls=args.context_urls, web=args.web,
                         look=args.look, camera=args.camera, fmt=args.format, root=args.root)
    print(f"session: {s.path}")
    if args.no_record:
        return
    pid = S.start_recorder(s, camera_device=args.camera_device, mic=not args.no_mic, display=args.display)
    st = S.wait_for(s, ("recording",), timeout=args.timeout)
    if st.get("status") == "error":
        raise SystemExit(f"recorder error: {st.get('error')} (log: {s.take / 'recorder.log'})")
    if st.get("status") != "recording":
        print(f"recorder (pid {pid}) is starting; approve the screen-share prompt if one is showing")
    else:
        print(f"recording (pid {pid}). Stop with the floating bar, Ctrl+Alt+S, or `clipagent stop`.")
    print("Scratch Marker: Ctrl+Alt+X (or say “cut that”) to drop the last sentence.")


def cmd_stop(args):
    s = _session(args)
    S.request_stop(s)
    st = S.wait_for(s, ("done",), timeout=args.timeout)
    print(json.dumps(st))
    if st.get("status") != "done":
        raise SystemExit("recorder did not finish in time; check take/recorder.log")
    s.update(status="recorded")


def cmd_wait(args):
    """Block until the Take is finished (run it in the background so the agent is told when the user stops)."""
    s = _session(args)
    st = S.wait_for(s, ("done",), timeout=0, poll=1.0)
    if st.get("status") == "error":
        raise SystemExit(f"recorder error: {st.get('error')}")
    s.update(status="recorded")
    tk = S.take_manifest(s)
    print(f"take finished: {tk.get('duration', 0):.1f}s recorded -> {s.path}")


def cmd_status(args):
    s = _session(args)
    m = s.meta()
    out = {"session": str(s.path), "status": m.get("status"), "take": s.take_state(), "look": m.get("look"),
           "context_pack": m.get("context_pack"), "camera": m.get("camera")}
    print(json.dumps(out, indent=2))


def cmd_context(args):
    s = _session(args)
    cp = s.add_context(args.items, web=True if args.web else None, note=args.note)
    print(json.dumps(cp, indent=2))


def cmd_camera(args):
    s = _session(args)
    f = Path(args.file).resolve()
    if not f.exists():
        raise SystemExit(f"no such file: {f}")
    s.update(camera="external", camera_file=str(f))
    print(f"camera file set: {f} (synced to the screen by audio during prepare)")


def cmd_import(args):
    s = S.Session.create(title=args.title or Path(args.screen).stem, context=args.context_paths, urls=args.context_urls,
                         web=args.web, look=args.look, camera="external" if args.camera else "none", fmt=args.format,
                         root=args.root)
    from .ingest import import_media
    import_media(s, args.screen, args.camera)
    if args.camera:
        s.update(camera_file=str(Path(args.camera).resolve()))
    print(f"session: {s.path}")


# ---------------------------------------------------------------- preparing the edit

def cmd_prepare(args):
    from . import analyze, draft, transcribe
    from .ingest import ingest_take
    s = _session(args)
    m = s.meta()
    media_f = s.work / "media.json"
    if not media_f.exists() or args.reingest:
        media = ingest_take(s)
    else:
        media = load_json(media_f)
    work = str(s.work)
    if not (s.work / "transcript.json").exists() or args.retranscribe:
        print("transcribing (local Whisper; first run downloads the model)...", flush=True)
        vocab = ", ".join(filter(None, [args.vocab, _vocab_from_context(m)]))
        transcribe.main([media["screen"], work, "--model", args.model, "--language", args.language,
                         *(["--vocab", vocab] if vocab else [])])
    a = [work, "--screen", media["screen"]] + (["--camera", media["camera"]] if media.get("camera") else [])
    analyze.main(a)
    d = [work, "--screen", media["screen"], "--format", m.get("format", "landscape"), "--events", media["events"],
         "--look", args.look or m.get("look") or "architecture-flow"]
    if media.get("camera"):
        d += ["--camera", media["camera"]]
    if "camera_offset" in media:
        d += ["--camera-offset", str(media["camera_offset"])]
    draft.main(d)
    edl_p = s.work / "edl.json"
    edl = load_json(edl_p)
    edl["output"]["path"] = str(s.out / "final.mp4")
    edl["outro"]["text"] = edl["outro"].get("text") or "Made with ClipAgent"
    save_json(edl, edl_p)
    s.update(status="drafted")
    print(f"\nnext: read {s.work / 'transcript.txt'} and {s.work / 'words.txt'}, the Context Pack, then edit {edl_p}")


def _vocab_from_context(meta) -> str:
    """Names from the Context Pack steer Whisper's spelling (repo and file names)."""
    names = []
    for p in meta.get("context_pack", {}).get("paths", []):
        pp = Path(p)
        names.append(pp.name)
        if pp.is_dir():
            names += [c.stem for c in sorted(pp.iterdir())[:30] if not c.name.startswith(".")]
    seen = []
    for n in names:
        if n and n not in seen and len(n) < 40:
            seen.append(n)
    return ", ".join(seen[:40])


def cmd_frames(args):
    from . import frames
    s = _session(args)
    media = load_json(s.work / "media.json")
    a = [media["screen"], str(s.work / "frames")]
    if args.every:
        a += ["--every", str(args.every)]
    if args.at is not None:
        a += ["--at", str(args.at)]
    if args.rect:
        a += ["--rect", args.rect]
    frames.main(a)


def _timeline(edl):
    return Timeline(edl["segments"], edl["output"].get("fps", 30), probe(edl["inputs"]["screen"])["duration"])


def cmd_inserts(args):
    from .inserts.build import render_all
    s = _session(args)
    edl = load_json(_edl(s))
    tr = load_json(s.work / "transcript.json")
    man = render_all(s.work, edl, tr, _timeline(edl), only=args.only, workers=args.workers, force=args.force)
    n = sum(1 for i in man["inserts"] if i["status"] in ("rendered", "cached"))
    print(f"inserts: {n}/{len(man['inserts'])} ready, {len(man['warnings'])} warning(s)")


def cmd_qa(args):
    from .qa import print_qa, run_qa
    s = _session(args)
    edl = load_json(_edl(s))
    res = run_qa(s.work, edl, text_probe=not args.no_text_probe)
    print_qa(res)
    if args.stills:
        from . import render
        times = []
        for ins in load_json(s.work / "inserts" / "manifest.json")["inserts"]:
            a, b = ins["src"]
            times.append(round((a + b) / 2, 2))
        for l in edl.get("layouts", [])[:4]:
            times.append(l["at"] + 1.0)
        if times:
            render.main([str(_edl(s)), "--still", *map(str, times)])


def cmd_render(args):
    from . import render
    s = _session(args)
    a = [str(_edl(s)), "--workers", str(args.workers)]
    if args.preview:
        a.append("--preview")
    if args.still:
        a += ["--still", *map(str, args.still)]
    if args.range:
        a += ["--range", *map(str, args.range)]
    if args.force_cut:
        a.append("--force-cut")
    render.main(a)
    if not args.still and not args.preview and not args.range:
        s.update(status="rendered")


def cmd_deliver(args):
    from .deliver import deliver
    s = _session(args)
    res = deliver(s, _edl(s))
    s.update(status="delivered")
    print(json.dumps(res, indent=2))
    print(f"\nreport: {s.out / 'report.md'}")


def cmd_snap(args):
    """Screenshot a web page (or one element) into work/assets/ for telestration Inserts."""
    import re
    from playwright.sync_api import sync_playwright
    s = _session(args)
    if not s.meta()["context_pack"].get("web"):
        raise SystemExit("web content is not allowed for this Session (Context Pack web: false). "
                         "The user can allow it: `clipagent context add --web`")
    name = args.name or re.sub(r"[^a-z0-9]+", "-", args.url.lower().split("//")[-1])[:40].strip("-")
    out = s.work / "assets" / f"{name}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        try:
            b = p.chromium.launch(channel="chrome")
        except Exception:
            b = p.chromium.launch()
        page = b.new_page(viewport={"width": args.width, "height": args.height}, device_scale_factor=2)
        page.goto(args.url, wait_until="networkidle", timeout=45000)
        if args.selector:
            page.locator(args.selector).first.screenshot(path=str(out))
        else:
            page.screenshot(path=str(out))
        b.close()
    m = s.meta()
    m["context_pack"].setdefault("snaps", []).append({"url": args.url, "file": str(out)})
    s.save_meta(m)
    print(out)


def cmd_looks(args):
    from .looks import list_looks
    for l in list_looks():
        print(f"{l['id']:<20} {l.get('name', '')}: {l.get('description', '')}")
        if l.get("best_for"):
            print(f"{'':<20} best for: {', '.join(l['best_for'])}")


# ---------------------------------------------------------------- setup

def cmd_doctor(args):
    ok = True

    def say(k, v, good=True):
        nonlocal ok
        ok &= good
        print(f"{'ok ' if good else 'FIX'} {k:<12} {v}")

    ff = shutil.which("ffmpeg") or FFMPEG
    try:
        filters = subprocess.run([ff, "-hide_banner", "-filters"], capture_output=True, text=True).stdout
        need = [f for f in ("ass", "afftdn", "loudnorm", "sidechaincompress", "arnndn") if f" {f} " not in filters]
        say("ffmpeg", "ok" if not need else f"missing filters: {need} (install a full ffmpeg build)", not need)
    except FileNotFoundError:
        say("ffmpeg", "missing: install ffmpeg >= 6 (apt install ffmpeg / brew install ffmpeg / winget install ffmpeg)", False)
    try:
        S.recorder_command()
        say("recorder", "ok")
    except SystemExit as e:
        say("recorder", str(e), False)
    try:
        from .inserts import html_render  # noqa: F401
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            try:
                b = p.chromium.launch(channel="chrome")
            except Exception:
                b = p.chromium.launch()
            b.close()
        say("browser", "ok (headless Chromium for Inserts)")
    except Exception as e:
        say("browser", f"{str(e)[:120]} -> run: uv run playwright install chromium", False)
    if platform.system() == "Linux" and os.environ.get("XDG_SESSION_TYPE") == "wayland":
        import glob
        readable = any(os.access(p, os.R_OK) for p in glob.glob("/dev/input/event*"))
        say("input", "ok (evdev)" if readable else
            "keys/clicks not readable on Wayland: sudo usermod -aG input $USER, then log out and in "
            "(optional: ClipAgent estimates clicks from the video without it)", True)
    from .looks import list_looks
    looks = [l["id"] for l in list_looks()]
    say("looks", ", ".join(looks) if looks else "none found", bool(looks))
    try:
        import manim  # noqa: F401
        say("manim", "ok (math-vector Look uses real Manim)")
    except ImportError:
        say("manim", "not installed; installed on first use of math-vector (`uv sync --extra manim`)", True)
    print("ready." if ok else "fix the items marked FIX.")
    if not ok:
        sys.exit(1)


def cmd_install_recorder(args):
    """Download the prebuilt recorder for this OS from GitHub Releases into ~/ClipAgent/bin."""
    sysname = {"Linux": "linux", "Darwin": "mac", "Windows": "win"}[platform.system()]
    name = {"linux": "ClipAgent-Recorder-linux-x86_64.AppImage",
            "mac": "ClipAgent-Recorder-mac-universal.dmg",
            "win": "ClipAgent-Recorder-win-x64.zip"}[sysname]
    dest = S.HOME / "bin"
    dest.mkdir(parents=True, exist_ok=True)
    url = f"{RELEASES}/{name}"
    print(f"downloading {url}")
    tmp = dest / name
    urllib.request.urlretrieve(url, tmp)
    if sysname == "linux":
        target = dest / "clipagent-recorder"
        tmp.chmod(0o755)
        tmp.replace(target)
        if not any(Path(p).exists() for p in ("/usr/lib/x86_64-linux-gnu/libfuse.so.2", "/lib/x86_64-linux-gnu/libfuse.so.2")):
            print("note: AppImages need libfuse2 (sudo apt install libfuse2), or set APPIMAGE_EXTRACT_AND_RUN=1")
    elif sysname == "mac":
        mnt = Path(subprocess.run(["hdiutil", "attach", "-nobrowse", "-readonly", str(tmp)], capture_output=True,
                                  text=True, check=True).stdout.strip().split("\t")[-1])
        app = next(mnt.glob("*.app"))
        shutil.rmtree(dest / app.name, ignore_errors=True)
        shutil.copytree(app, dest / app.name, symlinks=True)
        subprocess.run(["hdiutil", "detach", str(mnt)], capture_output=True)
        tmp.unlink()
        target = dest / "clipagent-recorder"
        exe = next((dest / app.name / "Contents" / "MacOS").iterdir())
        target.write_text(f'#!/bin/sh\nexec "{exe}" "$@"\n')
        target.chmod(0o755)
    else:
        import zipfile
        with zipfile.ZipFile(tmp) as z:
            z.extractall(dest / "recorder-app")
        tmp.unlink()
        exe = next(p for p in (dest / "recorder-app").rglob("*.exe") if "uninstall" not in p.name.lower())
        target = dest / "clipagent-recorder.cmd"
        target.write_text(f'@"{exe}" %*\n')
    print(f"installed: {target}")


# ---------------------------------------------------------------- parser

def build_parser():
    ap = argparse.ArgumentParser(prog="clipagent", description="ClipAgent: talk freely, get a studio-edited video.")
    ap.add_argument("--version", action="version", version=f"clipagent {VERSION}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, fn, help_):
        p = sub.add_parser(name, help=help_)
        p.add_argument("--session", help="session path or id (default: latest)")
        p.set_defaults(fn=fn)
        return p

    def context_args(p):
        p.add_argument("--context", nargs="*", default=[], help="repo/doc paths or URLs for the Context Pack")
        p.add_argument("--web", action="store_true", help="allow web search for this Session")
        p.add_argument("--look", help="force a Look (default: the agent picks)")
        p.add_argument("--format", default="landscape", choices=["landscape", "vertical"])
        p.add_argument("--title", default="")
        p.add_argument("--root", help="where sessions live (default ~/ClipAgent/sessions)")

    p = add("start", cmd_start, "create a Session and start recording")
    context_args(p)
    p.add_argument("--camera", default="webcam", choices=["webcam", "external", "none"])
    p.add_argument("--camera-device")
    p.add_argument("--display")
    p.add_argument("--no-mic", action="store_true")
    p.add_argument("--no-record", action="store_true", help="only create the Session")
    p.add_argument("--timeout", type=float, default=45)

    p = add("stop", cmd_stop, "stop the recording")
    p.add_argument("--timeout", type=float, default=120)
    add("wait", cmd_wait, "block until the Take is finished")
    add("status", cmd_status, "show the Session")

    p = add("context", cmd_context, "amend the Context Pack")
    p.add_argument("action", choices=["add"])
    p.add_argument("items", nargs="*", default=[])
    p.add_argument("--web", action="store_true")
    p.add_argument("--note")

    p = add("camera", cmd_camera, "use a phone/DSLR camera file")
    p.add_argument("file")

    p = add("import", cmd_import, "start a Session from an existing recording")
    p.add_argument("screen")
    p.add_argument("--camera")
    context_args(p)

    p = add("prepare", cmd_prepare, "ingest + transcribe + analyze + draft")
    p.add_argument("--model", default=os.environ.get("CLIPAGENT_WHISPER_MODEL", "large-v3-turbo"))
    p.add_argument("--language", default="en")
    p.add_argument("--vocab", default="")
    p.add_argument("--look")
    p.add_argument("--reingest", action="store_true")
    p.add_argument("--retranscribe", action="store_true")

    p = add("frames", cmd_frames, "contact sheets / single frames of the screen")
    p.add_argument("--every", type=float)
    p.add_argument("--at", type=float)
    p.add_argument("--rect")

    p = add("inserts", cmd_inserts, "render Inserts")
    p.add_argument("--only", nargs="*")
    p.add_argument("--force", action="store_true")
    p.add_argument("--workers", type=int, default=3)

    p = add("qa", cmd_qa, "self-check")
    p.add_argument("--stills", action="store_true", help="also render composited stills at each Insert")
    p.add_argument("--no-text-probe", action="store_true")

    p = add("render", cmd_render, "render the video")
    p.add_argument("--preview", action="store_true")
    p.add_argument("--still", type=float, nargs="+")
    p.add_argument("--range", type=float, nargs=2)
    p.add_argument("--force-cut", action="store_true")
    p.add_argument("--workers", type=int, default=4)

    add("deliver", cmd_deliver, "write all Deliverables")
    p = add("snap", cmd_snap, "screenshot a web page into work/assets (web Context Packs only)")
    p.add_argument("url")
    p.add_argument("--name")
    p.add_argument("--selector")
    p.add_argument("--width", type=int, default=1440)
    p.add_argument("--height", type=int, default=900)
    add("looks", cmd_looks, "list Looks")
    add("doctor", cmd_doctor, "check the machine")
    add("install-recorder", cmd_install_recorder, "download the recorder app")
    return ap


def main(argv=None):
    ap = build_parser()
    args = ap.parse_args(argv)
    if hasattr(args, "context"):
        items = args.context or []
        args.context_paths = [c for c in items if not c.startswith(("http://", "https://"))]
        args.context_urls = [c for c in items if c.startswith(("http://", "https://"))]
    args.fn(args)


if __name__ == "__main__":
    main()
