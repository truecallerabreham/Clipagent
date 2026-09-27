from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from ._shared import _hidden_subprocess_kwargs

# ==============================================================================
# SECTION 1: VIDEO METADATA STRUCTURE
# ==============================================================================
# Major Aim:
#   Define a typed, immutable data carrier for parsed video properties
#   (width, height, frames-per-second, duration, and audio presence).
#
# Visual Example Flow:
#   ffprobe output JSON -> VideoProbe(width=1920, height=1080, fps=30.0, ...)
# ==============================================================================
@dataclass(frozen=True, slots=True)
class VideoProbe:
    """Immutable data record holding essential video and audio container properties."""
    width: int
    height: int
    fps: float
    duration: float
    has_audio: bool


# ==============================================================================
# SECTION 2: RUNTIME CONFIGURATION & BINARY RESOLUTION
# ==============================================================================
# Major Aim:
#   Detect whether the native FFmpeg engine is enabled by environment variable,
#   and locate the executable binaries (ffmpeg, ffprobe) across PATH or overrides.
#
# Visual Example Flow:
#   _binary("FFMPEG_BIN", "ffmpeg")
#         |
#         +--> 1. Check os.environ["FFMPEG_BIN"]
#         +--> 2. Check shutil.which("ffmpeg")
#         \--> 3. Found -> Return absolute path string, or raise RuntimeError
# ==============================================================================
def native_ffmpeg_enabled() -> bool:
    """Check if the high-performance native FFmpeg pipeline is explicitly activated."""
    return (
        os.environ.get("CLIPAGENT_NATIVE_FFMPEG_PIPELINE", "").strip().lower()
    ) in {"1", "true", "yes", "on"}


def _positive_int_env(name: str, default: int) -> int:
    """Parse an environment variable as a positive integer with a safe fallback."""
    try:
        return max(1, int(os.environ.get(name, str(default))))
    except (TypeError, ValueError):
        return default


def _binary(env_name: str, executable: str) -> str:
    """Resolve an executable binary path from environment overrides or system PATH."""
    configured = os.environ.get(env_name, "").strip()
    if configured:
        return configured
    located = shutil.which(executable)
    if located:
        return located
    raise RuntimeError(f"{executable} executable was not found on PATH")


# ==============================================================================
# SECTION 3: SILENT PROCESS EXECUTION & RATE PARSING
# ==============================================================================
# Major Aim:
#   Execute FFmpeg commands silently in the background (no popup cmd windows)
#   and safely convert fraction framerates (e.g. "30000/1001") into float FPS.
#
# Visual Example Flow:
#   "30000/1001" -> _parse_rate() -> 29.97002997...
# ==============================================================================
def _run(command: Sequence[str], *, timeout: int = 1800) -> None:
    """Execute an FFmpeg command silently, raising RuntimeError on non-zero exit."""
    kwargs: dict[str, Any] = {
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": timeout,
    }
    if os.name == "nt":
        hidden = _hidden_subprocess_kwargs()
        if hidden:
            kwargs["creationflags"] = hidden["creationflags"]
            kwargs["startupinfo"] = hidden["startupinfo"]

    process = subprocess.run(list(command), **kwargs)
    if process.returncode != 0:
        detail = (process.stderr or process.stdout or "unknown ffmpeg error").strip()
        raise RuntimeError(detail[-2000:])


def _parse_rate(value: object) -> float:
    """Convert an FFmpeg fraction frame-rate string like '30/1' or '30000/1001' to float."""
    text = str(value or "0/1")
    numerator, _, denominator = text.partition("/")
    try:
        denominator_value = float(denominator or 1.0)
        return float(numerator) / denominator_value if denominator_value else 0.0
    except (TypeError, ValueError, ZeroDivisionError):
        return 0.0


# ==============================================================================
# SECTION 4: NATIVE FFPROBE INSPECTION
# ==============================================================================
# Major Aim:
#   Inspect a video file using ffprobe to extract stream dimensions, duration,
#   framerate, and audio track presence without decoding the full video file.
#
# Visual Example Flow:
#   video.mp4
#       |
#       V
#   ffprobe -show_entries format=duration:stream=... -of json
#       |
#       V
#   JSON stream payload -> VideoProbe(width, height, fps, duration, has_audio)
# ==============================================================================
def probe_video(path: Path) -> VideoProbe:
    """Probe video dimensions, frame rate, duration, and audio presence via ffprobe or cv2."""
    try:
        ffprobe_bin = _binary("FFPROBE_BIN", "ffprobe")
    except RuntimeError:
        ffprobe_bin = None

    if not ffprobe_bin:
        # Graceful fallback to OpenCV in-memory probe when ffprobe is absent
        try:
            import cv2
            if cv2 is not None:
                cap = cv2.VideoCapture(str(path))
                fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
                frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                duration = frame_count / fps if fps > 0 else 0.0
                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                cap.release()
                if width > 0 and height > 0 and duration > 0:
                    return VideoProbe(
                        width=width,
                        height=height,
                        fps=round(fps, 2),
                        duration=round(duration, 3),
                        has_audio=True,
                    )
        except Exception:
            pass
        raise RuntimeError("ffprobe executable was not found on PATH")

    command = [
        ffprobe_bin,
        "-v",
        "error",
        "-show_entries",
        "format=duration:stream=index,codec_type,width,height,avg_frame_rate,r_frame_rate",
        "-of",
        "json",
        str(path),
    ]
    kwargs: dict[str, Any] = {
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": 60,
    }
    if os.name == "nt":
        hidden = _hidden_subprocess_kwargs()
        if hidden:
            kwargs["creationflags"] = hidden["creationflags"]
            kwargs["startupinfo"] = hidden["startupinfo"]

    process = subprocess.run(command, **kwargs)
    if process.returncode != 0:
        detail = (process.stderr or process.stdout or "ffprobe failed").strip()
        raise RuntimeError(detail[-1200:])

    payload = json.loads(process.stdout or "{}")
    streams = payload.get("streams", [])
    video = next(
        (item for item in streams if item.get("codec_type") == "video"),
        None,
    )
    if not isinstance(video, dict):
        raise RuntimeError(f"no video stream found in {path}")

    width = int(video.get("width") or 0)
    height = int(video.get("height") or 0)
    fps = _parse_rate(video.get("avg_frame_rate") or video.get("r_frame_rate"))
    duration = float((payload.get("format") or {}).get("duration") or 0.0)
    if width <= 0 or height <= 0 or duration <= 0:
        raise RuntimeError(f"invalid video metadata for {path}")
    return VideoProbe(
        width=width,
        height=height,
        fps=fps if fps > 0 else 30.0,
        duration=duration,
        has_audio=any(item.get("codec_type") == "audio" for item in streams),
    )


# ==============================================================================
# SECTION 5: ENCODER CONFIGURATION & BASE COMMANDS
# ==============================================================================
# Major Aim:
#   Build standardized, optimized FFmpeg CLI arguments for video encoding
#   (H.264 video codec, yuv420p pixel format, multi-threading, preset speed).
# ==============================================================================
def _encoder_args(*, bitrate: str | None = None) -> list[str]:
    """Generate H.264 video encoding parameters with dynamic threading and presets."""
    preset = (
        os.environ.get("CLIPAGENT_FFMPEG_PRESET", "").strip()
        or "veryfast"
    )
    threads = _positive_int_env("CLIPAGENT_FFMPEG_THREADS", 8)
    args = [
        "-c:v",
        "libx264",
        "-preset",
        preset,
        "-threads",
        str(threads),
    ]
    if bitrate:
        args.extend(["-b:v", bitrate])
    else:
        crf = (
            os.environ.get("CLIPAGENT_FFMPEG_CRF", "").strip()
            or "20"
        )
        args.extend(["-crf", crf])
    args.extend(["-pix_fmt", "yuv420p"])
    return args


def _base_command() -> list[str]:
    """Construct common FFmpeg invocation arguments (overwrite, quiet banners, thread limits)."""
    filter_threads = _positive_int_env("CLIPAGENT_FFMPEG_FILTER_THREADS", 4)
    return [
        _binary("FFMPEG_BIN", "ffmpeg"),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-filter_threads",
        str(filter_threads),
        "-filter_complex_threads",
        str(filter_threads),
    ]


# ==============================================================================
# SECTION 6: NATIVE VIDEO CUTTING
# ==============================================================================
# Major Aim:
#   Perform precision video cutting directly via FFmpeg subprocess, avoiding
#   slow Python frame copying and memory leaks.
#
# Visual Example Flow:
#   source.mp4 [start=10.0s, end=25.0s]
#         |
#         V
#   ffmpeg -ss 10.000000 -t 15.000000 -i source.mp4 ... -c:v libx264 cut.mp4
#         |
#         V
#   Output: cut.mp4 (duration = 15.0s)
# ==============================================================================
def cut_video_native(
    input_path: Path,
    output_path: Path,
    *,
    start_time: float,
    end_time: float,
) -> float:
    """Trim a video file between start_time and end_time using native FFmpeg."""
    probe = probe_video(input_path)
    start = float(start_time)
    end = float(end_time)
    if start < 0 or end <= start or end > probe.duration + 0.05:
        raise ValueError(
            f"invalid cut range {start:.3f}-{end:.3f}s for {probe.duration:.3f}s video"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [*_base_command(), "-i", str(input_path), "-ss", f"{start:.6f}", "-t", f"{end - start:.6f}"]
    command.extend(["-map", "0:v:0", "-map", "0:a:0?"])
    command.extend(_encoder_args())
    command.extend(["-c:a", "aac", "-movflags", "+faststart", str(output_path)])
    try:
        _run(command)
    except Exception:
        output_path.unlink(missing_ok=True)
        raise
    return end - start


# ==============================================================================
# SECTION 7: NATIVE VIDEO EXPORT & ASPECT RATIO CONVERSION
# ==============================================================================
# Major Aim:
#   Scale, crop, and re-encode a video to match target dimensions (e.g. 1080x1920)
#   while maintaining the correct aspect ratio and adding +faststart for web playback.
#
# Visual Example Flow:
#   1920x1080 (Landscape) -> target: 1080x1920 (Portrait)
#         |
#         V
#   FFmpeg filter: scale (increase) -> crop (1080:1920) -> format=yuv420p
#         |
#         V
#   Exported portrait video file with target bitrate
# ==============================================================================
def export_video_native(
    input_path: Path,
    output_path: Path,
    *,
    target_size: tuple[int, int],
    bitrate: str = "8000k",
) -> float:
    """Scale, crop, and re-encode a video to target dimensions using native FFmpeg."""
    probe = probe_video(input_path)
    target_w, target_h = (int(target_size[0]), int(target_size[1]))
    if target_w <= 0 or target_h <= 0:
        raise ValueError(f"invalid export target size: {target_size}")

    video_filter = "setsar=1,format=yuv420p"
    if (probe.width, probe.height) != (target_w, target_h):
        video_filter = (
            f"scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
            f"crop={target_w}:{target_h},setsar=1,format=yuv420p"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [*_base_command(), "-i", str(input_path), "-map", "0:v:0", "-map", "0:a:0?"]
    command.extend(["-vf", video_filter])
    command.extend(_encoder_args(bitrate=bitrate))
    command.extend(["-c:a", "aac", "-movflags", "+faststart", str(output_path)])
    try:
        _run(command)
    except Exception:
        output_path.unlink(missing_ok=True)
        raise
    return probe.duration


# ==============================================================================
# SECTION 8: NATIVE MULTI-CLIP MERGE & AUDIO RESAMPLE
# ==============================================================================
# Major Aim:
#   Concatenate multiple video clips into a single continuous video with uniform
#   dimensions, synchronized framerate, and synthetic audio padding for silent clips.
#
# Visual Example Flow:
#   [Clip1 (with audio), Clip2 (silent), Clip3 (with audio)]
#              |
#              V  Filter Complex:
#   v0, v1, v2 scaled & cropped to match anchor orientation -> concat
#   a0, anullsrc (silence generator for clip 2), a2 resampled -> concat
#              |
#              V
#   Single seamless output video file!
# ==============================================================================
def merge_videos_native(
    input_paths: Sequence[Path],
    output_path: Path,
    *,
    target_duration: float | None,
    tolerance: float,
) -> tuple[float, int, tuple[int, int]]:
    """Concatenate multiple video files with audio normalization and aspect ratio alignment."""
    if not input_paths:
        raise ValueError("no videos were supplied")

    probes = [probe_video(path) for path in input_paths]
    landscape = [item for item in probes if item.width >= item.height]
    portrait = [item for item in probes if item.height > item.width]
    anchor = portrait[0] if portrait and len(portrait) > len(landscape) else landscape[0] if landscape else probes[0]
    target_w, target_h = anchor.width, anchor.height
    target_w -= target_w % 2
    target_h -= target_h % 2
    target_fps = max(item.fps for item in probes)

    selected: list[tuple[Path, VideoProbe, float]] = []
    remaining = float(target_duration) if target_duration and target_duration > 0 else None
    for path, probe in zip(input_paths, probes):
        if remaining is not None and remaining <= 0:
            break
        duration = probe.duration
        if remaining is not None and duration > remaining * (1.0 + float(tolerance)):
            duration = remaining
        selected.append((path, probe, duration))
        if remaining is not None:
            remaining -= duration

    if not selected:
        raise ValueError("no videos remained after duration selection")

    command = _base_command()
    for path, _, _ in selected:
        command.extend(["-i", str(path)])

    has_any_audio = any(probe.has_audio for _, probe, _ in selected)
    filters: list[str] = []
    concat_inputs: list[str] = []
    for index, (_, probe, duration) in enumerate(selected):
        filters.append(
            f"[{index}:v:0]trim=duration={duration:.6f},setpts=PTS-STARTPTS,"
            f"scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
            f"crop={target_w}:{target_h},fps={target_fps:.6f},setsar=1,format=yuv420p[v{index}]"
        )
        concat_inputs.append(f"[v{index}]")
        if has_any_audio:
            if probe.has_audio:
                filters.append(
                    f"[{index}:a:0]atrim=duration={duration:.6f},asetpts=PTS-STARTPTS,"
                    "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
                    f"aresample=async=1:first_pts=0[a{index}]"
                )
            else:
                filters.append(
                    "anullsrc=channel_layout=stereo:sample_rate=48000,"
                    f"atrim=duration={duration:.6f},asetpts=PTS-STARTPTS[a{index}]"
                )
            concat_inputs.append(f"[a{index}]")

    if has_any_audio:
        filters.append(
            "".join(concat_inputs)
            + f"concat=n={len(selected)}:v=1:a=1[vout][aout]"
        )
    else:
        filters.append(
            "".join(concat_inputs)
            + f"concat=n={len(selected)}:v=1:a=0[vout]"
        )

    command.extend(["-filter_complex", ";".join(filters), "-map", "[vout]"])
    if has_any_audio:
        command.extend(["-map", "[aout]"])
    command.extend(_encoder_args())
    if has_any_audio:
        command.extend(["-c:a", "aac"])
    command.extend(["-movflags", "+faststart", str(output_path)])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        _run(command)
    except Exception:
        output_path.unlink(missing_ok=True)
        raise

    return sum(item[2] for item in selected), len(selected), (target_w, target_h)
