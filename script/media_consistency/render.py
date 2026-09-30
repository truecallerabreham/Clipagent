from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

from script.tools._native_ffmpeg import (
    VideoProbe,
    _base_command,
    _encoder_args,
    _hidden_subprocess_kwargs,
    _run,
    native_ffmpeg_enabled,
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
from .probe import (
    MediaInspection,
    check_media_consistency,
    format_bytes_human,
    probe_media_deep,
)

# ==============================================================================
# MILESTONE 11: THE STANDARDIZER (media_consistency/render.py)
# ==============================================================================
# Major Aim:
#   Serve as the physical conforming engine ("the standardizer") for the AI video
#   editing agent. Transforms raw, heterogeneous video clips into uniform, normalized
#   intermediate assets (matching resolution, constant frame rate, yuv420p pixel
#   format, 48kHz stereo AAC audio, and physically normalized orientation).
#   Guarantees that all processed clips pass the post-standardization audit as
#   100% "Concat-Ready" for zero-artifact cutting, merging, and transition pipelines.
#
# Visual Example Flow:
#   Input Inconsistent Clips:
#     - Clip 1: 1920x1080 @ 30fps (48kHz audio)
#     - Clip 2: 1280x720  @ 24fps (44.1kHz audio)   [Needs scale, fps, audio resample]
#     - Clip 3: 720x1280  @ 30fps (Silent, rotated) [Needs scale, synthetic audio, rotation fix]
#           |
#           V
#   standardize_media_clips(clips)
#           |
#           +--> 1. Pre-Flight Consistency Audit:
#           |         - Analyzes clips via Milestone 10 probe
#           |         - Derives master standard: 1920x1080 @ 30.0 fps, 48000Hz stereo AAC
#           |         - Obtains exact per-clip Standardization Recipes
#           |
#           +--> 2. Physical Transformation Pipeline (Native FFmpeg):
#           |         - Clip 1: Already matches master -> Fast stream copy or minimal encode
#           |         - Clip 2: Scales 720p -> 1080p (pillarbox/pad), conforms fps 24 -> 30, resamples audio 44.1kHz -> 48kHz
#           |         - Clip 3: Fixes rotation, centers in 1080p, generates synthetic 48kHz stereo silence
#           |
#           +--> 3. Post-Standardization Quality Verification:
#           |         - Forensic probe on all generated assets in temp/standardized/
#           |         - Confirms: is_consistent = True, is_concat_ready = True
#           |
#           \--> 4. JSON Standardization Receipt:
#                     '{"status": "success", "is_concat_ready": true, "standardized_clips": [...]}'
# ==============================================================================


@dataclass(frozen=True, slots=True)
class StandardizedClipInfo:
    """Record holding metadata of a standardized, concat-ready media asset."""
    original_name: str
    standardized_name: str
    standardized_path: str
    file_size_human: str
    duration: float
    resolution: str
    fps: float
    has_audio: bool
    was_reencoded: bool


def _safe_standardized_output_path(
    source_name: str,
    output_subfolder: str = "standardized",
    prefix: str = "std_",
) -> Path:
    """Resolve a safe destination path for a standardized clip strictly inside WORKSPACE."""
    clean_stem = Path(source_name).stem
    clean_stem = re.sub(r"[^0-9A-Za-z_\-]+", "_", clean_stem).strip("_") or "clip"
    out_name = f"{prefix}{clean_stem}.mp4"

    if output_subfolder:
        clean_sub = re.sub(r"[^0-9A-Za-z_\-]+", "_", output_subfolder).strip("_")
        target_dir = (WORKSPACE / clean_sub).resolve()
    else:
        target_dir = (WORKSPACE / "standardized").resolve()

    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = (target_dir / out_name).resolve()

    if not _is_within_workspace(target_path):
        raise ValueError(f"Standardized target path resolved outside WORKSPACE: {target_path}")

    return target_path


def standardize_single_clip(
    source_path: Path,
    output_path: Path,
    recipe: dict[str, Any],
    master_standard: dict[str, Any],
) -> StandardizedClipInfo:
    """Transform a single video clip to match the master standard using native FFmpeg.

    Args:
        source_path: Physical path of the input raw clip in WORKSPACE.
        output_path: Target destination path in WORKSPACE / standardized.
        recipe: The per-clip standardization recipe computed by probe.py.
        master_standard: The target master profile (resolution, fps, sample_rate, codecs).

    Returns:
        StandardizedClipInfo record with verified post-render metrics.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    target_w = master_standard["width"]
    target_h = master_standard["height"]
    target_fps = master_standard["fps"]
    target_sr = master_standard["sample_rate"]

    needs_reencode = recipe.get("needs_reencode", False)

    # If clip already matches all master standard parameters perfectly: fast copy
    if not needs_reencode and source_path.resolve() != output_path.resolve():
        logger.info("Clip %s already matches master standard. Copying directly.", source_path.name)
        shutil.copy2(source_path, output_path)
        post_probe = probe_video(output_path)
        return StandardizedClipInfo(
            original_name=source_path.name,
            standardized_name=output_path.name,
            standardized_path=str(output_path),
            file_size_human=format_bytes_human(output_path.stat().st_size),
            duration=round(post_probe.duration, 3),
            resolution=f"{post_probe.width}x{post_probe.height}",
            fps=round(post_probe.fps, 2),
            has_audio=post_probe.has_audio,
            was_reencoded=False,
        )

    # Full Conforming Transformation Pipeline via Native FFmpeg
    command = [*_base_command(), "-i", str(source_path)]

    # Handle synthetic audio input if the clip is silent and needs audio
    needs_synthetic_audio = recipe.get("needs_synthetic_audio", False)
    if needs_synthetic_audio:
        # Input 1: infinite synthetic silence
        command.extend([
            "-f", "lavfi",
            "-i", f"anullsrc=channel_layout=stereo:sample_rate={target_sr}",
        ])

    # Video Filters: aspect ratio padding/scaling, pixel format, fps, rotation
    video_filters: list[str] = []
    if recipe.get("needs_rotation_fix"):
        # Transpose filters to physically rotate pixels
        rotation = recipe.get("rotation", 0)
        if rotation == 90:
            video_filters.append("transpose=1")
        elif rotation == 180:
            video_filters.append("transpose=2,transpose=2")
        elif rotation == 270:
            video_filters.append("transpose=2")

    # Scaling with aspect ratio preservation and black letterbox/pillarbox padding
    video_filters.append(
        f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,"
        f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2,"
        f"setsar=1"
    )
    # Standardize pixel format and constant frame rate (CFR)
    video_filters.append("format=yuv420p")
    video_filters.append(f"fps={target_fps:.2f}")

    command.extend(["-vf", ",".join(video_filters)])

    # Video Encoding parameters
    command.extend([
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "22",
        "-pix_fmt", "yuv420p",
        "-metadata:s:v:0", "rotate=0",  # Clear orientation display matrix tag
    ])

    # Audio Filters and Encoding
    if needs_synthetic_audio:
        # Map video from input 0, synthetic audio from input 1
        command.extend(["-map", "0:v", "-map", "1:a"])
        command.extend(["-c:a", "aac", "-b:a", "192k", "-shortest"])
    else:
        has_audio = recipe.get("has_audio", True)
        if has_audio:
            audio_filter = "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo"
            command.extend(["-af", audio_filter])
            command.extend(["-c:a", "aac", "-b:a", "192k"])
        else:
            command.extend(["-an"])

    command.extend(["-movflags", "+faststart", "-y", str(output_path)])

    try:
        _run(command)
    except Exception:
        output_path.unlink(missing_ok=True)
        raise

    post_probe = probe_video(output_path)
    return StandardizedClipInfo(
        original_name=source_path.name,
        standardized_name=output_path.name,
        standardized_path=str(output_path),
        file_size_human=format_bytes_human(output_path.stat().st_size),
        duration=round(post_probe.duration, 3),
        resolution=f"{post_probe.width}x{post_probe.height}",
        fps=round(post_probe.fps, 2),
        has_audio=post_probe.has_audio,
        was_reencoded=True,
    )


def standardize_media_clips_native(
    source_paths: Sequence[Path],
    *,
    target_resolution: str | None = None,
    target_fps: float | None = None,
    output_subfolder: str = "standardized",
) -> dict[str, Any]:
    """Execute physical standardization across multiple clips and verify post-conforming quality.

    Args:
        source_paths: Resolved paths of raw input video clips in WORKSPACE.
        target_resolution: Explicit target resolution (e.g. '1920x1080'), or None to auto-derive.
        target_fps: Explicit target frame rate (e.g. 30.0), or None to auto-derive.
        output_subfolder: Subfolder in WORKSPACE to place standardized assets.

    Returns:
        Structured standardization receipt containing before/after metrics and post-audit results.
    """
    if not source_paths:
        raise ValueError("Cannot standardize empty clip sequence.")

    # Step 1: Pre-Flight Forensic Inspection & Consistency Audit via Milestone 10 Probe
    inspections: list[MediaInspection] = []
    for p in source_paths:
        inspections.append(probe_media_deep(p))

    pre_report = check_media_consistency(
        inspections,
        target_resolution=target_resolution,
        target_fps=target_fps,
    )

    master_standard = pre_report["recommended_standard"]
    recipes = pre_report["recipes"]

    # Step 2: Physical Standardizing Render Loop
    standardized_records: list[StandardizedClipInfo] = []
    output_paths: list[Path] = []

    for i, p in enumerate(source_paths):
        out_path = _safe_standardized_output_path(
            p.name,
            output_subfolder=output_subfolder,
            prefix=f"std_{i+1:02d}_",
        )
        recipe = recipes[i]
        # Attach raw stream flags for the render worker
        recipe["rotation"] = inspections[i].rotation
        recipe["has_audio"] = inspections[i].has_audio

        logger.info(
            "Standardizing clip %d/%d: %s -> %s (reencode=%s)",
            i + 1,
            len(source_paths),
            p.name,
            out_path.name,
            recipe.get("needs_reencode", False),
        )

        record = standardize_single_clip(
            source_path=p,
            output_path=out_path,
            recipe=recipe,
            master_standard=master_standard,
        )
        standardized_records.append(record)
        output_paths.append(out_path)

    # Step 3: Post-Standardization Quality Verification Audit
    # Line rationale: Must independently inspect the rendered outputs to verify 100% Concat-Readiness
    post_inspections: list[MediaInspection] = []
    for out_p in output_paths:
        post_inspections.append(probe_media_deep(out_p))

    post_audit = check_media_consistency(post_inspections)

    return {
        "status": "success",
        "total_input_clips": len(source_paths),
        "standardized_clips_count": len(standardized_records),
        "output_directory": str(output_paths[0].parent),
        "master_standard": master_standard,
        "is_concat_ready": post_audit["is_concat_ready"],
        "post_audit_consistent": post_audit["is_consistent"],
        "post_audit_discrepancies": post_audit["discrepancies"],
        "standardized_clips": [asdict(r) for r in standardized_records],
    }


def _parse_clips_list(clips_input: list[str] | str) -> list[str]:
    """Parse list of clip names from python list, JSON string, or comma-separated string."""
    if isinstance(clips_input, list):
        return [str(c).strip() for c in clips_input if str(c).strip()]
    if isinstance(clips_input, str):
        cleaned = clips_input.strip()
        if cleaned.startswith("[") and cleaned.endswith("]"):
            try:
                parsed = json.loads(cleaned)
                if isinstance(parsed, list):
                    return [str(c).strip() for c in parsed if str(c).strip()]
            except json.JSONDecodeError:
                pass
        return [part.strip() for part in cleaned.split(",") if part.strip()]
    return []


@tool
def standardize_media_clips(
    video_paths: list[str] | str,
    target_resolution: str | None = None,
    target_fps: float | None = None,
    output_subfolder: str = "standardized",
) -> str:
    """Standardize a collection of heterogeneous video clips into uniform, concat-ready assets.

    Conforms resolutions with aspect-ratio letterbox/pillarbox padding, harmonizes
    framerates to constant frame rate (CFR), normalizes display rotation, unifies audio
    to 48kHz stereo AAC, and synthesizes missing audio for silent clips.

    Args:
        video_paths: List or JSON string of video filenames/paths located in WORKSPACE.
        target_resolution: Target master resolution (e.g. '1920x1080', '1280x720').
            If omitted, automatically standardizes to the highest resolution among the clips.
        target_fps: Target master frame rate (e.g. 30.0, 60.0).
            If omitted, automatically standardizes to the highest frame rate among the clips.
        output_subfolder: Destination subfolder inside WORKSPACE (default: 'standardized').

    Returns:
        JSON string containing the standardization receipt, output file paths,
        and post-render concat-readiness verification results.
    """
    try:
        # Step 1: Parse and normalize input clips list
        # Line rationale: LLM agents may provide Python lists, JSON array strings, or comma-delimited strings
        parsed_clip_names = _parse_clips_list(video_paths)
        if not parsed_clip_names:
            return "Standardizer error: video_paths cannot be empty."

        # Step 2: Security perimeter check: resolve and confine all input files to WORKSPACE
        # Line rationale: Strictly prevent directory traversal attacks on arbitrary filesystem files
        resolved_paths: list[Path] = []
        for name in parsed_clip_names:
            resolved = _resolve_workspace_input_path(name, must_exist=True)
            if resolved is None:
                return f"Standardizer error: Input video is outside WORKSPACE or does not exist: {name}"
            resolved_paths.append(resolved)

        # Step 3: Execute native standardization pipeline
        # Line rationale: Multi-stream normalization produces broadcast-grade, perfectly conformed clips
        receipt = standardize_media_clips_native(
            resolved_paths,
            target_resolution=target_resolution,
            target_fps=target_fps,
            output_subfolder=output_subfolder,
        )

        return json.dumps(receipt, ensure_ascii=False)

    except Exception as err:
        logger.warning("Handled error in standardize_media_clips: %s", err)
        return f"Standardizer error: {err}"
