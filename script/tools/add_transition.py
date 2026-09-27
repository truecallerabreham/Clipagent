from __future__ import annotations

import json
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
    _resolve_workspace_input_path,
    _safe_output_video_path,
    logger,
    tool,
)

# Supported standard FFmpeg xfade transition types
VALID_TRANSITIONS = {
    "fade",
    "fadeblack",
    "fadewhite",
    "wipeleft",
    "wiperight",
    "wipeup",
    "wipedown",
    "slideleft",
    "slideright",
    "slideup",
    "slidedown",
    "circlecrop",
    "rectcrop",
    "dissolve",
    "pixelize",
    "radial",
    "smoothleft",
    "smoothright",
}

# ==============================================================================
# MILESTONE 7: THE CROSSFADE (add_transition)
# ==============================================================================
# Major Aim:
#   Serve as the cinematic transition tool ("the crossfade") for the AI video
#   editing agent. Blends two video clips with visual transitions (fade, wipe,
#   slide, dissolve) and audio crossfading, replacing harsh jump cuts with
#   professional cinematic transitions.
#
# Visual Example Flow:
#   Agent Request:
#     add_transition(
#         video1_path="scene1.mp4",       # Duration = 4.0s
#         video2_path="scene2.mp4",       # Duration = 5.0s
#         transition_type="fade",         # Crossfade transition
#         transition_duration=1.0,        # 1.0 second blend
#         output_name="scene1_to_scene2"
#     )
#           |
#           +--> 1. Security Check: Confirms both clips reside in WORKSPACE
#           |
#           +--> 2. Video Metric Probing:
#           |         - Probe Clip 1: dur=4.0s, res=1280x720, fps=30.0
#           |         - Probe Clip 2: dur=5.0s, res=1280x720, fps=30.0
#           |
#           +--> 3. Overlap Math & Offset Calculation:
#           |         - transition_offset = duration1 - transition_duration = 4.0 - 1.0 = 3.0s
#           |         - expected_total_duration = 4.0 + 5.0 - 1.0 = 8.0s (due to 1.0s overlap)
#           |
#           +--> 4. FFmpeg Filtergraph Construction:
#           |         Video: [v0][v1]xfade=transition=fade:duration=1.0:offset=3.0[vout]
#           |         Audio: [0:a][1:a]acrossfade=d=1.0[aout]
#           |
#           \--> 5. JSON Return to Agent:
#                     '{"status": "success", "path": ".../scene1_to_scene2.mp4", "duration": 8.0, "transition": "fade"}'
# ==============================================================================


def add_transition_native(
    video1_path: Path,
    video2_path: Path,
    output_path: Path,
    *,
    transition_type: str = "fade",
    transition_duration: float = 1.0,
) -> float:
    """Execute video and audio transition between two video clips using native FFmpeg."""
    probe1 = probe_video(video1_path)
    probe2 = probe_video(video2_path)

    # Validate transition duration against input video lengths
    t_dur = float(transition_duration)
    if t_dur <= 0:
        raise ValueError(f"transition_duration must be positive, got {t_dur}s.")
    if t_dur >= probe1.duration:
        raise ValueError(
            f"transition_duration ({t_dur}s) must be shorter than video1 duration ({probe1.duration:.2f}s)."
        )
    if t_dur >= probe2.duration:
        raise ValueError(
            f"transition_duration ({t_dur}s) must be shorter than video2 duration ({probe2.duration:.2f}s)."
        )

    # Standardize transition type name (fallback to 'fade' if unrecognized)
    t_type = transition_type.strip().lower()
    if t_type not in VALID_TRANSITIONS:
        logger.warning("Unrecognized transition '%s', defaulting to 'fade'", t_type)
        t_type = "fade"

    # Match target dimensions and framerate to the first clip (anchor)
    target_w = probe1.width - (probe1.width % 2)
    target_h = probe1.height - (probe1.height % 2)
    target_fps = max(probe1.fps, probe2.fps)

    # Offset: the exact second where clip 1 starts blending into clip 2
    offset = max(0.0, probe1.duration - t_dur)
    expected_duration = probe1.duration + probe2.duration - t_dur

    # Build video filtergraph: scale both inputs to identical dimensions before xfade
    video_filters = [
        f"[0:v]scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
        f"crop={target_w}:{target_h},setsar=1,fps={target_fps:.6f},format=yuv420p[v0]",
        f"[1:v]scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
        f"crop={target_w}:{target_h},setsar=1,fps={target_fps:.6f},format=yuv420p[v1]",
        f"[v0][v1]xfade=transition={t_type}:duration={t_dur:.6f}:offset={offset:.6f}[vout]",
    ]

    # Build audio filtergraph: crossfade audio if both have audio
    has_audio1 = probe1.has_audio
    has_audio2 = probe2.has_audio
    has_audio = has_audio1 or has_audio2

    audio_filters: list[str] = []
    if has_audio:
        if has_audio1 and has_audio2:
            audio_filters.append(
                f"[0:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[a0];"
                f"[1:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[a1];"
                f"[a0][a1]acrossfade=d={t_dur:.6f}:c1=tri:c2=tri[aout]"
            )
        elif has_audio1:
            # Clip 2 is silent: fade out clip 1 audio at transition point
            audio_filters.append(
                f"[0:a]afade=t=out:st={offset:.6f}:d={t_dur:.6f},aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[aout]"
            )
        else:
            # Clip 1 is silent: fade in clip 2 audio
            audio_filters.append(
                f"[1:a]afade=t=in:st=0:d={t_dur:.6f},aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[aout]"
            )

    all_filters = video_filters + audio_filters
    command = [*_base_command(), "-i", str(video1_path), "-i", str(video2_path)]
    command.extend(["-filter_complex", ";".join(all_filters), "-map", "[vout]"])
    if has_audio:
        command.extend(["-map", "[aout]"])

    command.extend(_encoder_args())
    if has_audio:
        command.extend(["-c:a", "aac"])
    command.extend(["-movflags", "+faststart", str(output_path)])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        _run(command)
    except Exception:
        output_path.unlink(missing_ok=True)
        raise

    return expected_duration


@tool
def add_transition(
    video1_path: str,
    video2_path: str,
    transition_type: str = "fade",
    transition_duration: float = 1.0,
    output_name: str = "transition",
) -> str:
    """Apply a visual and audio transition effect between two consecutive video clips.

    Args:
        video1_path: First video (outgoing scene) located inside the workspace.
        video2_path: Second video (incoming scene) located inside the workspace.
        transition_type: Transition style (default: 'fade'). Options include:
            'fade', 'fadeblack', 'fadewhite', 'wipeleft', 'wiperight', 'wipeup',
            'wipedown', 'slideleft', 'slideright', 'circlecrop', 'dissolve', 'pixelize'.
        transition_duration: Transition overlap length in seconds (default: 1.0s).
            Must be shorter than both video clips.
        output_name: Name for the generated transition video (without .mp4 extension).

    Returns:
        JSON string containing status, output path, total duration, and transition type,
        or a descriptive error string.
    """
    try:
        # Step 1: Security perimeter checks for both input videos
        # Line rationale: Strictly prevent access to external filesystem paths outside workspace
        resolved_v1 = _resolve_workspace_input_path(video1_path, must_exist=True)
        if resolved_v1 is None:
            return f"Transition error: Video 1 is outside WORKSPACE or does not exist: {video1_path}"

        resolved_v2 = _resolve_workspace_input_path(video2_path, must_exist=True)
        if resolved_v2 is None:
            return f"Transition error: Video 2 is outside WORKSPACE or does not exist: {video2_path}"

        # Step 2: Sanitize output filename to guarantee safe storage in WORKSPACE
        # Line rationale: Eliminates spaces, quotes, and directory traversal patterns
        output_path = _safe_output_video_path(output_name or "transition", default_stem="transition")

        # Step 3: Execute native FFmpeg xfade transition pipeline
        # Line rationale: FFmpeg C-level xfade filter executes with zero memory leaks and maximum performance
        total_duration = add_transition_native(
            resolved_v1,
            resolved_v2,
            output_path,
            transition_type=transition_type,
            transition_duration=transition_duration,
        )

        logger.info(
            "Transition '%s' (%.1fs) applied between %s and %s -> %s (%.2fs)",
            transition_type,
            transition_duration,
            resolved_v1.name,
            resolved_v2.name,
            output_path.name,
            total_duration,
        )

        # Step 4: Serialize structured response for AI agent
        return json.dumps({
            "status": "success",
            "path": str(output_path),
            "duration": round(total_duration, 2),
            "transition": transition_type.strip().lower(),
            "transition_duration": round(float(transition_duration), 2),
            "video1": resolved_v1.name,
            "video2": resolved_v2.name,
        }, ensure_ascii=False)

    except Exception as e:
        # Step 5: Self-healing error capture
        # Line rationale: Returns descriptive string error so the AI agent can diagnose and self-heal
        return f"Transition error: {e}"
