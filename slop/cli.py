from __future__ import annotations

import os
from pathlib import Path
from typing import Optional
import logging
import sys
from datetime import datetime, timezone, timedelta

import typer
from rich.console import Console
from dotenv import load_dotenv

from .config import AppConfig
from .pipeline import generate_video_pipeline
from .youtube_uploader import YouTubeUploader, UploadMetadata
from .utils import sanitize_title
from .youtube_monitor import check_for_new_video_and_get_transcript, YouTubePublicMonitor, fetch_transcript_text, parse_published_at_iso8601
from .drive_uploader import DriveUploader


console = Console()
app = typer.Typer(help="slop - AI video generator", no_args_is_help=False)


def _configure_logging() -> None:
    # Configure root logger and stream to stdout for GH Actions visibility
    level_name = os.getenv("SLOP_LOG_LEVEL", "INFO").upper().strip()
    level_value = getattr(logging, level_name, logging.INFO)
    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler(stream=sys.stdout)
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s")
        handler.setFormatter(formatter)
        root.addHandler(handler)
    # Always set (or override) level based on env
    root.setLevel(level_value)


def ensure_env_loaded() -> None:
    load_dotenv()
    _configure_logging()


def _format_timedelta_human(delta: timedelta) -> str:
    total_seconds = int(delta.total_seconds())
    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60
    return f"{days}d {hours}h {minutes}m"


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
    drive_upload: bool = typer.Option(False, help="Also upload outputs to Google Drive (work dir + MP4)"),
    drive_parent_folder_id: Optional[str] = typer.Option(None, help="Optional Drive parent folder ID to upload into"),
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

    if drive_upload:
        try:
            uploader = DriveUploader(credentials_dir=Path(credentials_dir))
            parent_id = drive_parent_folder_id or os.getenv("DRIVE_PARENT_FOLDER_ID") or None
            basename = Path(result.video_path).stem
            work_dir = Path(output_dir) / basename
            folder_id = uploader.upload_directory(work_dir, parent_folder_id=parent_id, make_shareable=True)
            file_res = uploader.upload_file(Path(result.video_path), parent_folder_id=folder_id, make_shareable=True)
            link_note = f" | link: {file_res.web_view_link}" if file_res.web_view_link else ""
            console.print(f"[green]Uploaded to Drive folder: {folder_id}; MP4 file id: {file_res.file_id}{link_note}")
        except Exception as e:
            console.print(f"[red]Drive upload failed: {e}")

# Removed `init` command as we no longer write a default config file


@app.command()
def youtube_auth(
    credentials_dir: str = typer.Option(str(Path.cwd()), help="Directory for YouTube OAuth credentials"),
):
    """Generate or refresh YouTube OAuth token and save to token.json."""
    ensure_env_loaded()
    uploader = YouTubeUploader(credentials_dir=Path(credentials_dir))
    token_path = uploader.authorize()
    console.print(f"[green]Saved YouTube OAuth token to: {token_path}")


@app.command()
def drive_auth(
    credentials_dir: str = typer.Option(str(Path.cwd()), help="Directory for Google OAuth credentials (client_secret.json, token.json)"),
):
    """Generate or refresh Google OAuth token for Drive and save to token.json."""
    ensure_env_loaded()
    uploader = DriveUploader(credentials_dir=Path(credentials_dir))
    token_path = uploader.authorize()
    console.print(f"[green]Saved Google OAuth token (Drive) to: {token_path}")


@app.command()
def run_once(
    output_dir: str = typer.Option("outputs", help="Directory for outputs"),
    upload: bool = typer.Option(False, help="Upload the generated video to YouTube"),
    drive_upload: bool = typer.Option(False, help="Also upload outputs to Google Drive (work dir + MP4)"),
    drive_parent_folder_id: Optional[str] = typer.Option(None, help="Optional Drive parent folder ID to upload into"),
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

    if drive_upload:
        try:
            uploader = DriveUploader(credentials_dir=Path(credentials_dir))
            parent_id = drive_parent_folder_id or os.getenv("DRIVE_PARENT_FOLDER_ID") or None
            basename = Path(result.video_path).stem
            work_dir = Path(output_dir) / basename
            folder_id = uploader.upload_directory(work_dir, parent_folder_id=parent_id, make_shareable=True)
            file_res = uploader.upload_file(Path(result.video_path), parent_folder_id=folder_id, make_shareable=True)
            link_note = f" | link: {file_res.web_view_link}" if file_res.web_view_link else ""
            console.print(f"[green]Uploaded to Drive folder: {folder_id}; MP4 file id: {file_res.file_id}{link_note}")
        except Exception as e:
            console.print(f"[red]Drive upload failed: {e}")


@app.command()
def generate_from_channel_if_new(
    channel_handle: str = typer.Option("@SwaruuOficial", help="YouTube channel handle (e.g., @SwaruuOficial) or channel ID (UC...)"),
    credentials_dir: str = typer.Option(str(Path.cwd()), help="Directory for YouTube OAuth credentials"),
    output_dir: str = typer.Option("outputs", help="Directory for outputs"),
    upload: bool = typer.Option(True, help="Upload the generated video to YouTube when created"),
    use_generated_fallback: bool = typer.Option(True, help="(Deprecated) No longer used; transcripts come from RapidAPI yt-api"),
    freshness_hours: int = typer.Option(24, help="Max age (hours) for a video to consider"),
    max_candidates: int = typer.Option(5, help="How many recent uploads to scan"),
) -> None:
    """Check channel for a new video in the last 24h using RapidAPI; if found, use its transcript as PROMPT and generate/upload."""
    ensure_env_loaded()
    validate_required_env()
    if not os.getenv("RAPIDAPI_KEY"):
        typer.secho("Missing required env var: RAPIDAPI_KEY (set in .env)", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    os.environ.setdefault("YOUTUBE_CREDENTIALS_DIR", credentials_dir)

    credentials_path = Path(credentials_dir)

    # Search summary logging
    try:
        monitor = YouTubePublicMonitor(credentials_dir=credentials_path)
        channel_id = monitor.resolve_channel_id(channel_handle)
        if not channel_id:
            console.print("[red]Failed to resolve channel; check handle or credentials.")
            raise typer.Exit(code=1)
        videos = monitor.fetch_recent_videos(channel_id, max_results=max_candidates)
        console.print(f"[cyan]Search: channel_id={channel_id} | candidates={len(videos)} | freshness_threshold={freshness_hours}h")
        if videos:
            now = datetime.now(timezone.utc)
            freshest = None
            freshest_age = None
            for v in videos:
                pub_dt = parse_published_at_iso8601(v.published_at)
                if not pub_dt:
                    continue
                age = now - pub_dt
                if freshest_age is None or age < freshest_age:
                    freshest_age = age
                    freshest = v
            if freshest and freshest_age is not None:
                age_str = _format_timedelta_human(freshest_age)
                console.print(f"[cyan]Newest: {freshest.title} ({freshest.video_id}) | published={freshest.published_at} | age={age_str}")
        else:
            console.print("[yellow]No recent videos returned by API.")
    except Exception as e:
        console.print(f"[yellow]Search summary logging failed (continuing): {e}")

    try:
        res = check_for_new_video_and_get_transcript(
            channel_handle_or_id=channel_handle,
            credentials_dir=credentials_path,
            preferred_languages=None,
            freshness_hours=freshness_hours,
            max_candidates=max_candidates,
            use_generated_fallback=use_generated_fallback,
        )
    except Exception as e:
        console.print(f"[red]Failed to check channel for new videos: {e}")
        raise typer.Exit(code=1)

    if not res:
        console.print("[red]No new video detected or no transcript available; failing as requested.")
        raise typer.Exit(code=2)

    video_id, transcript = res
    os.environ["PROMPT"] = transcript

    try:
        config = AppConfig()
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        result = generate_video_pipeline(config=config, output_dir=Path(output_dir))
        console.print(f"[green]Generated video from transcript of {channel_handle} latest ({video_id}): {result.video_path}")
    except Exception as e:
        console.print(f"[red]Video generation failed: {e}")
        raise typer.Exit(code=1)

    if upload:
        try:
            resolved_title = result.topic
            uploader = YouTubeUploader(credentials_dir=credentials_path)
            metadata = UploadMetadata(
                title=resolved_title,
                description="",
                tags=None,
                category_id="22",
                privacy_status="public",
            )
            new_video_id = uploader.upload_video(video_path=Path(result.video_path), metadata=metadata)
            console.print(f"[green]Uploaded to YouTube. Video ID: {new_video_id}")
        except Exception as e:
            console.print(f"[red]YouTube upload failed: {e}")
            raise typer.Exit(code=1)


@app.command()
def discover(
    channel_handle: str = typer.Option(..., help="YouTube channel handle (e.g., @SwaruuOficial) or channel ID (UC...)"),
    max_candidates: int = typer.Option(5, help="How many recent uploads to scan"),
    freshness_hours: int = typer.Option(2400, help="Max age (hours) for a video to consider"),
    preferred_languages: Optional[str] = typer.Option(None, help="Comma-separated language codes (e.g., es,en,pl)"),
    use_generated_fallback: bool = typer.Option(True, help="(Deprecated) No longer used; transcripts come from RapidAPI yt-api"),
) -> None:
    """Discovery-only: print recent uploads and whether a transcript is available (uses RapidAPI)."""
    ensure_env_loaded()
    if not os.getenv("RAPIDAPI_KEY"):
        typer.secho("Missing required env var: RAPIDAPI_KEY (set in .env)", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    monitor = YouTubePublicMonitor(credentials_dir=Path.cwd())
    channel_id = monitor.resolve_channel_id(channel_handle)
    if not channel_id:
        console.print("[red]Failed to resolve channel; check handle or credentials.")
        raise typer.Exit(code=1)

    langs = [s.strip() for s in preferred_languages.split(",")] if preferred_languages else None

    videos = monitor.fetch_recent_videos(channel_id, max_results=max_candidates)
    if not videos:
        console.print("[yellow]No recent videos found.")
        raise typer.Exit(code=0)

    now = datetime.now(timezone.utc)
    console.print(f"[cyan]Channel ID: {channel_id}; candidates: {len(videos)}")
    for v in videos:
        pub_dt = parse_published_at_iso8601(v.published_at)
        is_fresh = bool(pub_dt) and ((now - pub_dt) <= timedelta(hours=freshness_hours))
        has_tx = False
        if is_fresh:
            tx = fetch_transcript_text(v.video_id, preferred_languages=langs, use_generated_fallback=use_generated_fallback)
            has_tx = bool(tx)
        console.print(f"{v.video_id} | {v.title} | {v.published_at} | fresh={is_fresh} | transcript={has_tx}")





