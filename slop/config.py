from __future__ import annotations

from typing import Literal, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8')

    duration_seconds: int = 300
    fps: int = 24
    resolution_width: int = 1024
    resolution_height: int = 1536
    num_images: int = 30
    voice_id: str = "Bx2lBwIZJBilRBVc3AGO"
    # ElevenLabs voice settings (Optional so they can be omitted if None)
    stability: Optional[float] = None
    similarity_boost: Optional[float] = None
    style: Optional[float] = None
    use_speaker_boost: Optional[bool] = True
    speed: Optional[float] = 1.2
    #d4Z5Fvjohw3zxGpV8XUV - Maria style = 0.34 stability 0.7 speed 1.15
    #olRVHO9SSe7gI7wwlL9o - rachel
    #21m00Tcm4TlvDq8ikWAM - poeta
    #pNInz6obpgDQGcFmaJgB - sarmata
    #Bx2lBwIZJBilRBVc3AGO - kamień stulecia

    # Runtime/model knobs (production defaults)
    chat_model: str = "gpt-4o"
    scene_llm_model: str = "gpt-4o"
    temperature: float = 0.7
    image_model: str = "gpt-image-1"
    image_quality: Literal["low", "medium", "high"] = "low"
    tts_model_id: str = "eleven_multilingual_v2"
    tts_output_format: str = "mp3_44100_128"
    # Concurrency for async ElevenLabs TTS chunking
    tts_concurrency: int = 4

    # YouTube upload visibility
    youtube_privacy_status: Literal["public", "unlisted", "private"] = "private"

    openai_api_key: str
    elevenlabs_api_key: str
    drive_parent_folder_id: Optional[str] = None

    # OAuth credentials (single-source fields, optional)
    # Expect RAW JSON content. If not provided, uploaders will rely on existing files on disk.
    oauth_client_json: Optional[str] = None
    drive_token_json: Optional[str] = None
    youtube_token_json: Optional[str] = None
