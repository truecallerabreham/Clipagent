from pathlib import Path

from moviepy import VideoFileClip


def extract_frames(
    video_path: str, output_dir: str | None = None, interval: float = 1.0
) -> list[str]:
    """Extract frames from a video at regular intervals.

    Args:
        video_path: Path to the video file.
        output_dir: Directory to save frames. Defaults to video parent / frames.
        interval: Seconds between extracted frames.

    Returns:
        frame_paths: List of paths to extracted frame images.
    """
    video = Path(video_path)
    if not video.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    if output_dir is None:
        output_dir = video.parent / "frames"
    else:
        output_dir = Path(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)

    clip = VideoFileClip(str(video))
    duration = clip.duration
    frame_paths = []

    t = 0.0
    while t < duration:
        frame_path = output_dir / f"frame_{int(t):04d}.png"
        clip.save_frame(str(frame_path), t=t)
        frame_paths.append(str(frame_path))
        t += interval

    clip.close()
    return frame_paths
