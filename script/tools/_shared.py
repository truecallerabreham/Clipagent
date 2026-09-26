from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

try:
    import cv2
except ImportError:
    cv2 = None

try:
    from langchain_core.tools import tool
except ImportError:
    def tool(func: Any = None, *args: Any, **kwargs: Any) -> Any:
        if func is not None and callable(func):
            return func

        def decorator(f: Any) -> Any:
            return f

        return decorator

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

WORKSPACE.mkdir(parents=True, exist_ok=True)
USER_WORKSPACE.mkdir(parents=True, exist_ok=True)
MEMORY_EXPERIENCE_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

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


def _is_within_workspace(path: Path) -> bool:
    allowed_roots = (
        WORKSPACE.resolve(strict=False),
        USER_WORKSPACE.resolve(strict=False),
    )
    try:
        resolved = path.resolve(strict=False)
    except Exception:
        return False

    for root in allowed_roots:
        try:
            resolved.relative_to(root)
            return True
        except Exception:
            continue
    return False


def _resolve_workspace_input_path(raw_path: str, must_exist: bool = True) -> Path | None:
    raw = (raw_path or "").strip()
    if not raw:
        return None

    if raw.startswith("file://"):
        parsed = urlparse(raw)
        raw = unquote(parsed.path or "")
        if os.name == "nt" and re.match(r"^/[a-zA-Z]:", raw):
            raw = raw.lstrip("/")

    source = Path(raw)
    roots = [WORKSPACE, USER_WORKSPACE]
    candidates: list[Path] = []
    if source.is_absolute():
        candidates.append(source)
        for root in roots:
            candidates.append(root / source.name)
    else:
        candidates.append(CURRENT_DIR / source)

        parts = source.parts
        if parts:
            if parts[0] == WORKSPACE.name and len(parts) > 1:
                candidates.append(WORKSPACE / Path(*parts[1:]))
            elif parts[0] == USER_WORKSPACE.name and len(parts) > 1:
                candidates.append(USER_WORKSPACE / Path(*parts[1:]))

        for root in roots:
            candidates.append(root / source)
            candidates.append(root / source.name)

    seen: set[str] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve(strict=False)
        except Exception:
            continue
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)

        if not _is_within_workspace(resolved):
            continue
        if must_exist and not resolved.exists():
            continue
        return resolved
    return None


def _safe_output_video_path(output_name: str, default_stem: str = "output") -> Path:
    stem_raw = (output_name or default_stem).strip()
    stem = Path(stem_raw).name
    stem = Path(stem).stem or default_stem
    stem = re.sub(r"[^0-9A-Za-z_\-\u4e00-\u9fff]+", "_", stem).strip("_")
    if not stem:
        stem = default_stem
    return (WORKSPACE / f"{stem}.mp4").resolve()


def _resolve_video_path(video_path: str) -> Path | None:
    resolved = _resolve_workspace_input_path(video_path, must_exist=True)
    if resolved is not None:
        return resolved

    raw = (video_path or "").strip()
    if not raw:
        return None

    direct = Path(raw)

    # 若是 BV 号路径推断，尝试寻找同名别名文件
    stem = direct.stem
    if stem.upper().startswith("BV"):
        for root in (WORKSPACE, USER_WORKSPACE):
            alias = root / f"{stem}.mp4"
            if alias.exists():
                return alias
    return None


def _get_video_meta(video_path: str) -> dict[str, Any]:
    if cv2 is not None:
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = frame_count / fps if fps > 0 else 0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()
        return {
            "duration_seconds": round(duration, 2),
            "fps": round(fps, 2),
            "resolution": f"{width}x{height}",
            "width": width,
            "height": height,
        }

    try:
        from ._native_ffmpeg import probe_video

        probe = probe_video(Path(video_path))
        return {
            "duration_seconds": round(probe.duration, 2),
            "fps": round(probe.fps, 2),
            "resolution": f"{probe.width}x{probe.height}",
            "width": probe.width,
            "height": probe.height,
        }
    except Exception as exc:
        raise RuntimeError(
            f"Cannot inspect video {video_path}: cv2 is not installed and ffprobe failed ({exc})"
        ) from exc


__all__ = [
    name
    for name in globals()
    if name not in {
        "__builtins__",
        "__cached__",
        "__doc__",
        "__file__",
        "__loader__",
        "__name__",
        "__package__",
        "__spec__",
        "__all__",
    }
]
