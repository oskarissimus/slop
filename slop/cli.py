from __future__ import annotations

import os
from pathlib import Path
import logging
import sys
from datetime import datetime, timezone

import typer
from rich.console import Console
from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow

from .config import AppConfig
from .pipeline import generate_video_pipeline
from .utils import InsufficientOpenAIFundsError, sanitize_title
from .youtube_monitor import check_for_new_video_and_get_transcript, YouTubePublicMonitor, parse_published_at_iso8601
from .youtube_uploader import YouTubeUploader, UploadMetadata, YOUTUBE_UPLOAD_SCOPES
from .drive_uploader import DriveUploader, DRIVE_SCOPES


console = Console()
app = typer.Typer(help="slop - AI video generator", no_args_is_help=True)


def _configure_logging() -> None:
    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler(stream=sys.stdout)
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s")
        handler.setFormatter(formatter)
        root.addHandler(handler)
    root.setLevel(logging.INFO)


def _ensure_env_loaded() -> None:
    load_dotenv()
    _configure_logging()


def _validate_required_env() -> None:
    missing = []
    if not os.getenv("OPENAI_API_KEY"):
        missing.append("OPENAI_API_KEY")
    if not os.getenv("ELEVENLABS_API_KEY"):
        missing.append("ELEVENLABS_API_KEY")
    if missing:
        typer.secho(
            "Missing required env vars: " + ", ".join(missing)
            + "\nAdd them to a .env file (see example.env) and rerun.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)


def _ensure_prompt_default() -> None:
    if not os.getenv("PROMPT"):
        default_prompt_path = Path.cwd() / "prompt.txt"
        if default_prompt_path.exists():
            try:
                content = default_prompt_path.read_text(encoding="utf-8").strip()
                if content:
                    os.environ["PROMPT"] = content
            except Exception:
                pass


def _default_output_dir() -> Path:
    return Path("outputs")


@app.command(name="generate")
def generate() -> None:
    """Generate a video using defaults and ENV/PROMPT; then upload to YouTube and Drive."""
    _ensure_env_loaded()
    _validate_required_env()
    _ensure_prompt_default()
    os.environ.setdefault("YOUTUBE_CREDENTIALS_DIR", str(Path.cwd()))

    output_dir = _default_output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)

    config = AppConfig()
    try:
        result = generate_video_pipeline(config=config, output_dir=output_dir)
    except InsufficientOpenAIFundsError:
        console.print("[red]OpenAI reports insufficient quota (429). Please check your OpenAI billing/funds: https://platform.openai.com/")
        raise typer.Exit(code=3)
    console.print(f"[green]Generated video: {result.video_path}")

    # Default uploads
    # 1) YouTube upload (private by default)
    try:
        title = sanitize_title(result.topic)
        uploader = YouTubeUploader(
            credentials_dir=Path(os.getenv("YOUTUBE_CREDENTIALS_DIR", str(Path.cwd()))),
            config=config,
        )
        metadata = UploadMetadata(
            title=title,
            description="",
            tags=None,
            category_id="22",
            privacy_status=config.youtube_privacy_status,
        )
        video_id = uploader.upload_video(video_path=Path(result.video_path), metadata=metadata)
        console.print(f"[green]Uploaded to YouTube. Video ID: {video_id}")
    except Exception as e:
        console.print(f"[red]YouTube upload failed: {e}")
        raise typer.Exit(code=4)

    # 2) Google Drive upload (work directory and final MP4)
    try:
        basename = Path(result.video_path).stem
        work_dir = output_dir / basename
        parent_id = config.drive_parent_folder_id
        drive = DriveUploader(
            credentials_dir=Path(os.getenv("YOUTUBE_CREDENTIALS_DIR", str(Path.cwd()))),
            config=config,
        )
        folder_id = drive.upload_directory(work_dir, parent_folder_id=parent_id, make_shareable=True)
        _ = drive.upload_file(Path(result.video_path), parent_folder_id=folder_id, make_shareable=True)
        console.print(f"[green]Uploaded to Google Drive. Folder ID: {folder_id}")
    except Exception as e:
        console.print(f"[red]Drive upload failed: {e}")
        raise typer.Exit(code=5)


@app.command(name="auth-youtube")
def auth_youtube(
    credentials_dir: str = typer.Option(
        str(Path.cwd()),
        help="Directory to store OAuth credentials (client_secret.json, youtube_token.json)",
    ),
) -> None:
    """Interactive OAuth flow to create/update YouTube token file."""
    _ensure_env_loaded()
    config = AppConfig()

    cred_dir = Path(credentials_dir)
    cred_dir.mkdir(parents=True, exist_ok=True)
    client_secret_path = cred_dir / "client_secret.json"
    token_path = cred_dir / "youtube_token.json"

    if not client_secret_path.exists():
        content = getattr(config, "oauth_client_json", None)
        if content and content.strip().startswith("{"):
            client_secret_path.write_text(content, encoding="utf-8")
        else:
            typer.secho(
                f"Missing client_secret.json at {client_secret_path}. Provide oauth_client_json in .env or place the file and retry.",
                fg=typer.colors.RED,
            )
            raise typer.Exit(code=1)

    flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_path), scopes=YOUTUBE_UPLOAD_SCOPES)
    creds = flow.run_local_server(port=0)
    token_path.write_text(creds.to_json())
    console.print(f"[green]Saved YouTube OAuth token to: {token_path}")


@app.command(name="auth-drive")
def auth_drive(
    credentials_dir: str = typer.Option(
        str(Path.cwd()),
        help="Directory to store OAuth credentials (client_secret.json, drive_token.json)",
    ),
) -> None:
    """Interactive OAuth flow to create/update Google Drive token file."""
    _ensure_env_loaded()
    config = AppConfig()

    cred_dir = Path(credentials_dir)
    cred_dir.mkdir(parents=True, exist_ok=True)
    client_secret_path = cred_dir / "client_secret.json"
    token_path = cred_dir / "drive_token.json"

    if not client_secret_path.exists():
        content = getattr(config, "oauth_client_json", None)
        if content and content.strip().startswith("{"):
            client_secret_path.write_text(content, encoding="utf-8")
        else:
            typer.secho(
                f"Missing client_secret.json at {client_secret_path}. Provide oauth_client_json in .env or place the file and retry.",
                fg=typer.colors.RED,
            )
            raise typer.Exit(code=1)

    flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_path), scopes=DRIVE_SCOPES)
    creds = flow.run_local_server(port=0)
    token_path.write_text(creds.to_json())
    console.print(f"[green]Saved Drive OAuth token to: {token_path}")

@app.command(name="generate-reaction")
def generate_reaction() -> None:
    """Generate from latest transcript of a default channel; no flags."""
    _ensure_env_loaded()
    _validate_required_env()
    if not os.getenv("RAPIDAPI_KEY"):
        typer.secho("Missing required env var: RAPIDAPI_KEY (set in .env)", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    os.environ.setdefault("YOUTUBE_CREDENTIALS_DIR", str(Path.cwd()))

    # Defaults (no user-provided flags)
    channel_handle = "@SwaruuOficial"
    freshness_hours = 24
    max_candidates = 5

    credentials_path = Path.cwd()

    # Optional search summary logging
    try:
        monitor = YouTubePublicMonitor(credentials_dir=credentials_path)
        channel_id = monitor.resolve_channel_id(channel_handle)
        if channel_id:
            videos = monitor.fetch_recent_videos(channel_id, max_results=max_candidates)
            console.print(
                f"[cyan]Search: channel_id={channel_id} | candidates={len(videos)} | freshness_threshold={freshness_hours}h"
            )
            if videos:
                now = datetime.now(timezone.utc)
                freshest_age = None
                for v in videos:
                    pub_dt = parse_published_at_iso8601(v.published_at)
                    if not pub_dt:
                        continue
                    age = now - pub_dt
                    if freshest_age is None or age < freshest_age:
                        freshest_age = age
        else:
            console.print("[yellow]Could not resolve channel id; continuing.")
    except Exception:
        pass

    try:
        res = check_for_new_video_and_get_transcript(
            channel_handle_or_id=channel_handle,
            credentials_dir=credentials_path,
            preferred_languages=None,
            freshness_hours=freshness_hours,
            max_candidates=max_candidates,
            use_generated_fallback=True,
        )
    except Exception as e:
        console.print(f"[red]Failed to check channel for new videos: {e}")
        raise typer.Exit(code=1)

    if not res:
        console.print("[red]No new video detected or no transcript available.")
        raise typer.Exit(code=2)

    _, transcript = res
    os.environ["PROMPT"] = transcript

    output_dir = _default_output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)
    config = AppConfig()
    result = generate_video_pipeline(config=config, output_dir=output_dir)
    console.print(f"[green]Generated reaction video: {result.video_path}")

    # Upload to YouTube
    try:
        title = sanitize_title(result.topic)
        uploader = YouTubeUploader(
            credentials_dir=Path(os.getenv("YOUTUBE_CREDENTIALS_DIR", str(Path.cwd()))),
            config=config,
        )
        metadata = UploadMetadata(
            title=title,
            description="",
            tags=None,
            category_id="22",
            privacy_status=config.youtube_privacy_status,
        )
        video_id = uploader.upload_video(video_path=Path(result.video_path), metadata=metadata)
        console.print(f"[green]Uploaded to YouTube. Video ID: {video_id}")
    except Exception as e:
        console.print(f"[red]YouTube upload failed: {e}")
        raise typer.Exit(code=4)

    # Upload to Google Drive (work directory and final MP4)
    try:
        basename = Path(result.video_path).stem
        work_dir = output_dir / basename
        parent_id = config.drive_parent_folder_id
        drive = DriveUploader(
            credentials_dir=Path(os.getenv("YOUTUBE_CREDENTIALS_DIR", str(Path.cwd()))),
            config=config,
        )
        folder_id = drive.upload_directory(work_dir, parent_folder_id=parent_id, make_shareable=True)
        _ = drive.upload_file(Path(result.video_path), parent_folder_id=folder_id, make_shareable=True)
        console.print(f"[green]Uploaded to Google Drive. Folder ID: {folder_id}")
    except Exception as e:
        console.print(f"[red]Drive upload failed: {e}")
        raise typer.Exit(code=5)





