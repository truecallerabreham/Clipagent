from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Any

from app.runtime_paths import configure_runtime_environment, get_bundle_root, get_runtime_root

configure_runtime_environment()

BUNDLE_DIR = get_bundle_root()
CURRENT_DIR = get_runtime_root()

_task_workspace = (
    os.environ.get("CLIPAGENT_TASK_WORKSPACE", "").strip()
    or os.environ.get("CRAYOTTER_TASK_WORKSPACE", "").strip()
)
WORKSPACE = Path(_task_workspace).resolve(strict=False) if _task_workspace else CURRENT_DIR / "temp"

_user_workspace = (
    os.environ.get("CLIPAGENT_USER_WORKSPACE", "").strip()
    or os.environ.get("CRAYOTTER_USER_WORKSPACE", "").strip()
)
USER_WORKSPACE = Path(_user_workspace).resolve(strict=False) if _user_workspace else CURRENT_DIR / "user_temp"
os.environ.setdefault("CLIPAGENT_USER_WORKSPACE", str(USER_WORKSPACE.resolve(strict=False)))
os.environ.setdefault("CRAYOTTER_USER_WORKSPACE", str(USER_WORKSPACE.resolve(strict=False)))

MEMORY_EXPERIENCE_DIR = CURRENT_DIR / "memory_experience"


def _select_logs_dir() -> Path:
    primary = CURRENT_DIR / "logs"
    fallback = CURRENT_DIR / "runtime_logs"

    for candidate in (primary, fallback):
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            probe = candidate / ".write_test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return candidate
        except Exception:
            continue

    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


LOGS_DIR = _select_logs_dir()
logger = logging.getLogger("clipagent")


def _hidden_subprocess_kwargs() -> dict[str, Any]:
    if os.name != "nt":
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    return {
        "creationflags": subprocess.CREATE_NO_WINDOW,
        "startupinfo": startupinfo,
    }


def _merge_hidden_subprocess_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    hidden = _hidden_subprocess_kwargs()
    if not hidden:
        return dict(kwargs)
    merged = dict(kwargs)
    merged["creationflags"] = int(merged.get("creationflags", 0) or 0) | int(
        hidden["creationflags"]
    )
    merged.setdefault("startupinfo", hidden["startupinfo"])
    return merged


def _is_unittest_mock(callable_obj: Any) -> bool:
    return str(getattr(callable_obj, "__module__", "")) == "unittest.mock"


def run_subprocess(*popenargs: Any, **kwargs: Any) -> subprocess.CompletedProcess:
    if _is_unittest_mock(subprocess.run):
        return subprocess.run(*popenargs, **kwargs)
    return subprocess.run(*popenargs, **_merge_hidden_subprocess_kwargs(kwargs))


def popen_subprocess(*popenargs: Any, **kwargs: Any) -> subprocess.Popen:
    if _is_unittest_mock(subprocess.Popen):
        return subprocess.Popen(*popenargs, **kwargs)
    return subprocess.Popen(*popenargs, **_merge_hidden_subprocess_kwargs(kwargs))
