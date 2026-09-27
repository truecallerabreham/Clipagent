from __future__ import annotations

import json
from pathlib import Path
from ._shared import (
    _get_video_meta,
    _resolve_workspace_input_path,
    logger,
    tool,
)

# ==============================================================================
# MILESTONE 3: THE STOPWATCH & RULER (inspect_video_duration)
# ==============================================================================
# Major Aim:
#   Act as the primary sensor tool for the AI video editing agent. Before cutting,
#   splitting, or merging videos, the agent must measure exact container metrics
#   (duration in seconds, resolution width x height, and frame rate FPS).
#   Without this tool, the agent would edit blindly with estimated or hallucinated timestamps.
#
# Visual Example Flow:
#   Agent decides: "I need to know how long source_video.mp4 is."
#         |
#         V
#   Calls: inspect_video_duration("source_video.mp4")
#         |
#         +--> 1. Path Security Check: Resolves path within WORKSPACE/USER_WORKSPACE
#         |       (Rejects unauthorized files or directory traversal attempts)
#         |
#         +--> 2. Metadata Sensor: Uses OpenCV (in-memory) or FFprobe (subprocess)
#         |       (Extracts width, height, fps, duration_seconds)
#         |
#         +--> 3. Structured Output: Formats result into JSON string for LLM parsing
#         |
#         V
#   Returns: '{"status": "success", "path": "...", "duration_seconds": 45.2, "resolution": "1920x1080", "fps": 30.0}'
# ==============================================================================


@tool
def inspect_video_duration(video_path: str) -> str:
    """Inspect basic video metadata such as duration, resolution, and frame rate.
    
    Should be called after cutting, merging, or before export to verify video duration.

    Args:
        video_path: Path to the video file to inspect, e.g. "sample.mp4" or "file:///...".
            Supports any video file located within WORKSPACE or USER_WORKSPACE.

    Returns:
        A JSON string containing status, duration_seconds, resolution, width, height,
        and fps, or a descriptive error message if inspection fails.
    """
    try:
        # Step 1: Security perimeter check -- verify the video resides within authorized workspaces
        # Line rationale: Never allow an agent to inspect arbitrary system files like private SSH keys or passwords.
        resolved_input = _resolve_workspace_input_path(video_path, must_exist=True)
        if resolved_input is None:
            return f"Inspection failed: File does not exist or is outside WORKSPACE: {video_path}"

        # Step 2: Extract real video container metrics using OpenCV or FFprobe fallback
        # Line rationale: Measures exact frame counts and timestamps rather than guessing.
        meta = _get_video_meta(str(resolved_input))

        # Step 3: Record the inspection measurement in the persistent audit log
        logger.info(
            "Duration inspection: %s -> %.2fs (%s)",
            str(resolved_input),
            meta["duration_seconds"],
            meta["resolution"],
        )

        # Step 4: Serialize into JSON string for direct consumption by the LLM agent
        # Line rationale: Standard JSON format allows agents to reliably parse numeric duration and bounds.
        return json.dumps(
            {"status": "success", "path": str(resolved_input), **meta},
            ensure_ascii=False,
        )

    except Exception as e:
        # Step 5: Catch all operational errors and return as a string instead of crashing
        # Line rationale: In agentic workflows, an uncaught exception terminates the agent session.
        # Returning a clear error string allows the LLM to self-heal and try an alternative approach.
        return f"Duration inspection error: {e}"
