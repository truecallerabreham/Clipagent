from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

# Optional OpenCV import for fast local frame inspection without subprocess overhead
try:
    import cv2
except ImportError:
    cv2 = None

# Optional LangChain core import: provides @tool decorator for LLM agent integration
# If langchain_core is not installed, provide a no-op fallback decorator.
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

# ==============================================================================
# SECTION 1: RUNTIME BOOTSTRAP & DIRECTORY INITIALIZATION
# ==============================================================================
# Major Aim:
#   Initialize the application environment and anchor core workspace directories
#   so all agent tools have isolated, safe areas to store temporary files and logs.
#
# Visual Example Flow:
#   configure_runtime_environment()
#         |
#         +--> BUNDLE_DIR  = Read-only code and bundled binaries
#         +--> CURRENT_DIR = Writable runtime root
#         +--> WORKSPACE   = Temporary task video files (temp/)
#         +--> USER_WORKSPACE = User uploaded videos (user_temp/)
#         \--> LOGS_DIR    = Persistent execution logs (logs/)
# ==============================================================================
configure_runtime_environment()

BUNDLE_DIR = get_bundle_root()
CURRENT_DIR = get_runtime_root()

# Task Workspace: where agent tools write intermediate video cuts and renders
_task_workspace = os.environ.get("CLIPAGENT_TASK_WORKSPACE", "").strip()
WORKSPACE = Path(_task_workspace).resolve(strict=False) if _task_workspace else CURRENT_DIR / "temp"

# User Workspace: where user-provided source media files are staged
_user_workspace = os.environ.get("CLIPAGENT_USER_WORKSPACE", "").strip()
USER_WORKSPACE = Path(_user_workspace).resolve(strict=False) if _user_workspace else CURRENT_DIR / "user_temp"
os.environ.setdefault("CLIPAGENT_USER_WORKSPACE", str(USER_WORKSPACE.resolve(strict=False)))

# Experience Directory: stores historical workflow heuristics and agent memory
MEMORY_EXPERIENCE_DIR = CURRENT_DIR / "memory_experience"


def _select_logs_dir() -> Path:
    """Select a writable directory for application logs, falling back if needed.
    
    Major Aim:
      Ensure logging never crashes the app by testing candidate directories
      with an empirical write probe before selecting one.
    """
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

# Ensure all essential directories exist before any tool executes
WORKSPACE.mkdir(parents=True, exist_ok=True)
USER_WORKSPACE.mkdir(parents=True, exist_ok=True)
MEMORY_EXPERIENCE_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("clipagent")


# ==============================================================================
# SECTION 2: WINDOWS SILENT SUBPROCESS CONTROLLER
# ==============================================================================
# Major Aim:
#   Prevent flashing black command prompt (cmd.exe) windows from popping up on
#   the user's desktop whenever background processes (FFmpeg, FFprobe, Python) run.
#
# Visual Example Flow:
#   subprocess.run(["ffmpeg", ...])
#              |
#              V  (Without these flags: Black cmd box flashes on screen)
#   _hidden_subprocess_kwargs()
#              |
#              +--> creationflags = CREATE_NO_WINDOW (0x08000000)
#              \--> startupinfo: dwFlags |= STARTF_USESHOWWINDOW, wShowWindow = SW_HIDE
#              |
#              V  (With these flags: Completely silent background execution)
# ==============================================================================
def _hidden_subprocess_kwargs() -> dict[str, Any]:
    """Build Windows-specific startup flags to suppress visible console windows."""
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
    """Combine user-supplied subprocess kwargs with the silent console flags."""
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
    """Detect whether a subprocess function has been replaced with a test mock."""
    return str(getattr(callable_obj, "__module__", "")) == "unittest.mock"


def run_subprocess(*popenargs: Any, **kwargs: Any) -> subprocess.CompletedProcess:
    """Run a subprocess to completion while hiding its console window on Windows."""
    if _is_unittest_mock(subprocess.run):
        return subprocess.run(*popenargs, **kwargs)
    return subprocess.run(*popenargs, **_merge_hidden_subprocess_kwargs(kwargs))


def popen_subprocess(*popenargs: Any, **kwargs: Any) -> subprocess.Popen:
    """Launch an asynchronous subprocess while hiding its console window on Windows."""
    if _is_unittest_mock(subprocess.Popen):
        return subprocess.Popen(*popenargs, **kwargs)
    return subprocess.Popen(*popenargs, **_merge_hidden_subprocess_kwargs(kwargs))


# ==============================================================================
# SECTION 3: WORKSPACE SECURITY PERIMETER GUARD
# ==============================================================================
# Major Aim:
#   Prevent arbitrary file read/write attacks (path traversal) by verifying that
#   every file handled by agent tools strictly resides within authorized directories.
#
# Visual Example Flow:
#   User input: "../../Windows/System32/calc.exe"
#         |
#         V
#   _is_within_workspace(path)
#         |
#         +--> Resolved: C:\Windows\System32\calc.exe
#         +--> Check: Is it under WORKSPACE or USER_WORKSPACE?
#         \--> NO -> Rejection (Returns False / Blocks Execution)
# ==============================================================================
def _is_within_workspace(path: Path) -> bool:
    """Verify that a target path resides inside either WORKSPACE or USER_WORKSPACE."""
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
    """Resolve an ambiguous user path into a verified workspace-confined Path object.
    
    Handles:
      - file:// URLs (with Windows drive letter correction)
      - Absolute paths pointing directly into the workspace
      - Relative paths anchored to WORKSPACE, USER_WORKSPACE, or CURRENT_DIR
    """
    raw = (raw_path or "").strip()
    if not raw:
        return None

    # Handle file:// URI scheme
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


# ==============================================================================
# SECTION 4: SAFE PATH SANITIZATION & VIDEO RESOLUTION
# ==============================================================================
# Major Aim:
#   Clean and sanitize output file stems to prevent directory traversal or
#   illegal filesystem characters, guaranteeing output lands inside WORKSPACE.
#
# Visual Example Flow:
#   User output string: "my clip! (draft 1) <final>.mp4"
#         |
#         V
#   _safe_output_video_path()
#         |
#         +--> Strips path traversal & directory separators
#         +--> Replaces non-alphanumeric chars with "_"
#         \--> Result: WORKSPACE / "my_clip_draft_1_final.mp4"
# ==============================================================================
def _safe_output_video_path(output_name: str, default_stem: str = "output") -> Path:
    """Generate a clean, sanitized output path strictly confined to WORKSPACE."""
    stem_raw = (output_name or default_stem).strip()
    stem = Path(stem_raw).name
    stem = Path(stem).stem or default_stem
    # Only allow English alphanumerics, underscores, and hyphens (zero Chinese characters)
    stem = re.sub(r"[^0-9A-Za-z_\-]+", "_", stem).strip("_")
    if not stem:
        stem = default_stem
    return (WORKSPACE / f"{stem}.mp4").resolve()


def _resolve_video_path(video_path: str) -> Path | None:
    """Locate a video file within authorized workspaces or alias patterns."""
    resolved = _resolve_workspace_input_path(video_path, must_exist=True)
    if resolved is not None:
        return resolved

    raw = (video_path or "").strip()
    if not raw:
        return None

    direct = Path(raw)
    stem = direct.stem
    # If the user passed a reference code (e.g. BV123), check if an mp4 with that stem exists
    if stem.upper().startswith("BV"):
        for root in (WORKSPACE, USER_WORKSPACE):
            alias = root / f"{stem}.mp4"
            if alias.exists():
                return alias
    return None


# ==============================================================================
# SECTION 5: VIDEO METADATA EXTRACTION FALLBACK
# ==============================================================================
# Major Aim:
#   Extract key video metrics (duration, resolution, fps) with a dual engine:
#   fast OpenCV in-process probe if available, or native FFprobe subprocess.
# ==============================================================================
def _get_video_meta(video_path: str) -> dict[str, Any]:
    """Retrieve video duration, resolution, and frame rate using OpenCV or FFprobe."""
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
