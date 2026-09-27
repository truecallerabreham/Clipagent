from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence
from ._native_ffmpeg import merge_videos_native, native_ffmpeg_enabled
from ._shared import (
    _resolve_workspace_input_path,
    _safe_output_video_path,
    logger,
    tool,
)

# ==============================================================================
# MILESTONE 5: THE GLUE (merge_videos)
# ==============================================================================
# Major Aim:
#   Serve as the primary video concatenation tool ("the digital glue") for the AI
#   video editing agent. Glues multiple video segments into a single cohesive video
#   file, normalizing aspect ratios, framerates, and audio tracks across all input clips.
#
# Visual Example Flow:
#   Agent Request:
#     merge_videos(
#         video_paths=["intro.mp4", "scene1.mp4", "outro.mp4"],
#         output_name="final_compilation"
#     )
#           |
#           +--> 1. Security Check: Resolves each path within WORKSPACE or USER_WORKSPACE
#           |       (Requires at least 2 clips, rejects external or missing files)
#           |
#           +--> 2. Output Path Sanitization: Generates safe path WORKSPACE / "final_compilation.mp4"
#           |
#           +--> 3. Engine Selection:
#           |         - Primary Engine: merge_videos_native() via FFmpeg filter_complex
#           |           * Detects anchor aspect ratio (landscape or portrait)
#           |           * Scales & crops each clip to match anchor dimensions
#           |           * Generates synthetic audio silence for silent clips
#           |           * Concatenates video and audio streams into single timeline
#           |         - Fallback Engine: MoviePy concatenate_videoclips()
#           |
#           \--> 4. JSON Return to Agent:
#                     '{"status": "success", "path": ".../final_compilation.mp4", "duration": 25.0, "clip_count": 3, "resolution": "1920x1080"}'
# ==============================================================================


@tool
def merge_videos(
    video_paths: list[str],
    output_name: str = "merged",
    target_duration: float | None = None,
    tolerance: float = 0.1,
) -> str:
    """Concatenate multiple video files into a single continuous video.

    Args:
        video_paths: List of input video filenames or paths, e.g. ["clip1.mp4", "clip2.mp4"].
            Must contain at least 2 videos, all located within the workspace.
        output_name: Output filename stem without .mp4 extension (default: "merged").
        target_duration: Optional maximum target duration in seconds. If specified,
            subsequent videos will be trimmed or omitted to match the duration budget.
        tolerance: Allowed proportional tolerance for duration matching (default: 0.1 for 10%).

    Returns:
        JSON string containing status, output path, total duration, clip count, and resolution,
        or a descriptive error string if merging fails.
    """
    try:
        # Step 1: Input list validation
        # Line rationale: Concatenation requires at least two distinct video clips to glue together
        if not video_paths or not isinstance(video_paths, list):
            return "Merge error: video_paths must be a non-empty list of video paths."
        if len(video_paths) < 2:
            return f"Merge error: At least 2 videos are required for merging, but got {len(video_paths)}."

        # Step 2: Resolve and verify each input path against the workspace security boundary
        # Line rationale: Ensures none of the inputs attempt directory traversal or access unauthorized files
        resolved_paths: list[Path] = []
        for raw_path in video_paths:
            resolved = _resolve_workspace_input_path(raw_path, must_exist=True)
            if resolved is None:
                return f"Merge error: Input video is outside WORKSPACE or does not exist: {raw_path}"
            resolved_paths.append(resolved)

        # Step 3: Sanitize output filename to guarantee safe storage in WORKSPACE
        # Line rationale: Strips illegal filesystem characters and path traversal patterns
        output_path = _safe_output_video_path(output_name or "merged", default_stem="merged")

        # Step 4: Detect optional MoviePy fallback availability
        # Line rationale: Allows running on minimal systems without moviepy installed
        try:
            from moviepy.video.io.VideoFileClip import VideoFileClip
            from moviepy.video.compositing.concatenate import concatenate_videoclips
            use_moviepy = True
        except ImportError:
            use_moviepy = False

        # Step 5: Primary Engine Execution (Native FFmpeg Filter Complex)
        # Line rationale: FFmpeg C-level subprocess handles aspect ratio scaling, fps syncing,
        # and audio channel normalization with zero memory leaks and maximum speed
        if native_ffmpeg_enabled() or not use_moviepy:
            total_duration, clip_count, (w, h) = merge_videos_native(
                resolved_paths,
                output_path,
                target_duration=target_duration,
                tolerance=tolerance,
            )
            logger.info("Successfully merged %d clips -> %s (%.2fs)", clip_count, str(output_path), total_duration)
            return json.dumps({
                "status": "success",
                "path": str(output_path),
                "duration": round(total_duration, 1),
                "clip_count": clip_count,
                "resolution": f"{w}x{h}",
            }, ensure_ascii=False)

        # Step 6: Fallback Engine Execution (MoviePy)
        # Line rationale: Used only when native FFmpeg pipeline is explicitly deactivated
        clips = [VideoFileClip(str(p)) for p in resolved_paths]
        try:
            final_clip = concatenate_videoclips(clips, method="compose")
            final_clip.write_videofile(
                str(output_path),
                codec="libx264",
                audio_codec="aac",
                logger=None,
            )
            duration = final_clip.duration
        finally:
            for c in clips:
                c.close()

        return json.dumps({
            "status": "success",
            "path": str(output_path),
            "duration": round(duration, 1),
            "clip_count": len(resolved_paths),
        }, ensure_ascii=False)

    except Exception as e:
        # Step 7: Self-healing error capture
        # Line rationale: Returns descriptive string error so the AI agent can diagnose and retry
        return f"Merge error: {e}"
