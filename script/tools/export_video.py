from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from typing import Any
from ._native_ffmpeg import (
    VideoProbe,
    _base_command,
    _encoder_args,
    _run,
    native_ffmpeg_enabled,
    probe_video,
)
from ._shared import (
    _is_within_workspace,
    _resolve_workspace_input_path,
    logger,
    tool,
    WORKSPACE,
)

# Supported export container formats
VALID_FORMATS = {"mp4", "mov", "mkv", "webm", "gif"}

# Supported aspect ratio modes
VALID_ASPECT_RATIOS = {"source", "16:9", "9:16", "1:1"}

# Preset configurations mapping to encoder speed, CRF quality, and audio bitrate
EXPORT_PRESETS: dict[str, dict[str, Any]] = {
    "high": {
        "crf": "18",
        "preset": "medium",
        "audio_bitrate": "320k",
        "description": "High quality master for YouTube, TV, or presentation delivery.",
    },
    "master": {
        "crf": "16",
        "preset": "slow",
        "audio_bitrate": "320k",
        "description": "Near-lossless production master for archiving or post-production.",
    },
    "standard": {
        "crf": "23",
        "preset": "veryfast",
        "audio_bitrate": "192k",
        "description": "Standard web quality balancing visual fidelity and download size.",
    },
    "web": {
        "crf": "23",
        "preset": "veryfast",
        "audio_bitrate": "192k",
        "description": "Optimized for web hosting and video players with faststart enabled.",
    },
    "mobile": {
        "crf": "28",
        "preset": "faster",
        "audio_bitrate": "128k",
        "max_height": 720,
        "description": "Compact file size optimized for mobile messaging and cellular data.",
    },
    "compressed": {
        "crf": "30",
        "preset": "fast",
        "audio_bitrate": "96k",
        "max_height": 480,
        "description": "Ultra-compressed video for bandwidth-constrained environments.",
    },
    "lossless": {
        "crf": "14",
        "preset": "slow",
        "audio_bitrate": "320k",
        "description": "Archival quality with minimal compression artifacts.",
    },
    "gif": {
        "fps": 15,
        "scale_width": 480,
        "description": "Animated GIF with color palette optimization for previews and social embeds.",
    },
}

# ==============================================================================
# MILESTONE 9: THE EXPORT BOX (export_video)
# ==============================================================================
# Major Aim:
#   Serve as the final export and publishing engine ("the export box") for the AI
#   video editing agent. Packages working videos into optimized, release-ready
#   deliverables with configurable quality profiles, aspect ratio re-formatting
#   (16:9 landscape, 9:16 Shorts/TikTok, 1:1 Instagram), web faststart streaming
#   optimization (+faststart), and animated GIF preview generation.
#
# Visual Example Flow:
#   Agent Request:
#     export_video(
#         video_path="temp/final_cut.mp4",
#         output_name="tiktok_clip",
#         preset="standard",
#         aspect_ratio="9:16",
#         format="mp4",
#         faststart=True
#     )
#           |
#           +--> 1. Security Check: Validates input is inside WORKSPACE
#           |
#           +--> 2. Source Media Probing:
#           |         - Probes input video dimensions (1920x1080), fps, audio
#           |
#           +--> 3. Target Path & Container Setup:
#           |         - Resolves safe destination: WORKSPACE / "exports" / "tiktok_clip.mp4"
#           |
#           +--> 4. Aspect Ratio & Video Filtergraph Construction:
#           |         - 9:16 Vertical format: Center-crop to 9:16 aspect ratio (607x1080 -> 608x1080)
#           |         - Guarantees even dimensions (divisible by 2) for H.264 compatibility
#           |
#           +--> 5. Encoder & Faststart Configuration:
#           |         - Video: libx264, crf=23, preset=veryfast, pix_fmt=yuv420p
#           |         - Audio: aac, b:a 192k
#           |         - Web Optimization: -movflags +faststart (places moov atom at start)
#           |
#           +--> 6. Native FFmpeg Execution (Silent, no window popup)
#           |
#           \--> 7. JSON Export Receipt Return to Agent:
#                     '{"status": "success", "export_path": ".../exports/tiktok_clip.mp4", "file_size_human": "4.2 MB", ...}'
# ==============================================================================


def format_file_size(size_bytes: int) -> str:
    """Format byte count into human-readable string (e.g. 1.45 MB)."""
    if size_bytes <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    size = float(size_bytes)
    while size >= 1024.0 and i < len(units) - 1:
        size /= 1024.0
        i += 1
    return f"{size:.2f} {units[i]}"


def _safe_export_path(
    output_name: str,
    format_ext: str = "mp4",
    export_subfolder: str = "exports",
    default_stem: str = "export",
) -> Path:
    """Generate a sanitized export destination path strictly confined to WORKSPACE."""
    stem_raw = (output_name or default_stem).strip()
    direct = Path(stem_raw)
    stem = direct.stem or default_stem
    # Strip non-alphanumeric characters for clean cross-platform filenames
    clean_stem = re.sub(r"[^0-9A-Za-z_\-]+", "_", stem).strip("_")
    if not clean_stem:
        clean_stem = default_stem

    clean_ext = format_ext.strip().lstrip(".").lower() or "mp4"

    # Destination folder inside WORKSPACE
    if export_subfolder:
        clean_sub = re.sub(r"[^0-9A-Za-z_\-]+", "_", export_subfolder).strip("_")
        target_dir = (WORKSPACE / clean_sub).resolve()
    else:
        target_dir = WORKSPACE.resolve()

    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = (target_dir / f"{clean_stem}.{clean_ext}").resolve()

    if not _is_within_workspace(target_path):
        raise ValueError(f"Export target path resolved outside WORKSPACE: {target_path}")

    return target_path


def build_aspect_ratio_filter(
    probe: VideoProbe,
    aspect_ratio: str,
    max_height: int | None = None,
) -> str | None:
    """Generate FFmpeg video filter string for aspect ratio cropping and scaling.

    Guarantees that dimensions are even numbers (divisible by 2) for H.264 codec compatibility.
    """
    aspect = aspect_ratio.strip().lower()
    filters: list[str] = []

    if aspect == "9:16":
        # Vertical format (TikTok / Reels / Shorts): Center crop to 9:16 aspect ratio
        filters.append("crop='min(iw,ih*9/16)':'min(ih,iw*16/9)'")
    elif aspect == "1:1":
        # Square format (Instagram posts): Center crop to 1:1 aspect ratio
        filters.append("crop='min(iw,ih)':'min(iw,ih)'")
    elif aspect == "16:9":
        # Widescreen format (YouTube / TV): Center crop to 16:9 aspect ratio
        filters.append("crop='min(iw,ih*16/9)':'min(ih,iw*9/16)'")

    # Optional downscaling constraint (e.g. For mobile preset max_height=720)
    if max_height and probe.height > max_height:
        filters.append(f"scale=-2:{max_height}")
    else:
        # Guarantee even width and height for H.264
        filters.append("scale=trunc(iw/2)*2:trunc(ih/2)*2")

    return ",".join(filters) if filters else None


def export_video_native(
    source_path: Path,
    output_path: Path,
    *,
    preset: str = "high",
    aspect_ratio: str = "source",
    format_ext: str = "mp4",
    faststart: bool = True,
    fps: float | None = None,
) -> dict[str, Any]:
    """Execute physical video export and packaging using native FFmpeg.

    Args:
        source_path: Resolved path of input video inside WORKSPACE.
        output_path: Resolved destination path for exported deliverable.
        preset: Quality configuration profile ('high', 'standard', 'mobile', 'gif', etc.).
        aspect_ratio: Target aspect ratio ('source', '16:9', '9:16', '1:1').
        format_ext: Target container format ('mp4', 'mov', 'mkv', 'webm', 'gif').
        faststart: Enable +faststart moov atom optimization for web streaming.
        fps: Optional frame rate override.

    Returns:
        Structured export receipt dictionary containing physical media metrics.
    """
    probe = probe_video(source_path)
    clean_format = format_ext.strip().lstrip(".").lower()
    clean_preset = preset.strip().lower()

    if clean_preset not in EXPORT_PRESETS:
        logger.warning("Unrecognized preset '%s', defaulting to 'standard'", clean_preset)
        clean_preset = "standard"

    preset_config = EXPORT_PRESETS[clean_preset]

    # Special handling for animated GIF export
    if clean_format == "gif" or clean_preset == "gif":
        return _export_gif_native(source_path, output_path, fps=fps)

    # General video export (MP4, MOV, MKV, WEBM)
    command = [*_base_command(), "-i", str(source_path)]

    # Step 1: Video filtering (aspect ratio cropping, scaling, framerate)
    max_h = preset_config.get("max_height")
    vf = build_aspect_ratio_filter(probe, aspect_ratio, max_height=max_h)
    if vf:
        command.extend(["-vf", vf])

    if fps and fps > 0:
        command.extend(["-r", f"{fps:.2f}"])

    # Step 2: Video encoding arguments
    crf = preset_config.get("crf", "23")
    enc_speed = preset_config.get("preset", "veryfast")

    if clean_format in {"mp4", "mov", "mkv"}:
        command.extend([
            "-c:v", "libx264",
            "-crf", crf,
            "-preset", enc_speed,
            "-pix_fmt", "yuv420p",
        ])
    elif clean_format == "webm":
        command.extend([
            "-c:v", "libvpx-vp9",
            "-crf", crf,
            "-b:v", "0",
            "-pix_fmt", "yuv420p",
        ])
    else:
        command.extend(_encoder_args())

    # Step 3: Audio encoding arguments
    has_audio = probe.has_audio
    if has_audio:
        audio_b = preset_config.get("audio_bitrate", "192k")
        if clean_format in {"mp4", "mov", "mkv"}:
            command.extend(["-c:a", "aac", "-b:a", audio_b])
        elif clean_format == "webm":
            command.extend(["-c:a", "libopus", "-b:a", audio_b])
        else:
            command.extend(["-c:a", "aac"])
    else:
        command.extend(["-an"])

    # Step 4: Web streaming optimization (moov atom relocation)
    enable_faststart = faststart and clean_format in {"mp4", "mov"}
    if enable_faststart:
        command.extend(["-movflags", "+faststart"])

    # Output destination
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command.extend(["-y", str(output_path)])

    try:
        _run(command)
    except Exception:
        output_path.unlink(missing_ok=True)
        raise

    # Step 5: Independent verification of exported artifact
    exported_probe = probe_video(output_path)
    file_size = output_path.stat().st_size
    bitrate_kbps = round((file_size * 8.0) / (exported_probe.duration * 1000.0), 1) if exported_probe.duration > 0 else 0.0

    return {
        "status": "success",
        "input_file": source_path.name,
        "export_path": str(output_path),
        "export_name": output_path.name,
        "format": clean_format,
        "preset": clean_preset,
        "aspect_ratio": aspect_ratio,
        "file_size_bytes": file_size,
        "file_size_human": format_file_size(file_size),
        "duration": round(exported_probe.duration, 3),
        "resolution": f"{exported_probe.width}x{exported_probe.height}",
        "fps": round(exported_probe.fps, 2),
        "has_audio": exported_probe.has_audio,
        "bitrate_kbps": bitrate_kbps,
        "faststart_enabled": enable_faststart,
    }


def _export_gif_native(
    source_path: Path,
    output_path: Path,
    *,
    fps: float | None = None,
) -> dict[str, Any]:
    """Export source video to high-fidelity animated GIF using 2-pass palette generation."""
    target_fps = int(fps) if fps and fps > 0 else 15
    palette_filter = (
        f"[0:v]fps={target_fps},scale=480:-1:flags=lanczos,split[s0][s1];"
        f"[s0]palettegen=max_colors=128[p];"
        f"[s1][p]paletteuse=dither=bayer"
    )

    command = [
        *_base_command(),
        "-i", str(source_path),
        "-filter_complex", palette_filter,
        "-loop", "0",
        "-y", str(output_path),
    ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        _run(command)
    except Exception:
        output_path.unlink(missing_ok=True)
        raise

    file_size = output_path.stat().st_size

    # Measure duration from source probe
    src_probe = probe_video(source_path)

    return {
        "status": "success",
        "input_file": source_path.name,
        "export_path": str(output_path),
        "export_name": output_path.name,
        "format": "gif",
        "preset": "gif",
        "aspect_ratio": "source",
        "file_size_bytes": file_size,
        "file_size_human": format_file_size(file_size),
        "duration": round(src_probe.duration, 3),
        "resolution": "480xauto",
        "fps": target_fps,
        "has_audio": False,
        "bitrate_kbps": 0.0,
        "faststart_enabled": False,
    }


@tool
def export_video(
    video_path: str,
    output_name: str = "exported_video",
    preset: str = "high",
    aspect_ratio: str = "source",
    format: str = "mp4",
    faststart: bool = True,
    fps: float | None = None,
    export_subfolder: str = "exports",
) -> str:
    """Export and package a video file with quality presets, social aspect ratios, and faststart.

    Args:
        video_path: Path or filename of the source video in WORKSPACE.
        output_name: Desired name for the exported video (without extension).
        preset: Encoding quality preset:
            'high' (master quality, CRF 18), 'standard' (web balanced, CRF 23),
            'mobile' (compressed, max 720p, CRF 28), 'lossless' (CRF 14), 'gif' (animated preview).
        aspect_ratio: Framing mode:
            'source' (original), '16:9' (widescreen YouTube), '9:16' (TikTok / Reels / Shorts),
            '1:1' (Instagram square).
        format: Deliverable container format:
            'mp4' (default), 'mov', 'mkv', 'webm', 'gif'.
        faststart: Enable +faststart moov atom placement for instant web streaming (default: True).
        fps: Optional frame rate override (e.g. 30.0, 60.0).
        export_subfolder: Destination subfolder within WORKSPACE (default: 'exports').

    Returns:
        JSON string containing the structured export receipt and media metrics,
        or a descriptive error string.
    """
    try:
        # Step 1: Security perimeter defense: resolve and confine input video to WORKSPACE
        # Line rationale: Strictly prevent access to external filesystem files outside WORKSPACE
        resolved_source = _resolve_workspace_input_path(video_path, must_exist=True)
        if resolved_source is None:
            return f"Export error: Input video is outside WORKSPACE or does not exist: {video_path}"

        # Step 2: Validate format and aspect ratio selections
        clean_format = format.strip().lstrip(".").lower()
        if clean_format not in VALID_FORMATS:
            return (
                f"Export error: Invalid format '{clean_format}'. "
                f"Supported formats: {sorted(VALID_FORMATS)}"
            )

        clean_aspect = aspect_ratio.strip().lower()
        if clean_aspect not in VALID_ASPECT_RATIOS:
            return (
                f"Export error: Invalid aspect_ratio '{clean_aspect}'. "
                f"Supported aspect ratios: {sorted(VALID_ASPECT_RATIOS)}"
            )

        # Step 3: Determine safe export destination path inside WORKSPACE
        # Line rationale: Protects against directory traversal and ensures exports land in WORKSPACE
        output_path = _safe_export_path(
            output_name=output_name,
            format_ext=clean_format,
            export_subfolder=export_subfolder,
            default_stem="exported_video",
        )

        # Step 4: Execute native FFmpeg export pipeline
        # Line rationale: Multi-threaded native FFmpeg execution delivers maximum performance with silent background runs
        receipt = export_video_native(
            resolved_source,
            output_path,
            preset=preset,
            aspect_ratio=clean_aspect,
            format_ext=clean_format,
            faststart=faststart,
            fps=fps,
        )

        logger.info(
            "Video exported successfully: %s -> %s (%s, %s, %s)",
            resolved_source.name,
            output_path.name,
            receipt["resolution"],
            receipt["preset"],
            receipt["file_size_human"],
        )

        return json.dumps(receipt, ensure_ascii=False)

    except Exception as err:
        logger.warning("Handled error in export_video: %s", err)
        return f"Export error: {err}"
