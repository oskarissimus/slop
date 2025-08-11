from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from dotenv import load_dotenv

from .config import AppConfig, write_default_config
from .pipeline import generate_video_pipeline


console = Console()
app = typer.Typer(help="slop - AI video generator", no_args_is_help=False)


def ensure_env_loaded() -> None:
    load_dotenv()


def validate_required_env() -> None:
    missing = []
    if not os.getenv("OPENAI_API_KEY"):
        missing.append("OPENAI_API_KEY")
    if not (os.getenv("ELEVENLABS_API_KEY") or os.getenv("ELEVEN_API_KEY")):
        missing.append("ELEVENLABS_API_KEY or ELEVEN_API_KEY")
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
    config_path: str = typer.Option("slop_app_config.py", help="Path to config"),
    output_dir: str = typer.Option("outputs", help="Directory for outputs"),
) -> None:
    """If no command is provided, run one-off generation with defaults."""
    ensure_env_loaded()
    validate_required_env()
    if ctx.invoked_subcommand is not None:
        return
    target = Path(config_path)
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        write_default_config(target)
        console.print(f"[yellow]No config found. Wrote default to {target}")
    config = AppConfig.load(target)
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    output_path = generate_video_pipeline(config=config, output_dir=Path(output_dir))
    console.print(f"[green]Generated video: {output_path}")


@app.command()
def init(config_path: str = typer.Option("slop_app_config.py", help="Where to write default config")) -> None:
    """Create a default config file."""
    ensure_env_loaded()
    target = Path(config_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        console.print(f"[yellow]Config already exists at {target}")
        return
    write_default_config(target)
    console.print(f"[green]Wrote default config to {target}")


@app.command()
def run_once(config_path: str = typer.Option("slop_app_config.py", help="Path to config"),
             output_dir: str = typer.Option("outputs", help="Directory for outputs")) -> None:
    """Generate a single two-minute video now."""
    ensure_env_loaded()
    validate_required_env()
    config = AppConfig.load(Path(config_path))
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    output_path = generate_video_pipeline(config=config, output_dir=Path(output_dir))
    console.print(f"[green]Generated video: {output_path}")





