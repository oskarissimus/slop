from __future__ import annotations

import os
from pathlib import Path
from typing import Optional
import logging
import sys

import typer
from rich.console import Console
from dotenv import load_dotenv

from .config import AppConfig
from .pipeline import generate_video_pipeline
from .youtube_uploader import YouTubeUploader, UploadMetadata
from .utils import sanitize_title


console = Console()
app = typer.Typer(help="slop - AI video generator", no_args_is_help=False)


def _configure_logging() -> None:
    # Configure root logger to INFO and stream to stdout for GH Actions visibility
    if not logging.getLogger().handlers:
        handler = logging.StreamHandler(stream=sys.stdout)
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s")
        handler.setFormatter(formatter)
        root = logging.getLogger()
        root.setLevel(logging.INFO)
        root.addHandler(handler)


def ensure_env_loaded() -> None:
    load_dotenv()
    _configure_logging()


def validate_required_env() -> None:
    missing = []
    if not os.getenv("OPENAI_API_KEY"):
        missing.append("OPENAI_API_KEY")
    if not os.getenv("ELEVENLABS_API_KEY"):
        missing.append("ELEVENLABS_API_KEY")
    if missing:
        typer.secho(
            "Missing required env vars: " + ", ".join(missing) +
            "\nAdd them to a .env file (see example.env) and rerun.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)

@app.callback(invoke_without_command=True)
def _default(
    ctx: typer.Context,
    output_dir: str = typer.Option("outputs", help="Directory for outputs"),
    upload: bool = typer.Option(False, help="Upload the generated video to YouTube"),
    title: Optional[str] = typer.Option(None, help="YouTube title (defaults to generated topic)"),
    description: str = typer.Option("", help="YouTube description"),
    tags: Optional[str] = typer.Option(None, help="Comma-separated YouTube tags"),
    category_id: int = typer.Option(22, help="YouTube category ID (default 22: People & Blogs)"),
    privacy_status: str = typer.Option("public", help="YouTube privacy: public | unlisted | private"),
    thumbnail_path: Optional[str] = typer.Option(None, help="Optional path to thumbnail image"),
    credentials_dir: str = typer.Option(str(Path.cwd()), help="Directory for YouTube OAuth credentials"),
    prompt: Optional[str] = typer.Option(None, help="Pojedynczy input: na jego podstawie w jednym zapytaniu powstaje topic i sceny"),
    prompt_file: Optional[str] = typer.Option(None, "--prompt-file", help="Ścieżka do pliku TXT zawierającego prompt (użyte, jeśli --prompt nie podano)"),
) -> None:
    """If no command is provided, run one-off generation with defaults."""
    ensure_env_loaded()
    validate_required_env()
    if ctx.invoked_subcommand is not None:
        return
    if prompt:
        os.environ["PROMPT"] = prompt
    elif prompt_file:
        p = Path(prompt_file)
        if not p.exists() or not p.is_file():
            typer.secho(f"Prompt file not found: {prompt_file}", fg=typer.colors.RED)
            raise typer.Exit(code=1)
        try:
            content = p.read_text(encoding="utf-8").strip()
        except Exception as e:
            typer.secho(f"Failed to read prompt file: {e}", fg=typer.colors.RED)
            raise typer.Exit(code=1)
        if content:
            os.environ["PROMPT"] = content
    else:
        # Auto-read ./prompt.txt if present and PROMPT not set
        if not os.getenv("PROMPT"):
            default_prompt_path = Path.cwd() / "prompt.txt"
            if default_prompt_path.exists():
                try:
                    content = default_prompt_path.read_text(encoding="utf-8").strip()
                    if content:
                        os.environ["PROMPT"] = content
                except Exception:
                    pass
    # Surface credentials dir to analytics and uploader
    os.environ.setdefault("YOUTUBE_CREDENTIALS_DIR", credentials_dir)
    # Always use in-memory defaults; no file-based config
    config = AppConfig()
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    result = generate_video_pipeline(config=config, output_dir=Path(output_dir))
    console.print(f"[green]Generated video: {result.video_path}")

    if upload:
        try:
            resolved_title = sanitize_title(title) if title else result.topic
            tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
            uploader = YouTubeUploader(credentials_dir=Path(credentials_dir))
            metadata = UploadMetadata(
                title=resolved_title,
                description=description,
                tags=tag_list,
                category_id=str(category_id),
                privacy_status=privacy_status,
            )
            video_id = uploader.upload_video(video_path=Path(result.video_path), metadata=metadata)
            if thumbnail_path:
                uploader.set_thumbnail(video_id=video_id, thumbnail_path=Path(thumbnail_path))
            console.print(f"[green]Uploaded to YouTube. Video ID: {video_id}")
        except Exception as e:
            console.print(f"[red]YouTube upload failed: {e}")


# Removed `init` command as we no longer write a default config file


@app.command()
def run_once(
    output_dir: str = typer.Option("outputs", help="Directory for outputs"),
    upload: bool = typer.Option(False, help="Upload the generated video to YouTube"),
    title: Optional[str] = typer.Option(None, help="YouTube title (defaults to generated topic)"),
    description: str = typer.Option("", help="YouTube description"),
    tags: Optional[str] = typer.Option(None, help="Comma-separated YouTube tags"),
    category_id: int = typer.Option(22, help="YouTube category ID (default 22: People & Blogs)"),
    privacy_status: str = typer.Option("public", help="YouTube privacy: public | unlisted | private"),
    thumbnail_path: Optional[str] = typer.Option(None, help="Optional path to thumbnail image"),
    credentials_dir: str = typer.Option(str(Path.cwd()), help="Directory for YouTube OAuth credentials"),
    prompt: Optional[str] = typer.Option(None, help="Pojedynczy input: na jego podstawie w jednym zapytaniu powstaje topic i sceny"),
    prompt_file: Optional[str] = typer.Option(None, "--prompt-file", help="Ścieżka do pliku TXT zawierającego prompt (użyte, jeśli --prompt nie podano)"),
) -> None:
    """Generate a single two-minute video now."""
    ensure_env_loaded()
    validate_required_env()
    if prompt:
        os.environ["PROMPT"] = prompt
    elif prompt_file:
        p = Path(prompt_file)
        if not p.exists() or not p.is_file():
            typer.secho(f"Prompt file not found: {prompt_file}", fg=typer.colors.RED)
            raise typer.Exit(code=1)
        try:
            content = p.read_text(encoding="utf-8").strip()
        except Exception as e:
            typer.secho(f"Failed to read prompt file: {e}", fg=typer.colors.RED)
            raise typer.Exit(code=1)
        if content:
            os.environ["PROMPT"] = content
    else:
        if not os.getenv("PROMPT"):
            default_prompt_path = Path.cwd() / "prompt.txt"
            if default_prompt_path.exists():
                try:
                    content = default_prompt_path.read_text(encoding="utf-8").strip()
                    if content:
                        os.environ["PROMPT"] = content
                except Exception:
                    pass
    os.environ.setdefault("YOUTUBE_CREDENTIALS_DIR", credentials_dir)
    config = AppConfig()
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    result = generate_video_pipeline(config=config, output_dir=Path(output_dir))
    console.print(f"[green]Generated video: {result.video_path}")

    if upload:
        try:
            resolved_title = sanitize_title(title) if title else result.topic
            tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
            uploader = YouTubeUploader(credentials_dir=Path(credentials_dir))
            metadata = UploadMetadata(
                title=resolved_title,
                description=description,
                tags=tag_list,
                category_id=str(category_id),
                privacy_status=privacy_status,
            )
            video_id = uploader.upload_video(video_path=Path(result.video_path), metadata=metadata)
            if thumbnail_path:
                uploader.set_thumbnail(video_id=video_id, thumbnail_path=Path(thumbnail_path))
            console.print(f"[green]Uploaded to YouTube. Video ID: {video_id}")
        except Exception as e:
            console.print(f"[red]YouTube upload failed: {e}")





