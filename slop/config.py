from __future__ import annotations

import os
from typing import Literal, Optional

from pydantic import BaseModel, field_validator


class AppConfig(BaseModel):
    duration_seconds: int = 120
    fps: int = 24
    resolution_width: int = 1024
    resolution_height: int = 1536
    num_images: int = 12
    voice_id: str = "Bx2lBwIZJBilRBVc3AGO"
    # ElevenLabs voice settings (Optional so they can be omitted if None)
    stability: Optional[float] = 0.50
    similarity_boost: Optional[float] = 0.75
    style: Optional[float] = 0.60
    use_speaker_boost: Optional[bool] = True
    speed: Optional[float] = 0.94
    #d4Z5Fvjohw3zxGpV8XUV - Maria float = 0.34
    #olRVHO9SSe7gI7wwlL9o - rachel
    #21m00Tcm4TlvDq8ikWAM - poeta
    #pNInz6obpgDQGcFmaJgB - sarmata
    #Bx2lBwIZJBilRBVc3AGO - kamień stulecia

    # Runtime/model knobs (production defaults)
    chat_model: str = "gpt-4o-mini"
    scene_llm_model: str = "gpt-4o-mini"
    image_model: str = "gpt-image-1"
    image_quality: Literal["low", "medium", "high"] = "medium"
    tts_model_id: str = "eleven_v3"
    tts_output_format: str = "mp3_44100_128"

    @field_validator("style", mode="before")
    @classmethod
    def normalize_style(cls, value):
        # Accept float/int, numeric strings, or special strings like "none" to omit
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"", "none", "null", "nil"}:
                return None
            try:
                return float(value)
            except ValueError as e:
                raise ValueError("style must be a float or 'none'") from e
        raise ValueError("style must be a float, numeric string, or 'none'")

    @field_validator("stability", mode="before")
    @classmethod
    def normalize_stability(cls, value):
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"", "none", "null", "nil"}:
                return None
            try:
                return float(value)
            except ValueError as e:
                raise ValueError("stability must be a float or 'none'") from e
        raise ValueError("stability must be a float, numeric string, or 'none'")

    @field_validator("similarity_boost", mode="before")
    @classmethod
    def normalize_similarity_boost(cls, value):
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"", "none", "null", "nil"}:
                return None
            try:
                return float(value)
            except ValueError as e:
                raise ValueError("similarity_boost must be a float or 'none'") from e
        raise ValueError("similarity_boost must be a float, numeric string, or 'none'")

    @field_validator("speed", mode="before")
    @classmethod
    def normalize_speed(cls, value):
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"", "none", "null", "nil"}:
                return None
            try:
                return float(value)
            except ValueError as e:
                raise ValueError("speed must be a float or 'none'") from e
        raise ValueError("speed must be a float, numeric string, or 'none'")

    @field_validator("use_speaker_boost", mode="before")
    @classmethod
    def normalize_use_speaker_boost(cls, value):
        if isinstance(value, bool) or value is None:
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"", "none", "null", "nil"}:
                return None
            if lowered in {"true", "1", "yes", "y", "on"}:
                return True
            if lowered in {"false", "0", "no", "n", "off"}:
                return False
        raise ValueError("use_speaker_boost must be a boolean or 'none'")

# Note: file-based config loading has been removed intentionally.


