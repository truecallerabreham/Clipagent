from __future__ import annotations

import json
from pathlib import Path
from ._native_ffmpeg import cut_video_native, native_ffmpeg_enabled
from ._shared import (
    _resolve_workspace_input_path,
    _safe_output_video_path,
    tool,
)

# ==============================================================================
# MILESTONE 4: THE SCISSORS (cut_video)
# ==============================================================================
# Major Aim:
#   Serve as the primary cutting tool ("the digital scissors") for the AI video
#   editing agent. Slices a specified time segment [start_time, end_time] from
#   an input video file and saves the clean trimmed clip into the task WORKSPACE.
#
# Visual Example Flow:
#   User/Agent Request:
#     cut_video(input_path="raw_lecture.mp4", start_time=10.0, end_time=25.5, output_name="highlight")
#           |
#           +--> 1. Security Check: Confirms "raw_lecture.mp4" is inside WORKSPACE / USER_WORKSPACE
#           |
#           +--> 2. Path Sanitization: Generates safe path WORKSPACE / "highlight.mp4"
#           |
#           +--> 3. Engine Selection:
#           |         - Primary Engine: cut_video_native() via silent FFmpeg C-level subprocess
#           |         - Fallback Engine: MoviePy subclipped() if native pipeline is disabled
#           |
#           +--> 4. Precision Cutting:
#           |         Executes ffmpeg -ss 10.000000 -t 15.500000 -c:v libx264 ...
#           |
#           \--> 5. JSON Return to Agent:
#                     '{"status": "success", "path": ".../highlight.mp4", "duration": 15.5}'
# ==============================================================================


@tool
def cut_video(
    input_path: str,
    start_time: float,
    end_time: float,
    output_name: str = "",
) -> str:
    """Cut a specific time segment from a video file.
    
    If multiple clips need to be cut from the same video, use batch_cut_video instead.

    Args:
        input_path: Full path or filename of the video inside workspace, e.g. "source.mp4".
        start_time: Cut start time in seconds (e.g. 10.5 for 10.5s).
        end_time: Cut end time in seconds (e.g. 45.0 for 45.0s). Must be greater than start_time.
        output_name: Optional output filename stem (without .mp4 extension).
            If omitted, automatically generates "clip_{start}_{end}".

    Returns:
        JSON string containing status, output path, and trimmed duration,
        or a descriptive error string if the cut fails.
    """
    try:
        # Step 1: Security perimeter defense
        # Line rationale: Strictly prevent access to external filesystem paths outside workspace
        resolved_input = _resolve_workspace_input_path(input_path, must_exist=True)
        if resolved_input is None:
            return f"Cut error: Input video is outside WORKSPACE or does not exist: {input_path}"

        # Step 2: Auto-generate output name if user/agent left it blank
        # Line rationale: Guaranteed unique, descriptive filenames like "clip_10_45" prevent overwrites
        if not output_name:
            output_name = f"clip_{start_time:.0f}_{end_time:.0f}"

        # Step 3: Sanitize output stem to strip illegal filesystem characters
        # Line rationale: Eliminates spaces, quotes, slashes, and traversal characters
        output_path = _safe_output_video_path(output_name, default_stem="clip")

        # Step 4: Detect optional MoviePy fallback library
        # Line rationale: Allows running on minimal systems without moviepy installed
        try:
            from moviepy.video.io.VideoFileClip import VideoFileClip
            use_moviepy = True
        except ImportError:
            use_moviepy = False

        # Step 5: Primary Engine Execution (Native FFmpeg Subprocess)
        # Line rationale: Direct FFmpeg execution is orders of magnitude faster and leak-free
        if native_ffmpeg_enabled() or not use_moviepy:
            duration = cut_video_native(
                resolved_input,
                output_path,
                start_time=start_time,
                end_time=end_time,
            )
            return json.dumps({
                "status": "success",
                "path": str(output_path),
                "duration": round(duration, 1),
            }, ensure_ascii=False)

        # Step 6: Fallback Engine Execution (MoviePy)
        # Line rationale: Used only when native FFmpeg pipeline is explicitly disabled
        with VideoFileClip(str(resolved_input)) as clip:
            sub_clip = clip.subclipped(start_time, end_time)
            sub_clip.write_videofile(
                str(output_path), codec="libx264", audio_codec="aac", logger=None
            )
        return json.dumps({
            "status": "success",
            "path": str(output_path),
            "duration": round(end_time - start_time, 1),
        }, ensure_ascii=False)

    except Exception as e:
        # Step 7: Self-healing error capture
        # Line rationale: Catch exceptions and return clean string so LLM agent can self-heal
        return f"Cut error: {e}"
