"""FlightPrint Backend Configuration."""

from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings — loaded from env vars or .env file."""

    # Paths
    upload_dir: Path = Path("uploads")
    output_dir: Path = Path("output")

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # Pipeline
    max_video_size_mb: int = 2000  # 2GB
    default_target_fps: float = 2.0

    # AWS (optional)
    aws_s3_bucket: str = ""
    aws_region: str = "us-east-1"

    # AI
    openai_api_key: str = ""

    class Config:
        env_file = ".env"
        env_prefix = "FLIGHTPRINT_"


settings = Settings()
