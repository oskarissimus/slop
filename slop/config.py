from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel


class AppConfig(BaseModel):
    duration_seconds: int = 120
    fps: int = 24
    resolution_width: int = 1024
    resolution_height: int = 1536
    num_images: int = 12
    voice_id: str = "d4Z5Fvjohw3zxGpV8XUV"
    # ElevenLabs voice settings (Optional so they can be omitted if None)
    stability: Optional[float] = none
    similarity_boost: Optional[float] = none
    style: Optional[float] = 0.34
    use_speaker_boost: Optional[bool] = True
    speed: Optional[float] = none
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

    

# Note: file-based config loading has been removed intentionally.


