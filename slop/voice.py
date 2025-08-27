from __future__ import annotations

from pathlib import Path
import os
from typing import Dict, Any, Tuple, Optional
import base64
import logging

from elevenlabs.client import ElevenLabs
from elevenlabs.types.audio_with_timestamps_response import AudioWithTimestampsResponse
from elevenlabs.types.character_alignment_response_model import CharacterAlignmentResponseModel
from elevenlabs.types.voice_settings import VoiceSettings

import asyncio
from typing import Tuple as _Tuple


logger = logging.getLogger(__name__)


def _extract_audio_base64(response: Any) -> Optional[str]:
    """Extract base64 audio from various possible SDK response shapes."""
    if response is None:
        return None
    # Mapping-like
    if isinstance(response, dict):
        for k in ("audio_base64", "audio_base_64", "audio"):
            v = response.get(k)
            if isinstance(v, str) and v:
                return v
        return None
    # Object-like
    for attr in ("audio_base64", "audio_base_64", "audio"):
        value = getattr(response, attr, None)
        if isinstance(value, str) and value:
            return value
    return None






def synthesize_voice_with_alignment(
    text: str,
    voice_id: str,
    output_dir: Path,
    *,
    model_id: str,
    output_format: str,
    stability: Optional[float] = None,
    similarity_boost: Optional[float] = None,
    style: Optional[float] = None,
    use_speaker_boost: Optional[bool] = None,
    speed: Optional[float] = None,
) -> Tuple[Path, CharacterAlignmentResponseModel]:
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "voice.mp3"

    api_key = os.getenv("ELEVENLABS_API_KEY")
    client = ElevenLabs(api_key=api_key) if api_key else ElevenLabs()

    logger.info(
        "[tts] starting convert_with_timestamps | voice_id=%s model_id=%s format=%s text_len=%d",
        voice_id,
        model_id,
        output_format,
        len(text or ""),
    )

    # Generate audio with character-level alignment per ElevenLabs docs
    # Build kwargs conditionally to omit voice_settings when no settings provided
    tts_kwargs: Dict[str, Any] = {
        "voice_id": voice_id,
        "text": text,
        "model_id": model_id,
        "output_format": output_format,
    }
    # Collect requested settings
    requested_settings: Dict[str, Any] = {}
    if stability is not None:
        requested_settings["stability"] = stability
    if similarity_boost is not None:
        requested_settings["similarity_boost"] = similarity_boost
    if style is not None:
        requested_settings["style"] = style
    if use_speaker_boost is not None:
        requested_settings["use_speaker_boost"] = use_speaker_boost
    if speed is not None:
        requested_settings["speed"] = speed

    # Filter to fields supported by installed SDK to avoid runtime errors
    allowed_fields = set()
    try:
        # pydantic v2 models expose model_fields
        model_fields = getattr(VoiceSettings, "model_fields", None)
        if model_fields:
            allowed_fields = set(model_fields.keys())
        else:
            annotations = getattr(VoiceSettings, "__annotations__", None)
            if annotations:
                allowed_fields = set(annotations.keys())
    except Exception:
        allowed_fields = set()

    if requested_settings:
        settings_kwargs = (
            {k: v for k, v in requested_settings.items() if not allowed_fields or k in allowed_fields}
        )
        if settings_kwargs:
            tts_kwargs["voice_settings"] = VoiceSettings(**settings_kwargs)

    response = client.text_to_speech.convert_with_timestamps(**tts_kwargs)
    # Debug: log which attributes exist on the response
    try:
        keys_or_attrs = list(response.keys()) if isinstance(response, dict) else dir(response)
        logger.debug("[tts] response attrs: %s", keys_or_attrs)
    except Exception:
        pass

    audio_b64 = _extract_audio_base64(response)

    if not audio_b64:
        keys_or_attrs = list(response.keys()) if isinstance(response, dict) else dir(response)
        logger.error(
            "[tts] Missing audio in convert_with_timestamps response: type=%s keys=%s",
            type(response),
            keys_or_attrs,
        )
        raise RuntimeError("ElevenLabs convert_with_timestamps returned no audio")

    try:
        audio_bytes = base64.b64decode(audio_b64)
    except Exception as e:
        logger.exception("[tts] Failed to decode base64 audio: %s", e)
        raise

    with open(out_path, "wb") as f:
        f.write(audio_bytes)

    logger.info(
        "[tts] saved audio | path=%s size_bytes=%d alignment_chars=%s",
        str(out_path),
        len(audio_bytes),
    )


    return out_path, response.alignment


async def synthesize_voice_with_alignment_async(
    text: str,
    voice_id: str,
    output_dir: Path,
    *,
    model_id: str,
    output_format: str,
    stability: Optional[float] = None,
    similarity_boost: Optional[float] = None,
    style: Optional[float] = None,
    use_speaker_boost: Optional[bool] = None,
    speed: Optional[float] = None,
) -> _Tuple[Path, CharacterAlignmentResponseModel]:
    """Async ElevenLabs TTS with alignment; requires AsyncElevenLabs."""
    from elevenlabs.client import AsyncElevenLabs  # type: ignore

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "voice.mp3"

    api_key = os.getenv("ELEVENLABS_API_KEY")
    client = AsyncElevenLabs(api_key=api_key) if api_key else AsyncElevenLabs()  # type: ignore

    logger.info(
        "[tts/async] starting convert_with_timestamps | voice_id=%s model_id=%s format=%s text_len=%d",
        voice_id,
        model_id,
        output_format,
        len(text or ""),
    )

    # Build kwargs conditionally to omit voice_settings when no settings provided
    tts_kwargs: Dict[str, Any] = {
        "voice_id": voice_id,
        "text": text,
        "model_id": model_id,
        "output_format": output_format,
    }
    requested_settings: Dict[str, Any] = {}
    if stability is not None:
        requested_settings["stability"] = stability
    if similarity_boost is not None:
        requested_settings["similarity_boost"] = similarity_boost
    if style is not None:
        requested_settings["style"] = style
    if use_speaker_boost is not None:
        requested_settings["use_speaker_boost"] = use_speaker_boost
    if speed is not None:
        requested_settings["speed"] = speed

    allowed_fields = set()
    try:
        model_fields = getattr(VoiceSettings, "model_fields", None)
        if model_fields:
            allowed_fields = set(model_fields.keys())
        else:
            annotations = getattr(VoiceSettings, "__annotations__", None)
            if annotations:
                allowed_fields = set(annotations.keys())
    except Exception:
        allowed_fields = set()

    if requested_settings:
        settings_kwargs = (
            {k: v for k, v in requested_settings.items() if not allowed_fields or k in allowed_fields}
        )
        if settings_kwargs:
            tts_kwargs["voice_settings"] = VoiceSettings(**settings_kwargs)

    response = await client.text_to_speech.convert_with_timestamps(**tts_kwargs)  # type: ignore[attr-defined]

    try:
        keys_or_attrs = list(response.keys()) if isinstance(response, dict) else dir(response)
        logger.debug("[tts/async] response attrs: %s", keys_or_attrs)
    except Exception:
        pass

    audio_b64 = _extract_audio_base64(response)
    if not audio_b64:
        keys_or_attrs = list(response.keys()) if isinstance(response, dict) else dir(response)
        logger.error(
            "[tts/async] Missing audio in convert_with_timestamps response: type=%s keys=%s",
            type(response),
            keys_or_attrs,
        )
        raise RuntimeError("ElevenLabs convert_with_timestamps returned no audio")

    audio_bytes = base64.b64decode(audio_b64)
    with open(out_path, "wb") as f:
        f.write(audio_bytes)

    alignment = getattr(response, "alignment", None)
    if alignment is None and isinstance(response, dict):
        alignment = response.get("alignment")

    logger.info(
        "[tts/async] saved audio | path=%s size_bytes=%d",
        str(out_path),
        len(audio_bytes),
    )

    return out_path, alignment  # type: ignore[return-value]


