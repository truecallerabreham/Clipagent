from pathlib import Path

from moviepy import VideoFileClip

from clipagent_mcp.config import settings


def extract_audio(video_path: str, output_dir: str | None = None) -> str | None:
    """Extract audio from a video file.

    Args:
        video_path: Path to the video file.
        output_dir: Directory to save audio file. Defaults to same directory as video.

    Returns:
        audio_path: Path to the extracted audio file, or None if no audio track.
    """
    video = Path(video_path)
    if not video.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    if output_dir is None:
        output_dir = video.parent
    else:
        Path(output_dir).mkdir(parents=True, exist_ok=True)

    clip = VideoFileClip(str(video))
    if clip.audio is None:
        clip.close()
        return None

    audio_path = Path(output_dir) / f"{video.stem}.wav"
    clip.audio.write_audiofile(str(audio_path), logger=None)
    clip.close()

    return str(audio_path)
