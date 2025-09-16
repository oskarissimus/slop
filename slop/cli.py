from __future__ import annotations

import os
from pathlib import Path
import logging
import sys
from datetime import datetime, timezone, timedelta
from typing import Optional

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
from .uploader_config import YouTubeUploadConfig, DriveUploadConfig


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
    """Generate a video using defaults and ENV/PROMPT. No uploads here."""
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
    # Emit GitHub Actions outputs if available
    try:
        github_output = os.getenv("GITHUB_OUTPUT")
        if github_output:
            basename = Path(result.video_path).stem
            work_dir = output_dir / basename
            with open(github_output, "a", encoding="utf-8") as fh:
                fh.write(f"video_path={result.video_path}\n")
                fh.write(f"work_dir={work_dir}\n")
    except Exception:
        pass


@app.command(name="auth-youtube")
def auth_youtube(
    credentials_dir: str = typer.Option(
        str(Path.cwd()),
        help="Directory to store OAuth credentials (client_secret.json, youtube_token.json)",
    ),
) -> None:
    """Interactive OAuth flow to create/update YouTube token file."""
    _ensure_env_loaded()
    config = YouTubeUploadConfig()

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
    config = DriveUploadConfig()

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

@app.command(name="upload-youtube")
def upload_youtube(
    video_path: str = typer.Argument(..., help="Path to the MP4 file to upload"),
    title: Optional[str] = typer.Option(None, help="Video title. Defaults to file name"),
    description: str = typer.Option("", help="Video description"),
    privacy_status: Optional[str] = typer.Option(None, help="public | unlisted | private (defaults from config)"),
    credentials_dir: str = typer.Option(
        str(Path.cwd()),
        help="Directory with OAuth creds (client_secret.json, youtube_token.json)",
    ),
) -> None:
    """Upload a video to YouTube. Independent of generation."""
    _ensure_env_loaded()

    video = Path(video_path)
    if not video.exists():
        typer.secho(f"Video not found: {video}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    cfg = YouTubeUploadConfig()
    # Derive title: CLI flag > title.txt in work dir > file stem
    resolved_title = title
    if not resolved_title:
        work_dir = video.parent / video.stem
        title_path = work_dir / "title.txt"
        if title_path.exists():
            try:
                resolved_title = title_path.read_text(encoding="utf-8").strip() or None
            except Exception:
                resolved_title = None
    if not resolved_title:
        resolved_title = video.stem
    uploader = YouTubeUploader(credentials_dir=Path(credentials_dir), config=cfg)
    metadata = UploadMetadata(
        title=resolved_title,
        description=description,
        tags=None,
        category_id="22",
        privacy_status=privacy_status or cfg.youtube_privacy_status,
    )
    try:
        video_id = uploader.upload_video(video_path=video, metadata=metadata)
    except Exception as e:
        console.print(f"[red]YouTube upload failed: {e}")
        raise typer.Exit(code=4)
    console.print(f"[green]Uploaded to YouTube. Video ID: {video_id}")


@app.command(name="upload-drive")
def upload_drive(
    video_path: str = typer.Argument(..., help="Path to the MP4 file to upload alongside its work dir"),
    parent_folder_id: Optional[str] = typer.Option(None, help="Drive parent folder ID (defaults from config)"),
    credentials_dir: str = typer.Option(
        str(Path.cwd()),
        help="Directory with OAuth creds (client_secret.json, drive_token.json)",
    ),
) -> None:
    """Upload work directory and MP4 to Google Drive. Independent of generation."""
    _ensure_env_loaded()

    video = Path(video_path)
    if not video.exists():
        typer.secho(f"Video not found: {video}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    cfg = DriveUploadConfig()
    output_dir = video.parent
    basename = video.stem
    work_dir = output_dir / basename
    if not work_dir.exists() or not work_dir.is_dir():
        typer.secho(f"Work directory does not exist: {work_dir}", fg=typer.colors.RED)
        raise typer.Exit(code=2)

    resolved_parent = parent_folder_id or cfg.drive_parent_folder_id
    if not resolved_parent:
        typer.secho("Drive parent folder ID is required (provide flag or set in env).", fg=typer.colors.RED)
        raise typer.Exit(code=3)

    drive = DriveUploader(credentials_dir=Path(credentials_dir), config=cfg)
    try:
        folder_id = drive.upload_directory(work_dir, parent_folder_id=resolved_parent, make_shareable=True)
        _ = drive.upload_file(video, parent_folder_id=folder_id, make_shareable=True)
    except Exception as e:
        console.print(f"[red]Drive upload failed: {e}")
        raise typer.Exit(code=5)
    console.print(f"[green]Uploaded to Google Drive. Folder ID: {folder_id}")


@app.command(name="upload-artifacts")
def upload_artifacts(
    outputs_dir: str = typer.Option("outputs", help="Directory containing generated outputs"),
) -> None:
    """Utility: emit artifact paths for CI (stdout and GITHUB_OUTPUT if present)."""
    _ensure_env_loaded()
    out_dir = Path(outputs_dir)
    if not out_dir.exists():
        typer.secho(f"Outputs directory not found: {out_dir}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    # Collect mp4s (primary artifacts)
    mp4s = sorted(out_dir.glob("*.mp4"))
    if not mp4s:
        typer.secho("No MP4 files found in outputs directory.", fg=typer.colors.RED)
        raise typer.Exit(code=2)

    # Print newline-separated list for ease of consumption
    for p in mp4s:
        console.print(str(p))

    # Also emit to GITHUB_OUTPUT for downstream steps
    try:
        github_output = os.getenv("GITHUB_OUTPUT")
        if github_output:
            with open(github_output, "a", encoding="utf-8") as fh:
                fh.write("artifact_paths=\n")
                for p in mp4s:
                    fh.write(f"{p}\n")
    except Exception:
        pass


@app.command(name="generate-reaction")
def generate_reaction() -> None:
    """Generate from latest transcript of a default channel; no uploads here."""
    _ensure_env_loaded()
    _validate_required_env()
    if not os.getenv("RAPIDAPI_KEY"):
        typer.secho("Missing required env var: RAPIDAPI_KEY (set in .env)", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    os.environ.setdefault("YOUTUBE_CREDENTIALS_DIR", str(Path.cwd()))

    # Defaults (no user-provided flags)
    channel_handle = "@SwaruuOficial"
    freshness_days = 1
    max_candidates = 5

    credentials_path = Path.cwd()

    # Optional search summary logging
    try:
        monitor = YouTubePublicMonitor(credentials_dir=credentials_path)
        channel_id = monitor.resolve_channel_id(channel_handle)
        if channel_id:
            videos = monitor.fetch_recent_videos(channel_id, max_results=max_candidates)
            console.print(
                f"[cyan]Search: channel_id={channel_id} | candidates={len(videos)} | freshness_window_days={freshness_days}"
            )
            if videos:
                now = datetime.now(timezone.utc)
                today_utc = now.date()
                allowed_dates = { (today_utc - timedelta(days=offset)) for offset in range(1, max(1, freshness_days) + 1) }
                console.print("[cyan]Last 5 uploads (title | published_at | fresh_yesterday):")
                for idx, v in enumerate(videos, start=1):
                    pub_dt = parse_published_at_iso8601(v.published_at)
                    is_fresh = False
                    pub_str = v.published_at
                    if pub_dt:
                        is_fresh = pub_dt.astimezone(timezone.utc).date() in allowed_dates
                        pub_str = pub_dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z")
                    console.print(f"  {idx}. {v.title} | {pub_str} | {is_fresh}")
            else:
                console.print("[yellow]No videos returned from API.")
        else:
            console.print("[yellow]Could not resolve channel id; continuing.")
    except Exception as e:
        console.print(f"[yellow]Failed to list recent videos for debugging: {e}")

    try:
        res = check_for_new_video_and_get_transcript(
            channel_handle_or_id=channel_handle,
            credentials_dir=credentials_path,
            preferred_languages=None,
            freshness_days=freshness_days,
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
    # Emit GitHub Actions outputs if available
    try:
        github_output = os.getenv("GITHUB_OUTPUT")
        if github_output:
            basename = Path(result.video_path).stem
            work_dir = output_dir / basename
            with open(github_output, "a", encoding="utf-8") as fh:
                fh.write(f"video_path={result.video_path}\n")
                fh.write(f"work_dir={work_dir}\n")
    except Exception:
        pass



@app.command(name="tts-test-context")
def tts_test_context() -> None:
    """Probe ElevenLabs models and list which support previous_text/next_text in convert_with_timestamps.

    Uses AppConfig (pydantic-settings) for configuration and API key.
    """
    _ensure_env_loaded()

    # Load config via pydantic (no direct os.getenv usage)
    try:
        cfg = AppConfig()
    except Exception as e:
        console.print(f"[red]Failed to load AppConfig (check your .env): {e}")
        raise typer.Exit(code=2)

    # Lazy import to avoid hard dependency on ElevenLabs for other commands
    try:
        from elevenlabs.client import ElevenLabs  # type: ignore
    except Exception as e:
        console.print(f"[red]Failed to import ElevenLabs SDK: {e}")
        raise typer.Exit(code=3)

    # Instantiate client using key from config
    try:
        client = ElevenLabs(api_key=cfg.elevenlabs_api_key)
    except Exception as e:
        console.print(f"[red]Failed to initialize ElevenLabs client: {e}")
        raise typer.Exit(code=4)

    # Discover models via SDK (trying common method names across versions)
    try:
        models_resource = getattr(client, "models", None)
        if models_resource is None:
            raise RuntimeError("Client has no 'models' resource. Update elevenlabs package.")

        models_list = None
        for method_name in ("get_all", "list", "list_models", "get_models"):
            getter = getattr(models_resource, method_name, None)
            if callable(getter):
                try:
                    models_list = getter()
                    break
                except Exception:
                    continue
        if models_list is None:
            # As a last resort, attempt attribute common in some SDKs
            models_list = getattr(models_resource, "_get_all", None)
            if callable(models_list):
                models_list = models_list()
        if models_list is None:
            raise RuntimeError("Unable to list models via ElevenLabs SDK. Tried multiple methods.")
    except Exception as e:
        console.print(f"[red]Failed to list ElevenLabs models: {e}")
        raise typer.Exit(code=5)

    # Normalize to iterable of model dict-like objects
    def _to_dict(model_obj):
        try:
            # pydantic models have model_dump
            dump = getattr(model_obj, "model_dump", None)
            if callable(dump):
                return dump()
        except Exception:
            pass
        try:
            # dataclass-like or simple objects
            keys = [
                k for k in dir(model_obj)
                if not k.startswith("_") and not callable(getattr(model_obj, k, None))
            ]
            data = {k: getattr(model_obj, k) for k in keys}
            # ensure model_id present if exists under different name
            if "id" in data and "model_id" not in data:
                data["model_id"] = data.get("id")
            return data
        except Exception:
            pass
        # Already a dict?
        if isinstance(model_obj, dict):
            return model_obj
        return {"model_id": str(model_obj)}

    models_info = [_to_dict(m) for m in models_list]

    # Heuristic: prefer models that are for text_to_speech
    def _is_tts_model(info: dict) -> bool:
        model_id = str(info.get("model_id") or info.get("id") or "").lower()
        model_type = str(info.get("type") or info.get("category") or "").lower()
        categories = info.get("categories") or info.get("capabilities") or []
        if isinstance(categories, dict):
            # Some SDKs expose capabilities as dict
            if any(
                str(k).lower() in ("text_to_speech", "tts") and bool(v)
                for k, v in categories.items()
            ):
                return True
        if isinstance(categories, (list, tuple)):
            if any(str(c).lower() in ("text_to_speech", "tts") for c in categories):
                return True
        if model_type in ("text_to_speech", "tts"):
            return True
        # Fallback: Eleven TTS model ids commonly start with 'eleven_'
        return model_id.startswith("eleven_")

    tts_models = [m for m in models_info if _is_tts_model(m)]
    if not tts_models:
        console.print("[yellow]No obvious TTS models detected from listing; proceeding to probe all returned models.")
        tts_models = models_info

    test_text = "This is a short test."
    prev_text = "Previous sentence for context."
    next_text = "Next sentence for continuity."

    supported: list[tuple[str, str]] = []  # (model_id, display_name)
    unsupported: list[tuple[str, str, str]] = []  # (model_id, display_name, error)

    # Do minimal probing per model
    for info in tts_models:
        model_id = str(info.get("model_id") or info.get("id") or "")
        display_name = str(info.get("display_name") or info.get("name") or model_id)
        if not model_id:
            continue
        try:
            kwargs = {
                "voice_id": cfg.voice_id,
                "text": test_text,
                "model_id": model_id,
                "output_format": cfg.tts_output_format,
                "previous_text": prev_text,
                "next_text": next_text,
            }
            resp = client.text_to_speech.convert_with_timestamps(**kwargs)
            # Determine success by presence of audio field
            audio_b64 = None
            if isinstance(resp, dict):
                audio_b64 = resp.get("audio_base64") or resp.get("audio_base_64") or resp.get("audio")
            else:
                for attr in ("audio_base64", "audio_base_64", "audio"):
                    val = getattr(resp, attr, None)
                    if isinstance(val, str) and val:
                        audio_b64 = val
                        break
            if audio_b64:
                supported.append((model_id, display_name))
            else:
                unsupported.append((model_id, display_name, "No audio returned"))
        except Exception as e:
            # Treat any exception as unsupported for context parameters
            msg = str(e)
            unsupported.append((model_id, display_name, msg))

    # Present results
    if supported:
        console.print("[green]Models that handled previous_text/next_text without error:")
        for mid, name in sorted(supported, key=lambda x: x[0].lower()):
            console.print(f"  - {mid} | {name}")
    else:
        console.print("[red]No models succeeded with previous_text/next_text.")

    if unsupported:
        console.print("[cyan]Models that failed (likely unsupported for context, or other error):")
        for mid, name, err in sorted(unsupported, key=lambda x: x[0].lower()):
            # Keep error concise
            short_err = err.strip().split("\n", 1)[0]
            console.print(f"  - {mid} | {name} | {short_err}")

    # Exit code 0 always; the goal is to enumerate capabilities, not fail the run
    return




