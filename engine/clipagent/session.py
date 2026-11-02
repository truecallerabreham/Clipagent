"""Sessions: one folder per `/screen-record` run.

SESSION/
  session.json     id, title, Context Pack, Look, Camera Source, format, status
  take/            what the recorder wrote (never modified)
  work/            ingested media, transcript, analysis, edl.json, inserts, render cache, stills
  deliverables/    final video, shorts, thumbnail, captions, chapters, copy, report
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from .common import load_json, save_json

REPO_DIR = Path(__file__).resolve().parent.parent.parent      # repo root when running from a checkout
HOME = Path(os.environ.get("CLIPAGENT_HOME", Path.home() / "ClipAgent"))
SESSIONS = HOME / "sessions"
LATEST = HOME / "latest"


def slugify(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return s[:40] or "take"


class Session:
    def __init__(self, path: Path):
        self.path = Path(path).resolve()

    # -- folders
    @property
    def take(self) -> Path:
        return self.path / "take"

    @property
    def work(self) -> Path:
        return self.path / "work"

    @property
    def out(self) -> Path:
        return self.path / "deliverables"

    @property
    def meta_path(self) -> Path:
        return self.path / "session.json"

    def meta(self) -> dict:
        return load_json(self.meta_path)

    def save_meta(self, meta: dict):
        save_json(meta, self.meta_path)

    def update(self, **kw):
        m = self.meta()
        m.update(kw)
        self.save_meta(m)
        return m

    # -- lifecycle
    @classmethod
    def create(cls, title: str = "", context=None, urls=None, web=False, look=None, camera="webcam",
               fmt="landscape", root: Path | None = None) -> "Session":
        stamp = dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
        root = Path(root) if root else SESSIONS
        path = root / f"{stamp}_{slugify(title)}"
        path.mkdir(parents=True, exist_ok=False)
        s = cls(path)
        for d in (s.take, s.work, s.out):
            d.mkdir()
        s.save_meta({
            "version": 1,
            "id": path.name,
            "title": title,
            "created": dt.datetime.now().isoformat(timespec="seconds"),
            "status": "created",
            "context_pack": {"paths": [str(Path(p).resolve()) for p in (context or [])],
                             "urls": list(urls or []), "web": bool(web), "notes": []},
            "look": look,                # None = the agent picks from the Context Pack and topic
            "camera": camera,            # none | webcam | external (phone/DSLR file added after stop)
            "camera_file": None,
            "format": fmt,
        })
        set_latest(path)
        return s

    @classmethod
    def resolve(cls, ref: str | None) -> "Session":
        """A session from a path, a session id, or the latest one."""
        if ref:
            p = Path(ref)
            if p.exists():
                return cls(p)
            q = SESSIONS / ref
            if q.exists():
                return cls(q)
            raise SystemExit(f"no such session: {ref}")
        if LATEST.exists():
            target = Path(LATEST.read_text().strip())
            if target.exists():
                return cls(target)
        raise SystemExit("no session yet: start one with `clipagent start`")

    def add_context(self, items: list[str], web: bool | None = None, note: str | None = None):
        m = self.meta()
        cp = m["context_pack"]
        for it in items:
            if re.match(r"^https?://", it):
                if it not in cp["urls"]:
                    cp["urls"].append(it)
            else:
                p = str(Path(it).expanduser().resolve())
                if not Path(p).exists():
                    raise SystemExit(f"context path does not exist: {it}")
                if p not in cp["paths"]:
                    cp["paths"].append(p)
        if web is not None:
            cp["web"] = web
        if note:
            cp["notes"].append(note)
        self.save_meta(m)
        return cp

    def take_state(self) -> dict:
        f = self.take / "state.json"
        return load_json(f) if f.exists() else {"status": "not-started"}


def set_latest(path: Path):
    HOME.mkdir(parents=True, exist_ok=True)
    LATEST.write_text(str(Path(path).resolve()))


# ---------------------------------------------------------------- recorder process

def recorder_command() -> list[str]:
    """How to launch the recorder: $CLIPAGENT_RECORDER, an installed binary, or the dev checkout."""
    env = os.environ.get("CLIPAGENT_RECORDER")
    if env:
        return env.split()
    installed = HOME / "bin" / ("clipagent-recorder.exe" if sys.platform == "win32" else "clipagent-recorder")
    if installed.exists():
        return [str(installed)]
    found = shutil.which("clipagent-recorder")
    if found:
        return [found]
    dev = REPO_DIR / "recorder"
    wrapper = dev / "bin" / "clipagent-recorder"
    if wrapper.exists() and (dev / "node_modules").exists():
        return [str(wrapper)]
    raise SystemExit("recorder not installed: run `clipagent install-recorder` "
                     "(or `cd recorder && npm install` in a dev checkout)")


def start_recorder(s: Session, camera_device: str | None = None, mic: bool = True, display: str | None = None):
    cmd = recorder_command() + ["--session", str(s.path)]
    m = s.meta()
    if m["camera"] in ("none", "external"):
        cmd += ["--camera", "none"]
    elif camera_device:
        cmd += ["--camera", camera_device]
    if not mic:
        cmd += ["--no-mic"]
    if display:
        cmd += ["--display", display]
    log = open(s.take / "recorder.log", "ab")
    kw = {"start_new_session": True} if os.name != "nt" else {"creationflags": 0x00000008}  # DETACHED_PROCESS
    proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, **kw)
    s.update(status="recording", recorder_pid=proc.pid)
    return proc.pid


def wait_for(s: Session, statuses=("recording",), timeout=60.0, poll=0.25) -> dict:
    t0 = time.time()
    while True:
        st = s.take_state()
        if st.get("status") in statuses or st.get("status") == "error":
            return st
        if timeout and time.time() - t0 > timeout:
            return st
        time.sleep(poll)


def request_stop(s: Session):
    (s.take / "stop").write_text(str(time.time()))


def take_manifest(s: Session) -> dict:
    f = s.take / "take.json"
    if not f.exists():
        raise SystemExit(f"take not finished: {f} missing (is the recorder still running? `clipagent status`)")
    return json.loads(f.read_text())
