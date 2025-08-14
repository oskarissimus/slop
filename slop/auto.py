from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console

from .config import AppConfig
from .pipeline import generate_video_pipeline
from .utils import sanitize_title
from .youtube_uploader import YouTubeUploader, UploadMetadata


console = Console()


def _validate_required_env() -> None:
    missing = []
    if os.getenv("SLOP_OFFLINE") == "1":
        # In offline mode, skip API key validation
        return
    if not os.getenv("OPENAI_API_KEY"):
        missing.append("OPENAI_API_KEY")
    if not os.getenv("ELEVENLABS_API_KEY"):
        missing.append("ELEVENLABS_API_KEY")
    if missing:
        raise RuntimeError(
            "Missing required env vars: "
            + ", ".join(missing)
            + ". Add them to a .env file (see example.env) and rerun."
        )


def generate_and_upload(
    config_path: Path | str = "slop_app_config.py",
    output_dir: Path | str = "outputs",
    credentials_dir: Path | str = Path.cwd(),
    privacy_status: str = "private",
) -> str:
    """Generate a video and upload it to YouTube using sensible defaults.

    Returns the uploaded YouTube video ID.
    """
    load_dotenv()
    _validate_required_env()

    config_path = Path(config_path)
    output_dir = Path(output_dir)
    credentials_dir = Path(credentials_dir)

    output_dir.mkdir(parents=True, exist_ok=True)

    config = AppConfig.load(config_path)
    result = generate_video_pipeline(config=config, output_dir=output_dir)
    console.print(f"[green]Generated video: {result.video_path}")

    title = sanitize_title(result.topic)
    uploader = YouTubeUploader(credentials_dir=credentials_dir)
    metadata = UploadMetadata(
        title=title,
        description="",
        tags=None,
        category_id="22",
        privacy_status=privacy_status,
    )
    video_id = uploader.upload_video(video_path=Path(result.video_path), metadata=metadata)
    console.print(f"[green]Uploaded to YouTube. Video ID: {video_id}")
    return video_id


