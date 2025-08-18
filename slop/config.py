from __future__ import annotations

from pathlib import Path
from typing import List, Optional
import os

from pydantic import BaseModel, Field


class AppConfig(BaseModel):
    duration_seconds: int = 120
    fps: int = 24
    resolution_width: int = 1080
    resolution_height: int = 1920
    num_images: int = 12
    image_provider: str = "placeholder"  # placeholder | openai
    voice_id: str = "olRVHO9SSe7gI7wwlL9o"

    # Runtime/model knobs (production defaults mirror current behavior)
    environment_mode: str = Field(default_factory=lambda: os.getenv("SLOP_MODE", "production"))  # production | test
    chat_model: str = Field(default_factory=lambda: os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini"))
    scene_llm_model: str = Field(default_factory=lambda: os.getenv("OPENAI_SCENE_MODEL", "gpt-4o-mini"))
    image_model: str = Field(default_factory=lambda: os.getenv("OPENAI_IMAGE_MODEL", "dall-e-3"))
    image_size: str = Field(default_factory=lambda: os.getenv("OPENAI_IMAGE_SIZE", "1024x1536"))
    image_quality: Optional[str] = Field(default_factory=lambda: os.getenv("OPENAI_IMAGE_QUALITY", "standard"))  # standard | hd | None
    tts_model_id: str = Field(default_factory=lambda: os.getenv("ELEVENLABS_TTS_MODEL", "eleven_multilingual_v2"))
    tts_output_format: str = Field(default_factory=lambda: os.getenv("ELEVENLABS_TTS_FORMAT", "mp3_44100_128"))

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
        "voice_id": "olRVHO9SSe7gI7wwlL9o",
        # Scheduling removed; generate manually via CLI
    }
    """.strip()
    )


def apply_env_overrides(config: AppConfig) -> AppConfig:
    """Apply environment-driven overrides for easy test/production switching.

    Production remains identical to existing defaults. Test mode prioritizes lowest cost.
    """
    mode = os.getenv("SLOP_MODE", config.environment_mode).strip().lower()
    config.environment_mode = mode if mode in {"production", "test"} else "production"

    # Generic direct overrides (take precedence if provided)
    config.fps = int(os.getenv("SLOP_FPS", config.fps))
    config.resolution_width = int(os.getenv("SLOP_RESOLUTION_WIDTH", config.resolution_width))
    config.resolution_height = int(os.getenv("SLOP_RESOLUTION_HEIGHT", config.resolution_height))
    config.num_images = int(os.getenv("SLOP_NUM_IMAGES", config.num_images))
    config.image_provider = os.getenv("SLOP_IMAGE_PROVIDER", config.image_provider)

    config.chat_model = os.getenv("OPENAI_CHAT_MODEL", config.chat_model)
    config.scene_llm_model = os.getenv("OPENAI_SCENE_MODEL", config.scene_llm_model)
    config.image_model = os.getenv("OPENAI_IMAGE_MODEL", config.image_model)
    config.image_size = os.getenv("OPENAI_IMAGE_SIZE", config.image_size)
    config.image_quality = os.getenv("OPENAI_IMAGE_QUALITY", config.image_quality)
    config.tts_model_id = os.getenv("ELEVENLABS_TTS_MODEL", config.tts_model_id)
    config.tts_output_format = os.getenv("ELEVENLABS_TTS_FORMAT", config.tts_output_format)

    if config.environment_mode == "test":
        # In tests, only reduce image generation cost by lowering quality.
        # Keep all other settings identical to production unless explicitly overridden by env.
        # For gpt-image-1, use the cheapest quality tier: "low".
        config.image_quality = os.getenv("OPENAI_IMAGE_QUALITY", "low")

    return config


