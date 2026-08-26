from pathlib import Path

import numpy as np
from PIL import Image


def embed_image(frame_path: str) -> np.ndarray:
    """Generate a feature embedding for an image using basic image analysis.

    Args:
        frame_path: Path to the image file.

    Returns:
        embedding: 512-dimensional numpy array.
    """
    frame = Path(frame_path)
    if not frame.exists():
        raise FileNotFoundError(f"Frame not found: {frame_path}")

    img = Image.open(frame).convert("RGB").resize((64, 64))
    pixels = np.array(img, dtype=np.float32) / 255.0

    embedding = np.zeros(512, dtype=np.float32)

    embedding[0] = np.mean(pixels[:, :, 0])
    embedding[1] = np.mean(pixels[:, :, 1])
    embedding[2] = np.mean(pixels[:, :, 2])

    embedding[3] = np.std(pixels[:, :, 0])
    embedding[4] = np.std(pixels[:, :, 1])
    embedding[5] = np.std(pixels[:, :, 2])

    h, w = pixels.shape[:2]
    for i in range(6, min(512, 6 + h * w * 3)):
        idx = i - 6
        ch = idx % 3
        y = (idx // 3) % h
        x = (idx // 3) // h
        if x < w:
            embedding[i] = pixels[y, x, ch]

    embedding = embedding / np.linalg.norm(embedding)
    return embedding


def embed_text(text: str) -> np.ndarray:
    """Generate a feature embedding for text using basic text analysis.

    Args:
        text: Text to embed.

    Returns:
        embedding: 512-dimensional numpy array.
    """
    embedding = np.zeros(512, dtype=np.float32)

    embedding[0] = len(text) / 100.0
    embedding[1] = len(text.split()) / 20.0

    for i, char in enumerate(text[:500]):
        embedding[2 + (i % 510)] += ord(char) / 1000.0

    embedding = embedding / np.linalg.norm(embedding)
    return embedding


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two embeddings."""
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
