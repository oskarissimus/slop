from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import typer
from dotenv import load_dotenv
from rich.console import Console

from .youtube_uploader import YouTubeUploader, UploadMetadata


console = Console()
app = typer.Typer(help="slop-youtube - Upload videos to YouTube", no_args_is_help=True)


def ensure_env_loaded() -> None:
    load_dotenv()


@app.command()
def upload(
    video_path: str = typer.Argument(..., help="Path to the MP4 file to upload"),
    title: str = typer.Option(None, help="Video title. Defaults to file name"),
    description: str = typer.Option("", help="Video description"),
    tags: Optional[str] = typer.Option(None, help="Comma-separated list of tags"),
    category_id: int = typer.Option(22, help="YouTube category ID (default 22: People & Blogs)"),
    privacy_status: str = typer.Option("private", help="public | unlisted | private"),
    thumbnail_path: Optional[str] = typer.Option(None, help="Optional path to a thumbnail image"),
    credentials_dir: str = typer.Option(
        str(Path.cwd()),
        help="Directory to store OAuth credentials (client_secret.json, token.json)",
    ),
) -> None:
    """Upload a video to YouTube with OAuth 2.0 (resumable)."""
    ensure_env_loaded()

    video = Path(video_path)
    if not video.exists():
        typer.secho(f"Video not found: {video}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    resolved_title = title or video.stem
    tag_list = None
    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    uploader = YouTubeUploader(credentials_dir=Path(credentials_dir))

    metadata = UploadMetadata(
        title=resolved_title,
        description=description,
        tags=tag_list,
        category_id=str(category_id),
        privacy_status=privacy_status,
    )

    video_id = uploader.upload_video(video_path=video, metadata=metadata)
    if thumbnail_path:
        uploader.set_thumbnail(video_id=video_id, thumbnail_path=Path(thumbnail_path))

    console.print(f"[green]Uploaded video with ID: {video_id}")


if __name__ == "__main__":
    app()


