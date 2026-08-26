from pathlib import Path

from groq import Groq

from clipagent_mcp.config import settings


def transcribe_audio(audio_path: str) -> str:
    """Transcribe audio file using Groq Whisper.

    Args:
        audio_path: Path to the audio file (WAV, MP3, etc.).

    Returns:
        text: Transcribed text.
    """
    audio_file = Path(audio_path)
    if not audio_file.exists():
        raise FileNotFoundError(f"Audio not found: {audio_path}")

    client = Groq(api_key=settings.groq_api_key)

    with open(audio_file, "rb") as f:
        result = client.audio.transcriptions.create(
            file=(audio_file.name, f),
            model="whisper-large-v3",
            language="en",
        )

    return result.text
