from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console

from .config import AppConfig, LLMProvider
from .pipeline import generate_video_pipeline
from .utils import sanitize_title
from .youtube_uploader import YouTubeUploader, UploadMetadata


console = Console()


def _validate_required_env() -> None:
    missing = []
    try:
        cfg = AppConfig()
        if cfg.llm_provider == LLMProvider.DEEPSEEK:
            if not cfg.deepseek_api_key:
                missing.append("DEEPSEEK_API_KEY")
        else:
            if not cfg.openai_api_key:
                missing.append("OPENAI_API_KEY")
    except Exception:
        # If config loading fails, check env vars directly
        if not os.getenv("OPENAI_API_KEY") and not os.getenv("DEEPSEEK_API_KEY"):
            missing.append("OPENAI_API_KEY or DEEPSEEK_API_KEY")
    if not os.getenv("ELEVENLABS_API_KEY"):
        missing.append("ELEVENLABS_API_KEY")
    if missing:
        raise RuntimeError(
            "Missing required env vars: "
            + ", ".join(missing)
            + ". Add them to a .env file (see example.env) and rerun."
        )


def generate_and_upload(
    output_dir: Path | str = "outputs",
    credentials_dir: Path | str = Path.cwd(),
    privacy_status: str = "private",
) -> str:
    """Generate a video and upload it to YouTube using sensible defaults.

    Respects env overrides and optional PROMPT provided via CI/manual workflow.
    Returns the uploaded YouTube video ID.
    """
    load_dotenv()
    _validate_required_env()

    # Auto-read default prompt if PROMPT is unset
    if not os.getenv("PROMPT"):
        default_prompt_path = Path.cwd() / "prompt.txt"
        if default_prompt_path.exists():
            try:
                content = default_prompt_path.read_text(encoding="utf-8").strip()
                if content:
                    os.environ["PROMPT"] = content
            except Exception:
                pass

    output_dir = Path(output_dir)
    credentials_dir = Path(credentials_dir)

    output_dir.mkdir(parents=True, exist_ok=True)

    # Surface credentials dir to analytics/uploader
    os.environ.setdefault("YOUTUBE_CREDENTIALS_DIR", str(credentials_dir))

    config = AppConfig()
    result = generate_video_pipeline(config=config, output_dir=output_dir)
    console.print(f"[green]Generated video: {result.video_path}")

    title = sanitize_title(result.topic)
    uploader = YouTubeUploader(credentials_dir=credentials_dir)
    metadata = UploadMetadata(
        title=title,
        description="",
        tags=None,
        category_id="22",
        privacy_status=config.youtube_privacy_status,
    )
    video_id = uploader.upload_video(video_path=Path(result.video_path), metadata=metadata)
    console.print(f"[green]Uploaded to YouTube. Video ID: {video_id}")
    return video_id


