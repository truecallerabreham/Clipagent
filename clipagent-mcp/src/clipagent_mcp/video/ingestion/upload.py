import shutil
import uuid
from pathlib import Path

import pixeltable as pxt

from clipagent_mcp.config import settings
from clipagent_mcp.database import init_database


def upload_video(video_path: str) -> str:
    """Upload a video file to the media directory and register in database.

    Args:
        video_path: Path to the video file to upload.

    Returns:
        video_id: Unique identifier for the uploaded video.
    """
    init_database()

    source = Path(video_path)
    if not source.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    video_id = str(uuid.uuid4())[:8]
    dest_dir = settings.media_path / video_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file = dest_dir / source.name
    shutil.copy2(source, dest_file)

    videos = pxt.get_table("videos")
    videos.insert(
        [
            {
                "video_id": video_id,
                "video_path": str(dest_file),
                "filename": source.name,
                "duration": 0.0,
                "status": "uploaded",
            }
        ]
    )

    return video_id


def get_video(video_id: str) -> dict:
    """Get video metadata by ID."""
    init_database()
    videos = pxt.get_table("videos")
    result = (
        videos.select(videos.video_id, videos.video_path, videos.filename, videos.status)
        .where(videos.video_id == video_id)
        .collect()
    )
    if len(result) == 0:
        raise ValueError(f"Video not found: {video_id}")
    return result[0]
