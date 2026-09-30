from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

from script.tools._native_ffmpeg import (
    VideoProbe,
    _binary,
    _hidden_subprocess_kwargs,
    _parse_rate,
    probe_video,
)
from script.tools._shared import (
    _is_within_workspace,
    _resolve_workspace_input_path,
    logger,
    tool,
    WORKSPACE,
    USER_WORKSPACE,
)

# ==============================================================================
# MILESTONE 10: THE VIDEO INSPECTOR (media_consistency/probe.py)
# ==============================================================================
# Major Aim:
#   Serve as the forensic quality inspector ("the video inspector") for the AI
#   video editing agent. Performs deep multi-stream inspection across collections
#   of raw video clips, audits media consistency (resolutions, framerates, audio
#   sample rates, channel layouts, pixel formats, and orientation metadata),
#   determines whether clips are "Concat-Ready" for zero-re-encoding stream copy,
#   and calculates an exact, executable Standardization Recipe for Phase 3.
#
# Visual Example Flow:
#   Input Clips: ["clip1.mp4" (1080p, 60fps, 48kHz), "clip2.mp4" (720p, 24fps, 44.1kHz, silent)]
#         |
#         V
#   inspect_media_consistency()
#         |
#         +--> 1. Deep Multi-Stream Inspection:
#         |       - Clip 1: 1920x1080, 60.0 fps, yuv420p, audio=48000Hz stereo
#         |       - Clip 2: 1280x720, 24.0 fps, yuv420p, audio=None (silent!)
#         |
#         +--> 2. Consistency Audit & Diagnostic Scan:
#         |       - Resolution mismatch: 1920x1080 vs 1280x720
#         |       - Framerate variance: 60.0 fps vs 24.0 fps
#         |       - Audio track asymmetry: Clip 1 has audio, Clip 2 is silent!
#         |       - is_concat_ready = False (Direct stream-copy would cause severe desync/corruption)
#         |
#         +--> 3. Target Profile Determination:
#         |       - Recommended standard: 1920x1080 @ 60fps, yuv420p, 48000Hz stereo AAC
#         |
#         \--> 4. Executable Standardization Recipe Generation:
#                 - Clip 1 Recipe: Conforming not needed (already matches master target)
#                 - Clip 2 Recipe: Scale 720p -> 1080p, resample fps 24 -> 60, synthesize 48kHz audio track
# ==============================================================================


@dataclass(frozen=True, slots=True)
class MediaInspection:
    """Immutable data record holding full container and stream-level media properties."""
    file_path: str
    file_name: str
    file_size_bytes: int
    file_size_human: str
    format_name: str
    duration: float
    bitrate_kbps: float
    has_video: bool
    has_audio: bool
    width: int
    height: int
    resolution: str
    aspect_ratio: str
    fps: float
    is_vfr: bool
    video_codec: str
    pix_fmt: str
    rotation: int
    audio_codec: str
    sample_rate: int
    channels: int
    channel_layout: str


def format_bytes_human(size_bytes: int) -> str:
    """Format byte count into human-readable string (e.g. 2.45 MB)."""
    if size_bytes <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB"]
    i = 0
    size = float(size_bytes)
    while size >= 1024.0 and i < len(units) - 1:
        size /= 1024.0
        i += 1
    return f"{size:.2f} {units[i]}"


def probe_media_deep(file_path: Path) -> MediaInspection:
    """Perform comprehensive multi-stream forensic inspection of a media file via ffprobe.

    Extracts container properties, video stream metrics, variable-framerate flags,
    rotation display tags, and audio stream properties.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Media file does not exist: {file_path}")

    file_size = file_path.stat().st_size

    try:
        ffprobe_bin = _binary("FFPROBE_BIN", "ffprobe")
    except RuntimeError:
        ffprobe_bin = None

    if not ffprobe_bin:
        # Fallback to base probe when ffprobe executable is not available on PATH
        base = probe_video(file_path)
        gcd = math_gcd(base.width, base.height) if base.width > 0 and base.height > 0 else 1
        aspect = f"{base.width // gcd}:{base.height // gcd}" if gcd > 0 else "16:9"
        bitrate_kbps = round((file_size * 8.0) / (base.duration * 1000.0), 1) if base.duration > 0 else 0.0

        return MediaInspection(
            file_path=str(file_path),
            file_name=file_path.name,
            file_size_bytes=file_size,
            file_size_human=format_bytes_human(file_size),
            format_name=file_path.suffix.lstrip(".").lower() or "mp4",
            duration=round(base.duration, 3),
            bitrate_kbps=bitrate_kbps,
            has_video=True,
            has_audio=base.has_audio,
            width=base.width,
            height=base.height,
            resolution=f"{base.width}x{base.height}",
            aspect_ratio=aspect,
            fps=round(base.fps, 2),
            is_vfr=False,
            video_codec="h264",
            pix_fmt="yuv420p",
            rotation=0,
            audio_codec="aac" if base.has_audio else "",
            sample_rate=48000 if base.has_audio else 0,
            channels=2 if base.has_audio else 0,
            channel_layout="stereo" if base.has_audio else "",
        )

    # Command: extract format and all stream details in JSON
    command = [
        ffprobe_bin,
        "-v", "error",
        "-show_format",
        "-show_streams",
        "-of", "json",
        str(file_path),
    ]

    kwargs: dict[str, Any] = {
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": 30,
    }
    if os.name == "nt":
        hidden = _hidden_subprocess_kwargs()
        if hidden:
            kwargs["creationflags"] = hidden["creationflags"]
            kwargs["startupinfo"] = hidden["startupinfo"]

    proc = subprocess.run(command, **kwargs)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "ffprobe failed").strip()
        raise RuntimeError(f"Deep probe failed for {file_path.name}: {detail[-500:]}")

    payload = json.loads(proc.stdout or "{}")
    streams = payload.get("streams", [])
    format_info = payload.get("format", {})

    # Extract Video Stream
    v_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    has_video = v_stream is not None

    width = int(v_stream.get("width") or 0) if v_stream else 0
    height = int(v_stream.get("height") or 0) if v_stream else 0
    v_codec = str(v_stream.get("codec_name") or "") if v_stream else ""
    pix_fmt = str(v_stream.get("pix_fmt") or "") if v_stream else ""

    # Parse Frame Rate & Detect Variable Frame Rate (VFR)
    fps = 30.0
    is_vfr = False
    if v_stream:
        avg_fps = _parse_rate(v_stream.get("avg_frame_rate"))
        r_fps = _parse_rate(v_stream.get("r_frame_rate"))
        fps = avg_fps if avg_fps > 0 else (r_fps if r_fps > 0 else 30.0)
        # If r_frame_rate and avg_frame_rate differ by more than 0.1, clip is variable frame rate
        if avg_fps > 0 and r_fps > 0 and abs(avg_fps - r_fps) > 0.1:
            is_vfr = True

    # Parse Rotation / Orientation (e.g. mobile vertical video tagged with rotation)
    rotation = 0
    if v_stream:
        # Check stream tags
        tags = v_stream.get("tags", {})
        if "rotate" in tags:
            try:
                rotation = int(tags["rotate"]) % 360
            except (ValueError, TypeError):
                pass
        # Check side data list (display matrix)
        for side in v_stream.get("side_data_list", []):
            if "rotation" in side:
                try:
                    rotation = int(side["rotation"]) % 360
                except (ValueError, TypeError):
                    pass

    # Extract Audio Stream
    a_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
    has_audio = a_stream is not None

    a_codec = str(a_stream.get("codec_name") or "") if a_stream else ""
    sample_rate = int(a_stream.get("sample_rate") or 0) if a_stream else 0
    channels = int(a_stream.get("channels") or 0) if a_stream else 0
    channel_layout = str(a_stream.get("channel_layout") or ("stereo" if channels == 2 else "mono" if channels == 1 else "")) if a_stream else ""

    # Calculate Aspect Ratio
    gcd = math_gcd(width, height) if width > 0 and height > 0 else 1
    aspect = f"{width // gcd}:{height // gcd}" if gcd > 0 else "16:9"

    # Container duration and bitrate
    duration = float(format_info.get("duration") or (v_stream.get("duration") if v_stream else 0.0) or 0.0)
    format_name = str(format_info.get("format_name") or file_path.suffix.lstrip(".")).split(",")[0].strip()
    bitrate_kbps = round((file_size * 8.0) / (duration * 1000.0), 1) if duration > 0 else 0.0

    return MediaInspection(
        file_path=str(file_path),
        file_name=file_path.name,
        file_size_bytes=file_size,
        file_size_human=format_bytes_human(file_size),
        format_name=format_name,
        duration=round(duration, 3),
        bitrate_kbps=bitrate_kbps,
        has_video=has_video,
        has_audio=has_audio,
        width=width,
        height=height,
        resolution=f"{width}x{height}",
        aspect_ratio=aspect,
        fps=round(fps, 2),
        is_vfr=is_vfr,
        video_codec=v_codec,
        pix_fmt=pix_fmt,
        rotation=rotation,
        audio_codec=a_codec,
        sample_rate=sample_rate,
        channels=channels,
        channel_layout=channel_layout,
    )


def math_gcd(a: int, b: int) -> int:
    """Compute greatest common divisor using Euclidean algorithm."""
    while b:
        a, b = b, a % b
    return abs(a)


def check_media_consistency(
    inspections: Sequence[MediaInspection],
    *,
    target_resolution: str | None = None,
    target_fps: float | None = None,
) -> dict[str, Any]:
    """Audit a sequence of media files for format discrepancies and compute standardization recipes.

    Args:
        inspections: Sequence of MediaInspection objects for all clips in the project.
        target_resolution: Explicit master resolution (e.g. '1920x1080'), or None to auto-derive.
        target_fps: Explicit master frame rate (e.g. 30.0), or None to auto-derive.

    Returns:
        Dictionary containing consistency verdict, concat-readiness, detected discrepancies,
        recommended master standard, and per-clip standardization recipes.
    """
    if not inspections:
        raise ValueError("Cannot check consistency of empty media list.")

    clip_count = len(inspections)
    discrepancies: list[str] = []

    # 1. Audit Resolutions
    resolutions = {item.resolution for item in inspections}
    if len(resolutions) > 1:
        discrepancies.append(
            f"Resolution mismatch: Found multiple resolutions {sorted(resolutions)}. "
            f"Clips must be scaled to a uniform frame size before concatenation."
        )

    # 2. Audit Framerates & Variable Frame Rates
    framerates = {item.fps for item in inspections}
    if len(framerates) > 1:
        discrepancies.append(
            f"Framerate variance: Found differing frame rates {sorted(framerates)} FPS. "
            f"Must be normalized to prevent video stutter or timeline drift."
        )
    vfr_clips = [item.file_name for item in inspections if item.is_vfr]
    if vfr_clips:
        discrepancies.append(
            f"Variable frame rate (VFR) detected in: {vfr_clips}. "
            f"Clips must be resampled to constant frame rate (CFR) to maintain audio sync."
        )

    # 3. Audit Audio Tracks (Presence, Sample Rate, Channels)
    audio_states = {item.has_audio for item in inspections}
    if len(audio_states) > 1:
        discrepancies.append(
            "Audio presence asymmetry: Some clips contain audio streams while others are completely silent. "
            "Silent clips require synthetic silence padded to prevent stream muxing failure."
        )

    audio_sample_rates = {item.sample_rate for item in inspections if item.has_audio}
    if len(audio_sample_rates) > 1:
        discrepancies.append(
            f"Audio sample rate mismatch: Found {sorted(audio_sample_rates)} Hz. "
            f"Differing sample rates cause audio clicks, pitch warping, or desynchronization."
        )

    channel_layouts = {item.channel_layout for item in inspections if item.has_audio}
    if len(channel_layouts) > 1:
        discrepancies.append(
            f"Audio channel layout mismatch: Found {sorted(channel_layouts)}. "
            f"Must be standardized to uniform stereo (2 channels)."
        )

    # 4. Audit Pixel Formats & Codecs
    pix_formats = {item.pix_fmt for item in inspections if item.pix_fmt}
    if len(pix_formats) > 1:
        discrepancies.append(
            f"Pixel format mismatch: Found {sorted(pix_formats)}. "
            f"All clips should use standardized yuv420p for maximum hardware compatibility."
        )

    # 5. Audit Orientation & Display Rotation
    rotated_clips = [f"{item.file_name} ({item.rotation}°)" for item in inspections if item.rotation != 0]
    if rotated_clips:
        discrepancies.append(
            f"Display rotation detected in: {rotated_clips}. "
            f"Orientation tags must be physically normalized to 0° to prevent sideways playback."
        )

    # Concat-Ready check: Can these clips be merged via zero-re-encoding stream copy?
    is_consistent = len(discrepancies) == 0
    is_concat_ready = (
        is_consistent
        and len(resolutions) == 1
        and len(framerates) == 1
        and not vfr_clips
        and not rotated_clips
        and len(audio_states) <= 1
        and len(audio_sample_rates) <= 1
    )

    # Determine Recommended Master Standard
    # Resolution standard: user-specified or mode / maximum
    if target_resolution:
        target_w, target_h = map(int, target_resolution.strip().lower().split("x"))
    else:
        # Default to highest resolution in the set
        max_clip = max(inspections, key=lambda x: x.width * x.height)
        target_w, target_h = max_clip.width, max_clip.height

    # Framerate standard: user-specified or maximum
    if target_fps and target_fps > 0:
        master_fps = float(target_fps)
    else:
        master_fps = max(item.fps for item in inspections)

    recommended_standard = {
        "width": target_w,
        "height": target_h,
        "resolution": f"{target_w}x{target_h}",
        "fps": master_fps,
        "video_codec": "h264",
        "pix_fmt": "yuv420p",
        "audio_codec": "aac",
        "sample_rate": 48000,
        "channels": 2,
        "channel_layout": "stereo",
        "audio_bitrate": "192k",
    }

    # Generate Per-Clip Standardization Recipes
    recipes: list[dict[str, Any]] = []
    for item in inspections:
        needs_scale = (item.width != target_w or item.height != target_h)
        needs_fps = (abs(item.fps - master_fps) > 0.05 or item.is_vfr)
        needs_pix_fmt = (item.pix_fmt != "yuv420p")
        needs_rotation = (item.rotation != 0)

        needs_audio_resample = (item.has_audio and item.sample_rate != 48000)
        needs_audio_channel = (item.has_audio and item.channels != 2)
        needs_synthetic_audio = (not item.has_audio and any(x.has_audio for x in inspections))

        needs_reencode = (
            needs_scale
            or needs_fps
            or needs_pix_fmt
            or needs_rotation
            or needs_audio_resample
            or needs_audio_channel
            or needs_synthetic_audio
        )

        # Build suggested FFmpeg filters for Phase 3 Standardizer
        video_filters: list[str] = []
        if needs_rotation:
            if item.rotation == 90:
                video_filters.append("transpose=1")
            elif item.rotation == 180:
                video_filters.append("transpose=2,transpose=2")
            elif item.rotation == 270:
                video_filters.append("transpose=2")

        if needs_scale:
            video_filters.append(
                f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,"
                f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2"
            )
        if needs_pix_fmt or needs_scale:
            video_filters.append("format=yuv420p")
        if needs_fps:
            video_filters.append(f"fps={master_fps:.2f}")

        audio_filters: list[str] = []
        if item.has_audio and (needs_audio_resample or needs_audio_channel):
            audio_filters.append("aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo")

        recipes.append({
            "file_name": item.file_name,
            "file_path": item.file_path,
            "needs_reencode": needs_reencode,
            "needs_scale": needs_scale,
            "needs_fps_conforming": needs_fps,
            "needs_pix_fmt_conversion": needs_pix_fmt,
            "needs_rotation_fix": needs_rotation,
            "needs_audio_resample": needs_audio_resample,
            "needs_audio_channel_conforming": needs_audio_channel,
            "needs_synthetic_audio": needs_synthetic_audio,
            "suggested_video_filter": ",".join(video_filters) if video_filters else None,
            "suggested_audio_filter": ",".join(audio_filters) if audio_filters else None,
        })

    return {
        "status": "success",
        "clip_count": clip_count,
        "is_consistent": is_consistent,
        "is_concat_ready": is_concat_ready,
        "discrepancies": discrepancies,
        "recommended_standard": recommended_standard,
        "clips": [asdict(item) for item in inspections],
        "recipes": recipes,
    }


def _parse_input_video_list(videos_input: list[str] | str) -> list[str]:
    """Parse list of video paths from list, JSON string, or comma-delimited string."""
    if isinstance(videos_input, list):
        return [str(v).strip() for v in videos_input if str(v).strip()]
    if isinstance(videos_input, str):
        cleaned = videos_input.strip()
        if cleaned.startswith("[") and cleaned.endswith("]"):
            try:
                parsed = json.loads(cleaned)
                if isinstance(parsed, list):
                    return [str(v).strip() for v in parsed if str(v).strip()]
            except json.JSONDecodeError:
                pass
        return [part.strip() for part in cleaned.split(",") if part.strip()]
    return []


@tool
def inspect_media_consistency(
    video_paths: list[str] | str,
    target_resolution: str | None = None,
    target_fps: float | None = None,
) -> str:
    """Inspect and audit media consistency across one or more video clips.

    Extracts multi-stream metadata, detects format discrepancies (resolution, fps,
    variable frame rate, rotation, audio sample rate, channels), verifies concat-readiness,
    and returns an actionable standardization recipe.

    Args:
        video_paths: List or JSON string of video filenames/paths inside WORKSPACE.
        target_resolution: Optional desired master resolution (e.g. '1920x1080', '1280x720').
        target_fps: Optional desired master frame rate (e.g. 30.0, 60.0).

    Returns:
        JSON string containing the consistency audit report, discrepancy list,
        recommended standard, and per-clip standardization recipes.
    """
    try:
        # Step 1: Parse input clips list
        # Line rationale: Large Language Models frequently pass JSON strings or comma-separated lists
        parsed_names = _parse_input_video_list(video_paths)
        if not parsed_names:
            return "Consistency probe error: video_paths cannot be empty."

        # Step 2: Security perimeter defense: resolve and confine all files to WORKSPACE
        # Line rationale: Strictly prevent directory traversal attacks on arbitrary system files
        resolved_paths: list[Path] = []
        for name in parsed_names:
            resolved = _resolve_workspace_input_path(name, must_exist=True)
            if resolved is None:
                return f"Consistency probe error: Video is outside WORKSPACE or does not exist: {name}"
            resolved_paths.append(resolved)

        # Step 3: Deep Multi-Stream Forensic Inspection for each file
        # Line rationale: Probes all container and stream attributes with zero guess-work
        inspections: list[MediaInspection] = []
        for path in resolved_paths:
            inspections.append(probe_media_deep(path))

        # Step 4: Consistency Audit and Standardization Recipe Calculation
        # Line rationale: Compares all streams across files and generates precise conforming plan
        report = check_media_consistency(
            inspections,
            target_resolution=target_resolution,
            target_fps=target_fps,
        )

        return json.dumps(report, ensure_ascii=False)

    except Exception as err:
        logger.warning("Handled error in inspect_media_consistency: %s", err)
        return f"Consistency probe error: {err}"
