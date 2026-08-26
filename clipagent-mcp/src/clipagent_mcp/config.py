from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env"}

    # Paths
    media_path: Path = Path("media")
    db_path: Path = Path(".pixeltable")

    # API Keys
    openai_api_key: str = ""
    groq_api_key: str = ""

    # Server
    mcp_host: str = "0.0.0.0"
    mcp_port: int = 9090

    # Models
    clip_model: str = "openai/clip-vit-base-patch32"
    caption_model: str = "gpt-4o-mini"
    transcription_model: str = "whisper-large-v3"


settings = Settings()
