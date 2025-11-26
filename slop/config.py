from __future__ import annotations

from enum import Enum
from typing import Literal, Optional, Union

from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMProvider(str, Enum):
    """LLM provider options for scene generation."""
    OPENAI = "openai"
    DEEPSEEK = "deepseek"


class OpenAIModel(str, Enum):
    """OpenAI model options."""
    GPT_4O = "gpt-4o"
    GPT_4O_MINI = "gpt-4o-mini"
    GPT_4_TURBO = "gpt-4-turbo"
    GPT_4 = "gpt-4"
    GPT_3_5_TURBO = "gpt-3.5-turbo"
    O1 = "o1"
    O1_MINI = "o1-mini"
    O1_PREVIEW = "o1-preview"


class DeepSeekModel(str, Enum):
    """DeepSeek model options."""
    DEEPSEEK_CHAT = "deepseek-chat"
    DEEPSEEK_CODER = "deepseek-coder"
    DEEPSEEK_REASONER = "deepseek-reasoner"
    DEEPSEEK_R1 = "deepseek-r1"


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8')

    duration_seconds: int = 180
    fps: int = 24
    resolution_width: int = 1024
    resolution_height: int = 1536
    num_images: int = 18
    voice_id: str = "Bx2lBwIZJBilRBVc3AGO"
    # ElevenLabs voice settings (Optional so they can be omitted if None)
    stability: Optional[float] = None
    similarity_boost: Optional[float] = None
    style: Optional[float] = None
    use_speaker_boost: Optional[bool] = True
    speed: Optional[float] = 1.1
    #d4Z5Fvjohw3zxGpV8XUV - Maria style = 0.34 stability 0.7 speed 1.15
    #olRVHO9SSe7gI7wwlL9o - rachel
    #21m00Tcm4TlvDq8ikWAM - poeta
    #pNInz6obpgDQGcFmaJgB - sarmata
    #Bx2lBwIZJBilRBVc3AGO - kamień stulecia

    # Runtime/model knobs (production defaults)
    chat_model: Union[OpenAIModel, DeepSeekModel] = OpenAIModel.GPT_4O
    scene_llm_model: Union[OpenAIModel, DeepSeekModel] = OpenAIModel.GPT_4O
    temperature: float = 0.7
    image_model: str = "gpt-image-1"
    image_quality: Literal["low", "medium", "high"] = "low"
    tts_model_id: str = "eleven_multilingual_v2"
    tts_output_format: str = "mp3_44100_128"
    # Concurrency for async ElevenLabs TTS chunking
    tts_concurrency: int = 4

    # YouTube upload visibility
    youtube_privacy_status: Literal["public", "unlisted", "private"] = "private"

    # LLM provider selection
    llm_provider: LLMProvider = LLMProvider.DEEPSEEK
    openai_api_key: Optional[str] = None
    deepseek_api_key: Optional[str] = None
    elevenlabs_api_key: Optional[str] = None
    drive_parent_folder_id: Optional[str] = None

    # OAuth credentials (single-source fields, optional)
    # Expect RAW JSON content. If not provided, uploaders will rely on existing files on disk.
    oauth_client_json: Optional[str] = None
    drive_token_json: Optional[str] = None
    youtube_token_json: Optional[str] = None
