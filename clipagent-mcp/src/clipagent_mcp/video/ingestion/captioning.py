from pathlib import Path

from PIL import Image


def caption_frame(frame_path: str) -> str:
    """Generate a caption for an image frame using basic image analysis.

    Args:
        frame_path: Path to the image frame (PNG, JPG, etc.).

    Returns:
        caption: Text description of the image.
    """
    frame = Path(frame_path)
    if not frame.exists():
        raise FileNotFoundError(f"Frame not found: {frame_path}")

    img = Image.open(frame)
    width, height = img.size
    dominant_color = img.getpixel((width // 2, height // 2))

    caption = f"A {width}x{height} image with dominant RGB color ({dominant_color[0]}, {dominant_color[1]}, {dominant_color[2]})"
    return caption
