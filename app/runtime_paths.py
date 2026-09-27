from __future__ import annotations

import os
import shutil
import sys
from collections.abc import Mapping
from pathlib import Path


# ==============================================================================
# SECTION 1: APPLICATION CONSTANTS
# ==============================================================================
# Major Aim:
#   Establish the canonical identity of the application and standard filenames,
#   preventing magic strings from being hardcoded across downstream modules.
#
# Visual Flow:
#   APP_NAME ("Clipagent") -> Used to construct %LOCALAPPDATA%\Clipagent and ~/.clipagent
# ==============================================================================
APP_NAME = "Clipagent"
RUNTIME_ENV_FILENAME = ".env"
EXECUTABLE_DIR_ENV_VAR = "CLIPAGENT_EXECUTABLE_DIR"


# ==============================================================================
# SECTION 2: EXECUTION MODE & BUNDLE DISCOVERY
# ==============================================================================
# Major Aim:
#   Determine whether Python is executing from raw source files or from inside
#   a compiled standalone binary (.exe) created with PyInstaller.
#
# Visual Example Flow:
#   Running via python main.py?
#         |-- YES -> sys.frozen is absent -> returns False
#         \-- NO  -> Double-clicked Clipagent.exe -> PyInstaller sets sys.frozen=True -> returns True
# ==============================================================================
def is_frozen() -> bool:
    """Check if the application is running inside a PyInstaller frozen bundle."""
    return bool(getattr(sys, "frozen", False))


# Major Aim:
#   Locate the read-only root directory containing the application's source code,
#   bundled scripts, and static resources.
#
# Visual Example Flow:
#   Development:
#     File: /project/app/runtime_paths.py
#     parents[0] = /project/app
#     parents[1] = /project/ (Returns project root)
#
#   Packaged .exe:
#     PyInstaller extracts code to temp directory sys._MEIPASS
#     Returns: Path(sys._MEIPASS)
# ==============================================================================
def get_bundle_root() -> Path:
    """Return the base directory for code and bundled resources."""
    if is_frozen():
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            return Path(meipass).resolve()
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


# Major Aim:
#   Identify the folder where the executable file or main launch script resides,
#   which serves as the preferred location for portable execution.
#
# Visual Example Flow:
#   User sets CLIPAGENT_EXECUTABLE_DIR override?
#         |-- YES -> Use custom directory
#         \-- NO  -> If frozen .exe: directory containing Clipagent.exe
#                   If source code: returns get_bundle_root()
# ==============================================================================
def get_executable_dir() -> Path:
    """Return the directory containing the physical executable or entrypoint."""
    override_dir = os.environ.get(EXECUTABLE_DIR_ENV_VAR, "").strip()
    if override_dir:
        return Path(override_dir).expanduser().resolve()
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return get_bundle_root()


# ==============================================================================
# SECTION 3: PERMISSION PROBING & RUNTIME ROOT DETERMINATION
# ==============================================================================
# Major Aim:
#   Directly test whether the current process has actual write permissions
#   in a directory by creating, writing, and deleting a probe file.
#
# Visual Example Flow:
#   Target folder: "C:\Program Files\Clipagent"
#                         |
#   Attempt:       Write dummy file ".clipagent_write_test"
#                         |
#   Result:        OS denies write (PermissionError) -> catches exception -> returns False
# ==============================================================================
def _can_write(path: Path) -> bool:
    """Empirically test write access by creating and deleting a temporary probe file."""
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".clipagent_write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except Exception:
        return False


# Major Aim:
#   Select a safe, writable directory on the filesystem for logs, temporary media
#   clips, and state, cascading through 4 priority tiers to avoid permission crashes.
#
# Visual Example Flow:
#   Tier 1: Explicit environment variable override (CLIPAGENT_RUNTIME_ROOT)?
#           |-- YES -> Use it
#           \-- NO  |
#   Tier 2: Is the executable directory writable? (Portable Mode e.g. USB or git repo)
#           |-- YES -> Use executable directory
#           \-- NO  |
#   Tier 3: Is %LOCALAPPDATA%\Clipagent writable? (Standard Windows per-user storage)
#           |-- YES -> Use %LOCALAPPDATA%\Clipagent
#           \-- NO  |
#   Tier 4: Ultimate fallback: ~/.clipagent (User home folder)
# ==============================================================================
def get_runtime_root() -> Path:
    """Resolve the writable directory where logs, temp files, and state are stored."""
    # Tier 1: User or CI explicitly specified a directory via environment variable
    env_root = os.environ.get("CLIPAGENT_RUNTIME_ROOT", "").strip()
    if env_root:
        root = Path(env_root).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        return root

    # Tier 2: Portable Mode -- if running from a writable folder (e.g. dev workspace)
    portable_root = get_executable_dir()
    if _can_write(portable_root):
        return portable_root

    # Tier 3: Standard Windows user app data directory (avoids Program Files restriction)
    local_appdata = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if local_appdata:
        appdata_root = (Path(local_appdata) / APP_NAME).resolve()
        if _can_write(appdata_root):
            return appdata_root

    # Tier 4: User home directory fallback (~/.clipagent)
    fallback_root = (Path.home() / f".{APP_NAME.lower()}").resolve()
    fallback_root.mkdir(parents=True, exist_ok=True)
    return fallback_root


# ==============================================================================
# SECTION 4: PATH COMPOSITION HELPERS
# ==============================================================================
# Major Aim:
#   Provide clean path builder functions that anchor relative subpaths
#   to either bundle_root (code/assets) or runtime_root (writable data).
#
# Visual Example Flow:
#   resource_path("script", "dep")  -> BUNDLE_ROOT/script/dep  (Read-only assets)
#   runtime_path("temp", "cuts")    -> RUNTIME_ROOT/temp/cuts  (Writable data)
# ==============================================================================
def resource_path(*parts: str) -> Path:
    """Resolve a path relative to the read-only bundle directory."""
    return get_bundle_root().joinpath(*parts)


def runtime_path(*parts: str) -> Path:
    """Resolve a path relative to the writable runtime directory."""
    return get_runtime_root().joinpath(*parts)


def runtime_env_path() -> Path:
    """Return the absolute path to the runtime .env configuration file."""
    return runtime_path(RUNTIME_ENV_FILENAME)


# ==============================================================================
# SECTION 5: CUSTOM .ENV SERIALIZATION (ZERO DEPENDENCY)
# ==============================================================================
# Major Aim:
#   Read, parse, escape, and persist KEY=VALUE pairs in .env configuration
#   files without requiring external packages like python-dotenv.
#
# Visual Example Flow:
#   Raw file line: CLIPAGENT_API_KEY="sk-12345" # Main key
#                         |
#   Parser:        Splits on "=", strips quotes, ignores comments
#                         |
#   Output dict:   {"CLIPAGENT_API_KEY": "sk-12345"}
# ==============================================================================
def load_runtime_env_file(*, override: bool = False) -> Path:
    """Load settings from the runtime .env into os.environ without overwriting active vars."""
    env_path = runtime_env_path()
    for key, value in read_runtime_env_file().items():
        if override or key not in os.environ:
            os.environ[key] = value
    return env_path


def read_runtime_env_file() -> dict[str, str]:
    """Parse the runtime .env file into a dictionary of string key-value pairs."""
    env_path = runtime_env_path()
    if not env_path.exists():
        return {}
    payload: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        payload[key] = _unquote_env_value(value.strip())
    return payload


def _quote_env_value(value: str) -> str:
    """Safely escape newlines and double quotes for .env serialization."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


def _unquote_env_value(value: str) -> str:
    """Unescape quoted values and strip trailing inline comments."""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        text = value[1:-1]
        text = text.replace("\\n", "\n")
        text = text.replace('\\"', '"')
        text = text.replace("\\\\", "\\")
        return text
    comment_index = value.find(" #")
    if comment_index >= 0:
        return value[:comment_index].rstrip()
    return value


def write_runtime_env_file(values: Mapping[str, str | None]) -> Path:
    """Write or update configuration pairs in the runtime .env file."""
    env_path = runtime_env_path()
    current = read_runtime_env_file()
    merged = dict(current)
    order = list(current.keys())

    for key in values:
        if key not in order:
            order.append(key)

    for key, raw_value in values.items():
        value = str(raw_value or "").strip()
        if value:
            merged[key] = value
        else:
            merged.pop(key, None)

    lines = [f"{key}={_quote_env_value(merged[key])}" for key in order if key in merged]
    env_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return env_path


# ==============================================================================
# SECTION 6: DIRECTORY SCAFFOLDING & RESOURCE SEEDING
# ==============================================================================
# Major Aim:
#   Create all required temporary and persistent directory structures on disk
#   before any media processing tools or loggers attempt to open files.
#
# Visual Example Flow:
#   ensure_runtime_dirs()
#         |
#   Creates: app_state/, logs/, temp/, user_temp/, memory_experience/
# ==============================================================================
def ensure_runtime_dirs() -> dict[str, Path]:
    """Ensure all required runtime directories exist on the filesystem."""
    directories = {
        "app_state": runtime_path("app_state"),
        "jobs": runtime_path("app_state", "jobs"),
        "logs": runtime_path("logs"),
        "runtime_logs": runtime_path("runtime_logs"),
        "temp": runtime_path("temp"),
        "user_temp": runtime_path("user_temp"),
        "memory_experience": runtime_path("memory_experience"),
    }
    for path in directories.values():
        path.mkdir(parents=True, exist_ok=True)
    return directories


def _seed_runtime_tree(relative_dir: str) -> None:
    """Copy bundled template files (like prompt heuristics) to the runtime root if missing."""
    source_dir = resource_path(relative_dir)
    target_dir = runtime_path(relative_dir)
    if not source_dir.exists() or not source_dir.is_dir():
        return

    for source in source_dir.rglob("*"):
        if not source.is_file():
            continue
        relative = source.relative_to(source_dir)
        target = target_dir / relative
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())


# ==============================================================================
# SECTION 7: BINARY RESOLUTION & PATH INJECTION
# ==============================================================================
# Major Aim:
#   Locate external executable binaries (ffmpeg, yt-dlp) across bundled project
#   directories and system PATH, automatically prepending them to the OS environment.
#
# Visual Example Flow:
#   Looking for "ffmpeg.exe":
#     1. Check script/dep/windows/ffmpeg.exe (Bundled binary)
#     2. Check app/bin/windows/ffmpeg.exe
#     3. Check system PATH via shutil.which("ffmpeg.exe")
#     4. Export FFMPEG_BIN = "C:/.../ffmpeg.exe"
# ==============================================================================
def _prepend_path(entries: list[Path]) -> None:
    """Prepend directories to the process's PATH environment variable without duplicates."""
    current = os.environ.get("PATH", "")
    existing = [item for item in current.split(os.pathsep) if item]
    normalized_existing = {str(Path(item).resolve()) for item in existing if Path(item).exists()}

    ordered: list[str] = []
    for entry in entries:
        if not entry.exists():
            continue
        resolved = str(entry.resolve())
        if resolved in normalized_existing or resolved in ordered:
            continue
        ordered.append(resolved)

    if ordered:
        os.environ["PATH"] = os.pathsep.join([*ordered, current] if current else ordered)


def _binary_search_roots() -> list[Path]:
    """Return search locations for bundled binaries in order of descending priority."""
    runtime_root = get_runtime_root()
    bundle_root = get_bundle_root()

    def _script_binary_dirs(root: Path) -> list[Path]:
        return [
            root / "script" / "dep" / "windows",
            root / "script" / "lib" / "windows",
            root / "script" / "dep",
            root / "script" / "lib",
        ]

    candidates = [
        *_script_binary_dirs(runtime_root),
        *_script_binary_dirs(bundle_root),
        runtime_root / "app" / "bin" / "windows",
        bundle_root / "app" / "bin" / "windows",
        runtime_root / "app" / "bin",
        bundle_root / "app" / "bin",
        runtime_root,
        bundle_root,
    ]
    return candidates


def resolve_binary(*names: str) -> Path | None:
    """Find the first matching executable binary by checking bundled directories then system PATH."""
    candidates: list[Path] = []
    for root in _binary_search_roots():
        for name in names:
            if not name:
                continue
            candidates.append(root / name)

    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()

    for name in names:
        if not name:
            continue
        found = shutil.which(name)
        if found:
            return Path(found).resolve()
    return None


# ==============================================================================
# SECTION 8: CENTRAL RUNTIME BOOTSTRAPPER
# ==============================================================================
# Major Aim:
#   Execute the full bootstrap sequence: create folders, load .env, locate
#   binaries, and export standard environment variables.
# ==============================================================================
def configure_runtime_environment() -> None:
    """Bootstrap the complete operating environment for Clipagent."""
    ensure_runtime_dirs()
    bundle_root = get_bundle_root()
    runtime_root = get_runtime_root()

    os.environ.setdefault("CLIPAGENT_BUNDLE_ROOT", str(bundle_root))
    os.environ.setdefault("CLIPAGENT_RUNTIME_ROOT", str(runtime_root))
    load_runtime_env_file(override=False)

    _prepend_path(_binary_search_roots())

    ffmpeg_names = ("ffmpeg.exe", "ffmpeg") if os.name == "nt" else ("ffmpeg",)
    yt_dlp_names = ("yt-dlp.exe", "yt-dlp.cmd", "yt-dlp") if os.name == "nt" else ("yt-dlp",)

    ffmpeg_path = resolve_binary(*ffmpeg_names)
    yt_dlp_path = resolve_binary(*yt_dlp_names)

    if ffmpeg_path is not None:
        os.environ.setdefault("FFMPEG_BIN", str(ffmpeg_path))
    if yt_dlp_path is not None:
        os.environ.setdefault("CLIPAGENT_YTDLP_BIN", str(yt_dlp_path))

    _seed_runtime_tree("memory_experience")
