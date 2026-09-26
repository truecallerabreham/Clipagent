from __future__ import annotations

from ._shared import *


@tool
def inspect_video_duration(video_path: str) -> str:
    """Inspect basic video metadata such as duration, resolution, and frame rate.
    Should be called after cutting, merging, or before export to verify video duration.

    Args:
        video_path: Path to the video file to inspect, e.g. "/workspace/merged.mp4".
            Supports any .mp4 file within the workspace (source video or intermediate artifact).
    """
    try:
        resolved_input = _resolve_workspace_input_path(video_path, must_exist=True)
        if resolved_input is None:
            return f"Inspection failed: File does not exist or is outside WORKSPACE: {video_path}"
        meta = _get_video_meta(str(resolved_input))
        logger.info(
            "📏 Duration inspection: %s -> %.2fs (%s)",
            str(resolved_input),
            meta["duration_seconds"],
            meta["resolution"],
        )
        return json.dumps({"status": "success", "path": str(resolved_input), **meta}, ensure_ascii=False)
    except Exception as e:
        return f"Duration inspection error: {e}"
