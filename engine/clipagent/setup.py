"""One-command setup, saved preferences, and linking the skill into every coding agent.

  clipagent setup            everything needed to record + edit, in parallel; instant once done
  clipagent prefs [...]      show / save the user's usual setup (asked once, reused every time)
  clipagent link             make /screen-record available in Claude Code, Codex, OpenCode, Antigravity
"""
from __future__ import annotations

import datetime as dt
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import session as S

RELEASES = "https://github.com/truecallerabreham/Clipagent/releases/latest/download"
SETUP_FILE = S.HOME / "setup.json"
LOCK = S.HOME / "setup.lock"
PREFS_FILE = S.HOME / "prefs.json"
SKILL_DIR = S.REPO_DIR / "skills" / "screen-record"
WHISPER_MODEL = os.environ.get("CLIPAGENT_WHISPER_MODEL", "large-v3-turbo")


# ---------------------------------------------------------------- preferences

PREF_CHOICES = {
    "make": ("tutorial", "short", "import"),            # 16:9 video, 9:16 short, edit an existing file
    "camera": ("webcam", "none", "external"),            # bubble, screen only, phone/DSLR file later
    "context": ("repo", "repo+web", "none"),             # what Inserts may draw from
}


def load_prefs() -> dict:
    try:
        p = json.loads(PREFS_FILE.read_text())
    except (OSError, ValueError):
        return {}
    p.pop("saved", None)
    return p


def save_prefs(**kw) -> dict:
    p = load_prefs()
    for k, v in kw.items():
        if v is None:
            continue
        if k in PREF_CHOICES and v not in PREF_CHOICES[k]:
            raise SystemExit(f"--{k} must be one of {', '.join(PREF_CHOICES[k])}")
        p[k] = None if (k == "look" and v in ("auto", "")) else v
    p["saved_at"] = dt.datetime.now().isoformat(timespec="seconds")
    S.HOME.mkdir(parents=True, exist_ok=True)
    PREFS_FILE.write_text(json.dumps(p, indent=2))
    return p


def describe_prefs(p: dict) -> str:
    if not p:
        return "none"
    make = {"tutorial": "16:9 video", "short": "9:16 short", "import": "edit an existing video"}.get(p.get("make"), "16:9 video")
    cam = {"webcam": "webcam bubble", "none": "screen only", "external": "phone camera added later"}.get(p.get("camera"), "webcam bubble")
    ctx = {"repo": "this repo", "repo+web": "this repo + web search", "none": "voice only"}.get(p.get("context"), "this repo")
    return f"{make} · {cam} · {ctx} · look: {p.get('look') or 'auto'}"


def apply_prefs(args):
    """Fill `start`/`import` flags the user didn't give from the saved setup, then from defaults."""
    p = load_prefs()
    if getattr(args, "camera", None) is None:
        args.camera = p.get("camera") or "webcam"
    if args.format is None:
        args.format = "vertical" if p.get("make") == "short" else "landscape"
    if args.look is None:
        args.look = p.get("look")
    ctx = p.get("context", "repo")
    if not args.context and ctx in ("repo", "repo+web"):
        args.context_paths = [os.getcwd()]
    if ctx == "repo+web" and not args.no_web:
        args.web = True
    if args.no_web:
        args.web = False


# ---------------------------------------------------------------- setup

def load_setup() -> dict:
    try:
        return json.loads(SETUP_FILE.read_text())
    except (OSError, ValueError):
        return {}


def _say(msg: str):
    print(msg, flush=True)


def _check_ffmpeg() -> tuple[bool, str]:
    from .common import FFMPEG
    ff = shutil.which("ffmpeg") or FFMPEG
    try:
        filters = subprocess.run([ff, "-hide_banner", "-filters"], capture_output=True, text=True).stdout
    except (FileNotFoundError, OSError):
        hint = {"Darwin": "brew install ffmpeg", "Windows": "winget install ffmpeg"}.get(platform.system(),
                                                                                         "sudo apt install ffmpeg")
        return False, f"missing: run `{hint}`"
    need = [f for f in ("ass", "afftdn", "loudnorm", "sidechaincompress", "arnndn") if f" {f} " not in filters]
    return (not need), ("ok" if not need else f"missing filters {need}: install a full ffmpeg build")


def recorder_ready() -> bool:
    try:
        S.recorder_command()
        return True
    except SystemExit:
        return False


def _ensure_recorder() -> tuple[bool, str]:
    if recorder_ready():
        return True, "ok"
    try:
        target = install_recorder(quiet=True)
        return True, f"installed ({target})"
    except SystemExit as e:
        return False, str(e)
    except Exception as e:  # noqa: BLE001
        return False, f"install failed: {e}"


def _browser_ok() -> bool:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            try:
                b = p.chromium.launch(channel="chrome")
            except Exception:  # noqa: BLE001
                b = p.chromium.launch()
            b.close()
        return True
    except Exception:  # noqa: BLE001
        return False


def _ensure_browser() -> tuple[bool, str]:
    if _browser_ok():
        return True, "ok"
    r = subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], capture_output=True, text=True)
    if r.returncode == 0 and _browser_ok():
        return True, "installed headless Chromium"
    return False, f"Chromium install failed: {(r.stderr or r.stdout).strip()[-200:]}"


def speech_model_ready() -> bool:
    try:
        from faster_whisper.utils import download_model
        download_model(WHISPER_MODEL, local_files_only=True)
        return True
    except Exception:  # noqa: BLE001
        return False


def _ensure_speech() -> tuple[bool, str]:
    if speech_model_ready():
        return True, "ok"
    try:
        from faster_whisper.utils import download_model
        download_model(WHISPER_MODEL)
        return True, f"downloaded {WHISPER_MODEL}"
    except Exception as e:  # noqa: BLE001
        return False, f"download failed ({e}); it is retried when the video is prepared"


TASKS = {"ffmpeg": _check_ffmpeg, "recorder": _ensure_recorder, "browser": _ensure_browser, "speech": _ensure_speech}


def _lock_alive() -> bool:
    try:
        pid = int(LOCK.read_text().strip())
    except (OSError, ValueError):
        return False
    try:
        os.kill(pid, 0)
        return pid != os.getpid()
    except PermissionError:
        return True
    except OSError:
        return False


def wait_for_other_setup(timeout: float = 1800):
    if not _lock_alive():
        return False
    _say("setup is already running in the background; waiting for it...")
    t0 = time.time()
    while _lock_alive() and time.time() - t0 < timeout:
        time.sleep(1)
    return True


def setup(only: list[str] | None = None, force: bool = False, quiet: bool = False) -> bool:
    """Install whatever is missing, in parallel. Prints one line per item. Returns True when ready to record."""
    S.HOME.mkdir(parents=True, exist_ok=True)
    names = only or ["ffmpeg", "recorder", "browser"]
    state = load_setup()
    if not force and not only and state.get("ready") and recorder_ready():
        if not quiet:
            _say("ready.")
        return True
    wait_for_other_setup()
    LOCK.write_text(str(os.getpid()))
    try:
        results = {}
        with ThreadPoolExecutor(max_workers=len(names)) as ex:
            futs = {n: ex.submit(TASKS[n]) for n in names}
            for n, f in futs.items():
                ok, msg = f.result()
                results[n] = {"ok": ok, "msg": msg}
                if not quiet or not ok:
                    _say(f"{'ok ' if ok else 'FIX'} {n:<9} {msg}")
        install_shim()
        items = {**load_setup().get("items", {}), **results}
        ready = all(items.get(n, {}).get("ok") for n in ("ffmpeg", "recorder", "browser"))
        SETUP_FILE.write_text(json.dumps({"ready": ready, "checked": dt.datetime.now().isoformat(timespec="seconds"),
                                          "items": items}, indent=2))
        if not only:
            _say("ready." if ready else "almost: fix the items marked FIX, then run setup again.")
        return ready
    finally:
        try:
            LOCK.unlink()
        except OSError:
            pass


def spawn_background(args: list[str], log_name: str):
    """Run `clipagent <args>` detached (used to fetch the speech model while the user records)."""
    S.HOME.mkdir(parents=True, exist_ok=True)
    log = open(S.HOME / log_name, "ab")
    kw = {"start_new_session": True} if os.name != "nt" else {"creationflags": 0x00000008}
    subprocess.Popen([sys.executable, "-m", "clipagent.cli", *args], stdout=log, stderr=subprocess.STDOUT,
                     stdin=subprocess.DEVNULL, **kw)


# ---------------------------------------------------------------- recorder install

def install_recorder(quiet: bool = False) -> Path:
    """Download the prebuilt recorder for this OS from GitHub Releases into ~/ClipAgent/bin (or build it)."""
    sysname = {"Linux": "linux", "Darwin": "mac", "Windows": "win"}[platform.system()]
    name = {"linux": "ClipAgent-Recorder-linux-x86_64.AppImage",
            "mac": "ClipAgent-Recorder-mac-universal.dmg",
            "win": "ClipAgent-Recorder-win-x64.zip"}[sysname]
    dest = S.HOME / "bin"
    dest.mkdir(parents=True, exist_ok=True)
    url = f"{RELEASES}/{name}"
    if not quiet:
        _say(f"downloading {url}")
    tmp = dest / name
    try:
        urllib.request.urlretrieve(url, tmp)
    except Exception as e:  # noqa: BLE001  no release published yet (or offline): build from the checkout
        if not quiet:
            _say(f"download failed ({e}); building the recorder from source instead")
        return build_recorder_from_source(dest, quiet=quiet)
    if sysname == "linux":
        target = dest / "clipagent-recorder"
        tmp.chmod(0o755)
        tmp.replace(target)
        if not any(Path(p).exists() for p in ("/usr/lib/x86_64-linux-gnu/libfuse.so.2", "/lib/x86_64-linux-gnu/libfuse.so.2")):
            _say("note: AppImages need libfuse2 (sudo apt install libfuse2), or set APPIMAGE_EXTRACT_AND_RUN=1")
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
    return target


def build_recorder_from_source(dest: Path, quiet: bool = False) -> Path:
    """Install only what the recorder needs at runtime (Electron + the input hook), not the packaging toolchain."""
    src = S.REPO_DIR / "recorder"
    if not (src / "package.json").exists():
        raise SystemExit("no recorder release and no recorder/ source folder: reinstall ClipAgent from git")
    npm = shutil.which("npm")
    if not npm:
        raise SystemExit("the recorder needs Node.js 20+ (https://nodejs.org), or a published recorder release")
    mods = src / "node_modules"
    if not (mods / "electron" / "package.json").exists():
        # A tiny package with just the runtime deps resolves in seconds; the full package.json pulls in
        # electron-builder and takes minutes. It lives in ~/ClipAgent so plugin updates don't re-download it.
        pkg = json.loads((src / "package.json").read_text())
        deps = {"electron": pkg["devDependencies"]["electron"], **pkg.get("optionalDependencies", {})}
        stage = S.HOME / "recorder-runtime"
        stage.mkdir(parents=True, exist_ok=True)
        (stage / "package.json").write_text(json.dumps({"name": "clipagent-recorder-runtime", "private": True,
                                                        "dependencies": deps}, indent=2))
        r = subprocess.run([npm, "install", "--no-audit", "--no-fund", "--loglevel=error"], cwd=stage,
                           capture_output=True, text=True, shell=sys.platform == "win32")
        if r.returncode != 0:
            raise SystemExit(f"npm install failed: {(r.stderr or r.stdout)[-300:]}")
        if mods.is_symlink() or mods.exists():
            shutil.rmtree(mods, ignore_errors=True) if not mods.is_symlink() else mods.unlink()
        if os.name == "nt":
            import _winapi
            _winapi.CreateJunction(str(stage / "node_modules"), str(mods))
        else:
            mods.symlink_to(stage / "node_modules", target_is_directory=True)
    node = shutil.which("node")
    if node and (mods / "electron" / "install.js").exists():         # fetch the Electron binary now, not mid-take
        subprocess.run([node, str(mods / "electron" / "install.js")], cwd=mods / "electron", capture_output=True)
    if sys.platform == "win32":
        target = dest / "clipagent-recorder.cmd"
        target.write_text(f'@node "{src / "bin" / "clipagent-recorder"}" %*\n')
    else:
        target = dest / "clipagent-recorder"
        if target.exists() or target.is_symlink():
            target.unlink()
        target.symlink_to(src / "bin" / "clipagent-recorder")
    return target


# ---------------------------------------------------------------- shim + agent linking

SHIM_MARK = "# clipagent shim"


def install_shim():
    """Put a `clipagent` command on PATH (~/.local/bin) so agents can call it without `uv run --project ...`."""
    exe = Path(sys.executable).parent / ("clipagent.exe" if os.name == "nt" else "clipagent")
    if os.name == "nt" or not exe.exists():
        return None
    bindir = Path.home() / ".local" / "bin"
    shim = bindir / "clipagent"
    if shim.exists() and SHIM_MARK not in shim.read_text(errors="ignore"):
        return None                                    # someone else's clipagent: leave it alone
    bindir.mkdir(parents=True, exist_ok=True)
    shim.write_text(f'#!/bin/sh\n{SHIM_MARK}\nexec "{exe}" "$@"\n')
    shim.chmod(0o755)
    return shim


def _agent_targets() -> list[tuple[str, Path, Path | None]]:
    """(agent, skills dir, slash-command file or None) for every agent installed on this machine."""
    h = Path.home()
    cfg = Path(os.environ.get("XDG_CONFIG_HOME", h / ".config"))
    out = []
    if (h / ".claude").is_dir():
        out.append(("Claude Code", h / ".claude" / "skills", None))
    if (h / ".codex").is_dir():
        out.append(("Codex", h / ".codex" / "skills", None))
    oc = cfg / "opencode"
    if oc.is_dir() or shutil.which("opencode"):
        cmd_dir = oc / ("command" if (oc / "command").is_dir() else "commands")
        out.append(("OpenCode", oc / "skills", cmd_dir / "screen-record.md"))
    gem = h / ".gemini"
    if (gem / "config").is_dir() or (gem / "antigravity").is_dir() or shutil.which("antigravity"):
        out.append(("Antigravity", gem / "config" / "skills", None))
    return out


OPENCODE_COMMAND = """---
description: Record your screen and get a studio-edited video (ClipAgent)
---
Load the `screen-record` skill and follow it. The user's request: $ARGUMENTS
"""


def _link_dir(src: Path, dst: Path):
    if dst.is_symlink() or dst.is_file():
        dst.unlink()
    elif dst.is_dir():
        if (dst / "SKILL.md").exists() and not (dst / ".git").exists():
            shutil.rmtree(dst)                         # an old copy of this skill
        else:
            raise SystemExit(f"{dst} exists and is not ClipAgent's: move it away and retry")
    dst.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        import _winapi                                 # a junction needs no admin rights
        _winapi.CreateJunction(str(src), str(dst))
    else:
        dst.symlink_to(src, target_is_directory=True)


def link_agents(only: list[str] | None = None, skip_claude: bool = False) -> list[str]:
    done = []
    for agent, skills, command in _agent_targets():
        if only and agent.lower().split()[0] not in [o.lower() for o in only]:
            continue
        if skip_claude and agent == "Claude Code":
            continue
        dst = skills / "screen-record"
        try:
            if not (dst.exists() and dst.resolve() == SKILL_DIR.resolve()):
                _link_dir(SKILL_DIR, dst)
            if command:
                command.parent.mkdir(parents=True, exist_ok=True)
                command.write_text(OPENCODE_COMMAND)
            done.append(f"{agent}: {dst}")
        except (OSError, SystemExit) as e:
            done.append(f"{agent}: FAILED ({e})")
    return done


if __name__ == "__main__":   # `python -m clipagent.setup link`: stdlib only, so it runs before `uv sync`
    if sys.argv[1:2] == ["link"]:
        lines = link_agents(only=sys.argv[2:] or None)
        print("\n".join(f"  ✓ {l}" for l in lines) if lines else
              "  no coding agent found yet (Claude Code, Codex, OpenCode, Antigravity): run `clipagent link` later")
