from __future__ import annotations

from ._native_ffmpeg import cut_video_native, native_ffmpeg_enabled
from ._shared import *


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
        input_path: Full path to the input video file, e.g. "/workspace/source.mp4".
        start_time: Cut start time in seconds, e.g. 10.5 (representing 10.5s).
        end_time: Cut end time in seconds, e.g. 45.0 (representing 45.0s).
            Must be greater than start_time and within total video duration.
        output_name: Output filename without extension. If empty, automatically generates
            clip_{start}_{end}.mp4, e.g. "intro_highlight".
    """
    try:
        resolved_input = _resolve_workspace_input_path(input_path, must_exist=True)
        if resolved_input is None:
            return f"Cut error: Input video is outside WORKSPACE or does not exist: {input_path}"

        if not output_name:
            output_name = f"clip_{start_time:.0f}_{end_time:.0f}"
        output_path = _safe_output_video_path(output_name, default_stem="clip")

        try:
            from moviepy.video.io.VideoFileClip import VideoFileClip
            use_moviepy = True
        except ImportError:
            use_moviepy = False

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
        return f"Cut error: {e}"
