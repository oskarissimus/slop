from __future__ import annotations

import os
from typing import Literal

from pydantic import BaseModel


class AppConfig(BaseModel):
    duration_seconds: int = 120
    fps: int = 24
    resolution_width: int = 1024
    resolution_height: int = 1536
    num_images: int = 12
    voice_id: str = "d4Z5Fvjohw3zxGpV8XUV"
    style: float = 0.34
    #d4Z5Fvjohw3zxGpV8XUV - Maria
    #olRVHO9SSe7gI7wwlL9o - rachel
    #21m00Tcm4TlvDq8ikWAM - poeta
    #pNInz6obpgDQGcFmaJgB - sarmata

    # Runtime/model knobs (production defaults)
    chat_model: str = "gpt-4o-mini"
    scene_llm_model: str = "gpt-4o-mini"
    image_model: str = "gpt-image-1"
    image_quality: Literal["low", "medium", "high"] = "medium"
    tts_model_id: str = "eleven_v3"
    tts_output_format: str = "mp3_44100_128"

# Note: file-based config loading has been removed intentionally.


