from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from ._native_ffmpeg import (
    VideoProbe,
    native_ffmpeg_enabled,
    probe_video,
)
from ._shared import (
    _resolve_workspace_input_path,
    _safe_output_video_path,
    logger,
    tool,
    WORKSPACE,
)
from .add_transition import VALID_TRANSITIONS, add_transition_native

# Style presets mapped to rotational transition types and recommended default durations
STYLE_PRESETS: dict[str, dict[str, Any]] = {
    "cinematic": {
        "transitions": ["fade", "dissolve", "fadeblack"],
        "default_duration": 1.0,
        "description": "Soft atmospheric dissolves and fades, ideal for storytelling and mood transitions.",
    },
    "action": {
        "transitions": ["slideleft", "wipeleft", "smoothleft", "slideright"],
        "default_duration": 0.5,
        "description": "Fast-paced directional slides and wipes, ideal for sports, action, or dynamic montages.",
    },
    "subtle": {
        "transitions": ["dissolve", "fade"],
        "default_duration": 0.75,
        "description": "Minimal, non-distracting dissolves that maintain narrative continuity.",
    },
    "wipe": {
        "transitions": ["wipeleft", "wiperight", "wipeup", "wipedown"],
        "default_duration": 0.75,
        "description": "Classic directional wipe wipes.",
    },
    "slide": {
        "transitions": ["slideleft", "slideright", "slideup", "slidedown"],
        "default_duration": 0.6,
        "description": "Push and slide motion transitions.",
    },
}

# ==============================================================================
# MILESTONE 8: THE TRANSITION PLANNER (plan_transition_for_clips)
# ==============================================================================
# Major Aim:
#   Serve as the intelligent transition planning and sequencing engine ("the transition
#   planner") for the AI video editing agent. Analyzes an ordered sequence of video
#   clips, verifies workspace confinement, probes physical durations and resolutions,
#   calculates exact frame-accurate timeline offsets ($T_{offset} = \sum D_{prev} - \sum T_{prev}$),
#   enforces overlap bounds ($T_{in} + T_{out} < D_{clip}$), adjusts pacing safely,
#   and outputs a structured, execution-ready blueprint (with optional native multi-clip rendering).
#
# Visual Example Flow:
#   Agent Request:
#     plan_transition_for_clips(
#         clips=["intro.mp4", "action.mp4", "outro.mp4"],
#         style="cinematic",
#         default_duration=1.0
#     )
#           |
#           +--> 1. Security Check: Resolves each clip strictly inside WORKSPACE
#           |
#           +--> 2. Physical Probe & Metric Inspection:
#           |         - Clip 0 (intro):  dur=4.0s, res=1280x720, fps=30.0, audio=True
#           |         - Clip 1 (action): dur=5.0s, res=1280x720, fps=30.0, audio=True
#           |         - Clip 2 (outro):  dur=6.0s, res=1280x720, fps=30.0, audio=True
#           |
#           +--> 3. Transition Selection & Overlap Constraints Guard:
#           |         - Boundary 0 (intro -> action): "fade", dur=1.0s
#           |         - Boundary 1 (action -> outro): "dissolve", dur=1.0s
#           |         - Constraint Check on Clip 1: (1.0s in + 1.0s out = 2.0s) < 5.0s (PASS!)
#           |
#           +--> 4. Frame-Accurate Timeline Math:
#           |         - Clip 0:    [0.0s  -> 4.0s]
#           |         - Trans 0:   Offset = 4.0s - 1.0s = 3.0s (dur=1.0s)
#           |         - Clip 1:    [3.0s  -> 8.0s]  (starts at Trans 0 offset)
#           |         - Trans 1:   Offset = (3.0s + 5.0s) - 1.0s = 7.0s (dur=1.0s)
#           |         - Clip 2:    [7.0s  -> 13.0s] (starts at Trans 1 offset)
#           |         - Total:     4.0 + 5.0 + 6.0 - (1.0 + 1.0) = 13.0s
#           |
#           +--> 5. Optional Multi-Clip Native Rendering (if render_video=True):
#           |         - Executes chained native FFmpeg transitions across all clips
#           |         - Generates verified output video in WORKSPACE
#           |
#           \--> 6. JSON Blueprint Return to Agent:
#                     '{"status": "success", "total_planned_duration": 13.0, "clips": [...], "transitions": [...]}'
# ==============================================================================


def _parse_clips_input(clips_input: list[str] | str) -> list[str]:
    """Parse and normalize clips input from either a list, JSON array string, or comma-separated string."""
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
        # Fallback to comma-separated values
        return [part.strip() for part in cleaned.split(",") if part.strip()]
    return []


def plan_clip_transitions(
    clip_paths: list[Path],
    style: str = "cinematic",
    default_transition: str = "fade",
    default_duration: float = 1.0,
    auto_adjust: bool = True,
) -> dict[str, Any]:
    """Calculate the structured transition blueprint and timeline for an ordered list of clips.

    Args:
        clip_paths: Resolved Path objects for all input clips inside WORKSPACE.
        style: Transition style preset name ('cinematic', 'action', 'subtle', 'wipe', 'slide', 'custom').
        default_transition: Fallback transition type if style is 'custom' or unrecognized.
        default_duration: Target transition overlap duration in seconds.
        auto_adjust: If True, automatically scales down transition durations if clips are too short.

    Returns:
        Dictionary containing the complete timeline blueprint, clips metadata,
        transition parameters, and consistency diagnostics.
    """
    if not clip_paths:
        raise ValueError("Clip list cannot be empty.")

    # Step 1: Probe each clip to inspect physical durations, resolution, and fps
    # Line rationale: Must know physical media bounds before computing timeline geometry
    probes: list[VideoProbe] = []
    for p in clip_paths:
        try:
            probes.append(probe_video(p))
        except Exception as err:
            raise ValueError(f"Failed to probe clip '{p.name}': {err}") from err

    clip_count = len(probes)
    diagnostics: list[str] = []

    # Consistency diagnostics: check for resolution or frame rate discrepancies
    resolutions = {f"{pb.width}x{pb.height}" for pb in probes}
    if len(resolutions) > 1:
        diagnostics.append(
            f"Resolution mismatch detected across clips: {sorted(resolutions)}. "
            f"Clips will be scaled and standardized during rendering."
        )
    framerates = {round(pb.fps, 1) for pb in probes}
    if len(framerates) > 1:
        diagnostics.append(
            f"Framerate variance detected: {sorted(framerates)} FPS. "
            f"Framerates will be aligned to maximum ({max(framerates)} FPS)."
        )
    audio_states = [pb.has_audio for pb in probes]
    if any(audio_states) and not all(audio_states):
        diagnostics.append(
            "Audio mismatch: Some clips contain audio streams while others are silent. "
            "Silent clips will have synthetic silence padded for clean audio crossfading."
        )

    # Step 2: Handle single-clip edge case (0 transitions needed)
    if clip_count == 1:
        single_dur = probes[0].duration
        return {
            "status": "success",
            "style": style,
            "clip_count": 1,
            "transition_count": 0,
            "total_raw_duration": round(single_dur, 3),
            "total_planned_duration": round(single_dur, 3),
            "overlap_duration_saved": 0.0,
            "clips": [
                {
                    "index": 0,
                    "name": clip_paths[0].name,
                    "path": str(clip_paths[0]),
                    "duration": round(single_dur, 3),
                    "resolution": f"{probes[0].width}x{probes[0].height}",
                    "fps": round(probes[0].fps, 2),
                    "has_audio": probes[0].has_audio,
                    "timeline_start": 0.0,
                    "timeline_end": round(single_dur, 3),
                }
            ],
            "transitions": [],
            "diagnostics": diagnostics or ["Single clip provided; no transitions required."],
        }

    # Step 3: Determine transition types based on style preset
    normalized_style = style.strip().lower()
    preset = STYLE_PRESETS.get(normalized_style)
    if preset is not None:
        style_pool = preset["transitions"]
        target_duration = default_duration if default_duration > 0 else preset["default_duration"]
    else:
        # Fallback / custom style
        cleaned_default = default_transition.strip().lower()
        if cleaned_default not in VALID_TRANSITIONS:
            diagnostics.append(f"Unrecognized default transition '{cleaned_default}', defaulting to 'fade'.")
            cleaned_default = "fade"
        style_pool = [cleaned_default]
        target_duration = default_duration if default_duration > 0 else 1.0

    # Step 4: Plan transitions between each consecutive clip pair
    # Line rationale: Iterate through N-1 boundaries and calculate safe overlap durations
    planned_transitions: list[dict[str, Any]] = []
    transition_durations: list[float] = []

    for i in range(clip_count - 1):
        c1 = probes[i]
        c2 = probes[i + 1]
        t_type = style_pool[i % len(style_pool)]
        t_dur = float(target_duration)
        adjusted = False
        adj_reason = None

        # Maximum allowed transition duration: cannot exceed 45% of either adjacent clip
        # Line rationale: Ensures middle clips don't collapse into 100% transition without visible body
        max_safe_t = min(c1.duration * 0.45, c2.duration * 0.45)
        if max_safe_t <= 0.05:
            raise ValueError(
                f"Clip '{clip_paths[i].name}' ({c1.duration:.2f}s) or '{clip_paths[i+1].name}' ({c2.duration:.2f}s) "
                f"is too short for a transition."
            )

        if t_dur > max_safe_t:
            if auto_adjust:
                adj_reason = (
                    f"Requested duration {t_dur:.2f}s exceeded 45% threshold of adjacent clips "
                    f"({c1.duration:.2f}s and {c2.duration:.2f}s). Clamped to {max_safe_t:.2f}s."
                )
                t_dur = round(max_safe_t, 2)
                adjusted = True
                from_name = clip_paths[i].name
                to_name = clip_paths[i + 1].name
                diagnostics.append(f"Transition {i} ({from_name} -> {to_name}): {adj_reason}")
            else:
                raise ValueError(
                    f"Transition duration ({t_dur}s) is too long for clips '{clip_paths[i].name}' "
                    f"({c1.duration:.2f}s) and '{clip_paths[i+1].name}' ({c2.duration:.2f}s). "
                    f"Maximum safe transition is {max_safe_t:.2f}s."
                )

        transition_durations.append(t_dur)
        planned_transitions.append({
            "index": i,
            "from_clip": clip_paths[i].name,
            "to_clip": clip_paths[i + 1].name,
            "transition_type": t_type,
            "duration": round(t_dur, 3),
            "timeline_offset": 0.0,  # Will be populated in Step 5
            "adjusted": adjusted,
            "adjustment_reason": adj_reason,
        })

    # Step 5: Compute frame-accurate global timeline positioning
    # Line rationale: Timeline offset = previous clip end minus current transition overlap
    clips_plan: list[dict[str, Any]] = []
    current_timeline_time = 0.0

    for i in range(clip_count):
        clip_dur = probes[i].duration
        clip_start = current_timeline_time
        clip_end = clip_start + clip_dur

        clips_plan.append({
            "index": i,
            "name": clip_paths[i].name,
            "path": str(clip_paths[i]),
            "duration": round(clip_dur, 3),
            "resolution": f"{probes[i].width}x{probes[i].height}",
            "fps": round(probes[i].fps, 2),
            "has_audio": probes[i].has_audio,
            "timeline_start": round(clip_start, 3),
            "timeline_end": round(clip_end, 3),
        })

        if i < clip_count - 1:
            # Transition begins at clip_end minus transition_duration
            t_dur = transition_durations[i]
            t_offset = clip_end - t_dur
            planned_transitions[i]["timeline_offset"] = round(t_offset, 3)
            # The next clip begins appearing exactly at the transition offset!
            current_timeline_time = t_offset

    total_raw_duration = sum(pb.duration for pb in probes)
    total_overlap_saved = sum(transition_durations)
    total_planned_duration = total_raw_duration - total_overlap_saved

    return {
        "status": "success",
        "style": normalized_style,
        "clip_count": clip_count,
        "transition_count": len(planned_transitions),
        "total_raw_duration": round(total_raw_duration, 3),
        "total_planned_duration": round(total_planned_duration, 3),
        "overlap_duration_saved": round(total_overlap_saved, 3),
        "clips": clips_plan,
        "transitions": planned_transitions,
        "diagnostics": diagnostics or ["All timeline and transition constraints successfully verified."],
    }


def execute_planned_transitions_native(
    plan: dict[str, Any],
    output_path: Path,
) -> float:
    """Execute multi-clip sequence with planned transitions using native FFmpeg.

    Uses iterative pairwise blending with add_transition_native to ensure robust
    audio synchronization, format alignment, and flawless timeline consistency.

    Args:
        plan: The dictionary blueprint returned by plan_clip_transitions.
        output_path: Output destination video file.

    Returns:
        The physical duration of the final rendered video.
    """
    clips_info = plan["clips"]
    transitions_info = plan["transitions"]
    clip_count = len(clips_info)

    if clip_count == 0:
        raise ValueError("Cannot render empty plan.")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Single clip: copy / transcode directly
    if clip_count == 1:
        src = Path(clips_info[0]["path"])
        import shutil
        shutil.copy2(src, output_path)
        return float(clips_info[0]["duration"])

    # Iterative pairwise rendering: blend clip 0 and clip 1 -> temp_1, then temp_1 and clip 2 -> temp_2, etc.
    # Line rationale: Guarantees rock-solid rendering across any number of clips without exceeding filter limits
    temp_files: list[Path] = []
    try:
        current_source = Path(clips_info[0]["path"])

        for i, trans in enumerate(transitions_info):
            next_clip = Path(clips_info[i + 1]["path"])
            is_last = (i == len(transitions_info) - 1)
            target = output_path if is_last else output_path.parent / f"_temp_trans_stage_{i}_{output_path.name}"

            if not is_last:
                temp_files.append(target)

            logger.info(
                "Rendering transition %d/%d (%s -> %s, type=%s, dur=%.2fs)",
                i + 1,
                len(transitions_info),
                current_source.name,
                next_clip.name,
                trans["transition_type"],
                trans["duration"],
            )

            add_transition_native(
                current_source,
                next_clip,
                target,
                transition_type=trans["transition_type"],
                transition_duration=trans["duration"],
            )
            current_source = target

        # Verify output file
        final_probe = probe_video(output_path)
        return final_probe.duration

    finally:
        # Clean up intermediate temporary files
        for tmp in temp_files:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass


@tool
def plan_transition_for_clips(
    clips: list[str] | str,
    style: str = "cinematic",
    default_transition: str = "fade",
    default_duration: float = 1.0,
    auto_adjust: bool = True,
    render_video: bool = False,
    output_name: str | None = None,
) -> str:
    """Plan and sequence transitions across multiple video clips with timeline calculation.

    Args:
        clips: Ordered list of video filenames or paths in WORKSPACE (or a JSON array string).
        style: Transition style preset ('cinematic', 'action', 'subtle', 'wipe', 'slide', 'custom').
        default_transition: Fallback transition type if style is 'custom' (default: 'fade').
        default_duration: Desired transition overlap duration in seconds (default: 1.0s).
        auto_adjust: Automatically scale down transition durations if clips are too short (default: True).
        render_video: If True, physically renders the multi-clip sequence using native FFmpeg (default: False).
        output_name: Output filename if render_video=True (default: 'planned_sequence').

    Returns:
        JSON string containing the structured transition blueprint, clips metadata,
        timeline coordinates, diagnostics, and rendered video details if requested.
    """
    try:
        # Step 1: Parse and normalize clips list input
        # Line rationale: LLM agents may send lists, JSON strings, or comma-separated lists
        parsed_clip_names = _parse_clips_input(clips)
        if not parsed_clip_names:
            return "Transition planner error: clips list cannot be empty."

        # Step 2: Security perimeter defense: resolve and confine all clips to WORKSPACE
        # Line rationale: Strictly prevent directory traversal attacks across all input clips
        resolved_clip_paths: list[Path] = []
        for name in parsed_clip_names:
            resolved = _resolve_workspace_input_path(name, must_exist=True)
            if resolved is None:
                return f"Transition planner error: Clip is outside WORKSPACE or does not exist: {name}"
            resolved_clip_paths.append(resolved)

        # Step 3: Compute structured transition blueprint and timeline
        # Line rationale: Validates duration bounds, calculates offsets, and assigns transition types
        plan = plan_clip_transitions(
            resolved_clip_paths,
            style=style,
            default_transition=default_transition,
            default_duration=float(default_duration),
            auto_adjust=auto_adjust,
        )

        # Step 4: Optional physical rendering of the planned sequence
        # Line rationale: When the agent approves the plan, it can render the final sequence in one call
        if render_video:
            out_stem = output_name or f"planned_{plan['style']}_sequence"
            safe_output = _safe_output_video_path(out_stem, default_stem="planned_sequence")
            rendered_dur = execute_planned_transitions_native(plan, safe_output)
            plan["rendered_video_path"] = str(safe_output)
            plan["rendered_video_name"] = safe_output.name
            plan["rendered_duration"] = round(rendered_dur, 3)

        return json.dumps(plan, ensure_ascii=False)

    except Exception as err:
        logger.warning("Handled error in plan_transition_for_clips: %s", err)
        return f"Transition planner error: {err}"
