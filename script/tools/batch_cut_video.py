from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from ._native_ffmpeg import cut_video_native, native_ffmpeg_enabled, probe_video
from ._shared import (
    _resolve_workspace_input_path,
    _safe_output_video_path,
    logger,
    tool,
)

# ==============================================================================
# MILESTONE 6: THE BATCH SCISSORS (batch_cut_video)
# ==============================================================================
# Major Aim:
#   Serve as the multi-segment slicing tool ("the batch scissors") for the AI
#   video editing agent. Cuts multiple distinct time intervals from a single source
#   video in a single tool call, eliminating repeated LLM round-trips and generating
#   an indexed collection of clip artifacts ready for merging or transition effects.
#
# Visual Example Flow:
#   Agent Request:
#     batch_cut_video(
#         video_path="lecture.mp4",
#         segments=[
#             {"start_time": 10.0, "end_time": 25.0, "output_name": "intro_clip"},
#             {"start_time": 40.0, "end_time": 55.0, "output_name": "middle_clip"},
#             {"start_time": 80.0, "end_time": 95.0, "output_name": "outro_clip"},
#         ]
#     )
#           |
#           +--> 1. Security Check: Confirms "lecture.mp4" is within WORKSPACE
#           |
#           +--> 2. Input Validation: Parses segments list, validates start < end bounds
#           |
#           +--> 3. Source Duration Guard: Ensures timestamps do not exceed video duration
#           |
#           +--> 4. Precision Slicing Loop:
#           |         - Iteration 1: Cuts [10s -> 25s] -> WORKSPACE / "intro_clip.mp4"
#           |         - Iteration 2: Cuts [40s -> 55s] -> WORKSPACE / "middle_clip.mp4"
#           |         - Iteration 3: Cuts [80s -> 95s] -> WORKSPACE / "outro_clip.mp4"
#           |
#           \--> 5. JSON Return to Agent:
#                     '{"status": "success", "total_clips": 3, "clips": [...]}'
# ==============================================================================


@tool
def batch_cut_video(
    video_path: str,
    segments: list[dict[str, Any]] | str,
) -> str:
    """Cut multiple time segments from a single video in a single operation.

    Args:
        video_path: Path or filename of the source video in the workspace.
        segments: A list of segment dictionaries (or a JSON string representing one).
            Each dictionary must specify:
              - "start_time" (or "start"): float seconds
              - "end_time" (or "end"): float seconds
              - "output_name" (optional): string name for the output clip file

    Returns:
        JSON string containing status, source video path, total clip count,
        and details of all generated clips, or a descriptive error string.
    """
    try:
        # Step 1: Security perimeter defense -- verify source video exists within workspace
        # Line rationale: Strictly prevent directory traversal attacks on the source video path
        resolved_source = _resolve_workspace_input_path(video_path, must_exist=True)
        if resolved_source is None:
            return f"Batch cut error: Input video is outside WORKSPACE or does not exist: {video_path}"

        # Step 2: Handle stringified JSON input (frequently passed by LLM agents)
        # Line rationale: Large Language Models often serialize nested arguments as JSON strings
        parsed_segments: list[dict[str, Any]]
        if isinstance(segments, str):
            try:
                parsed_segments = json.loads(segments)
            except json.JSONDecodeError as err:
                return f"Batch cut error: Failed to parse segments JSON string: {err}"
        elif isinstance(segments, list):
            parsed_segments = segments
        else:
            return "Batch cut error: segments must be a list of segment dictionaries or a valid JSON string."

        if not parsed_segments:
            return "Batch cut error: segments list cannot be empty."

        # Step 3: Probe source video duration to validate timestamp boundaries
        # Line rationale: Prevents asking FFmpeg to cut past the physical end of the video file
        source_probe = probe_video(resolved_source)
        source_duration = source_probe.duration

        # Detect optional MoviePy fallback
        try:
            from moviepy.video.io.VideoFileClip import VideoFileClip
            use_moviepy = True
        except ImportError:
            use_moviepy = False

        results: list[dict[str, Any]] = []

        # Step 4: Iterate and slice each requested segment
        # Line rationale: Slicing segments in a single tool call saves tokens and reduces latency
        for index, seg in enumerate(parsed_segments, start=1):
            if not isinstance(seg, dict):
                return f"Batch cut error: Segment #{index} must be a dictionary, got {type(seg).__name__}."

            # Support flexible keys ('start_time' / 'start', 'end_time' / 'end')
            start_val = seg.get("start_time") if "start_time" in seg else seg.get("start")
            end_val = seg.get("end_time") if "end_time" in seg else seg.get("end")

            if start_val is None or end_val is None:
                return f"Batch cut error: Segment #{index} must specify both start_time and end_time."

            try:
                start = float(start_val)
                end = float(end_val)
            except (ValueError, TypeError):
                return f"Batch cut error: Segment #{index} start and end times must be numeric numbers."

            # Boundary validation
            if start < 0:
                return f"Batch cut error: Segment #{index} start_time ({start}s) cannot be negative."
            if end <= start:
                return f"Batch cut error: Segment #{index} end_time ({end}s) must be greater than start_time ({start}s)."
            if end > source_duration + 0.1:
                return (
                    f"Batch cut error: Segment #{index} end_time ({end:.2f}s) exceeds "
                    f"total source video duration ({source_duration:.2f}s)."
                )

            # Sanitize output filename
            raw_name = seg.get("output_name") or seg.get("name") or f"clip_{index}_{start:.0f}_{end:.0f}"
            output_path = _safe_output_video_path(str(raw_name), default_stem=f"clip_{index}")

            # Execute cut using Native FFmpeg (Primary) or MoviePy (Fallback)
            if native_ffmpeg_enabled() or not use_moviepy:
                actual_dur = cut_video_native(
                    resolved_source,
                    output_path,
                    start_time=start,
                    end_time=end,
                )
            else:
                with VideoFileClip(str(resolved_source)) as clip:
                    sub_clip = clip.subclipped(start, end)
                    sub_clip.write_videofile(
                        str(output_path), codec="libx264", audio_codec="aac", logger=None
                    )
                actual_dur = end - start

            results.append({
                "clip_index": index,
                "name": output_path.name,
                "path": str(output_path),
                "start": start,
                "end": end,
                "duration": round(actual_dur, 2),
            })
            logger.info("Batch cut clip #%d created: %s (%.2fs)", index, str(output_path), actual_dur)

        # Step 5: Format structured JSON response for AI agent
        return json.dumps({
            "status": "success",
            "source_video": str(resolved_source),
            "total_clips": len(results),
            "clips": results,
        }, ensure_ascii=False)

    except Exception as e:
        # Step 6: Self-healing error capture
        return f"Batch cut error: {e}"
