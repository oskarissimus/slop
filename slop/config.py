from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field


class Personality(BaseModel):
    name: str = "Curious Explorer"
    description: str = (
        "An upbeat, inquisitive narrator who explains concepts simply and vividly,"
        " with curiosity, positivity, and gentle humor."
    )
    speaking_style: str = "warm, lively, friendly"
    voice_id: str = Field(
        default="21m00Tcm4TlvDq8ikWAM",  # ElevenLabs 'Rachel' as a common default
        description="Default ElevenLabs voice id",
    )


class AppConfig(BaseModel):
    duration_seconds: int = 120
    fps: int = 24
    resolution_width: int = 1080
    resolution_height: int = 1920
    num_images: int = 12
    image_provider: str = "placeholder"  # placeholder | openai
    personality: Personality = Personality()

    @staticmethod
    def load(path: Path) -> "AppConfig":
        namespace: dict = {}
        with open(path, "r", encoding="utf-8") as f:
            code = f.read()
        exec(compile(code, str(path), "exec"), namespace)
        if "CONFIG" not in namespace:
            raise ValueError("Config file must define CONFIG = {...}")
        return AppConfig.model_validate(namespace["CONFIG"])  # type: ignore[arg-type]


def write_default_config(target_path: Path) -> None:
    target_path.write_text(
        """
# slop config
# Define CONFIG as a dict matching AppConfig in `slop/config.py`
CONFIG = {
    "duration_seconds": 120,
    "fps": 24,
    "resolution_width": 1080,
    "resolution_height": 1920,
    "num_images": 12,
    "image_provider": "placeholder",
    "personality": {
        "name": "Curious Explorer",
        "description": "An upbeat, inquisitive narrator who explains concepts simply and vividly, with curiosity, positivity, and gentle humor.",
        "speaking_style": "warm, lively, friendly",
        "voice_id": "21m00Tcm4TlvDq8ikWAM"
    },
    # Scheduling removed; generate manually via CLI
}
""".strip()
    )


