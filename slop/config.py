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
    image_provider: str = "openai"  # placeholder | openai
    voice_id: str = "pNInz6obpgDQGcFmaJgB"
    #olRVHO9SSe7gI7wwlL9o - rachel
    #21m00Tcm4TlvDq8ikWAM - poeta
    #pNInz6obpgDQGcFmaJgB - sarmata

    # Simplified runtime/model knobs (no environment modes)
    chat_model: str = Field(default_factory=lambda: os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini"))
    scene_llm_model: str = Field(default_factory=lambda: os.getenv("OPENAI_SCENE_MODEL", "gpt-4o-mini"))
    image_model: str = Field(default_factory=lambda: os.getenv("OPENAI_IMAGE_MODEL", "dall-e-3"))
    image_size: str = Field(default_factory=lambda: os.getenv("OPENAI_IMAGE_SIZE", "1024x1536"))
    # Image quality is fixed to "low" and not configurable.
    image_quality: str = "low"
    tts_model_id: str = Field(default_factory=lambda: os.getenv("ELEVENLABS_TTS_MODEL", "eleven_multilingual_v2"))
    tts_output_format: str = Field(default_factory=lambda: os.getenv("ELEVENLABS_TTS_FORMAT", "mp3_44100_128"))

# Note: file-based config loading has been removed intentionally.


def apply_env_overrides(config: AppConfig) -> AppConfig:
    """Apply a minimal set of environment-driven overrides (no modes).

    Image quality is fixed to "low" and is not overridden by env.
    """
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
    # Intentionally do not read OPENAI_IMAGE_QUALITY; keep "low"
    config.tts_model_id = os.getenv("ELEVENLABS_TTS_MODEL", config.tts_model_id)
    config.tts_output_format = os.getenv("ELEVENLABS_TTS_FORMAT", config.tts_output_format)

    # Ensure it stays "low"
    config.image_quality = "low"

    return config


