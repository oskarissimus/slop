from __future__ import annotations

from pathlib import Path
import os
from typing import Dict, Any, Tuple, Optional
import base64
import logging

from elevenlabs.client import ElevenLabs


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


def _to_dict_maybe(model_like: Any) -> Optional[Dict[str, Any]]:
    """Convert a pydantic/dataclass-like model to dict if possible."""
    if model_like is None:
        return None
    if isinstance(model_like, dict):
        return model_like
    # pydantic v2
    fn = getattr(model_like, "model_dump", None)
    if callable(fn):
        try:
            return fn()
        except Exception:
            pass
    # pydantic v1 / generic
    fn = getattr(model_like, "dict", None)
    if callable(fn):
        try:
            return fn()
        except Exception:
            pass
    return None


def _extract_alignment(response: Any) -> Optional[Dict[str, Any]]:
    """Extract alignment dict, preferring normalized_alignment when present."""
    if response is None:
        return None
    # Mapping-like
    if isinstance(response, dict):
        for key in ("normalized_alignment", "alignment"):
            val = response.get(key)
            d = _to_dict_maybe(val)
            if d:
                return d
        return None
    # Object-like
    for attr in ("normalized_alignment", "alignment"):
        val = getattr(response, attr, None)
        d = _to_dict_maybe(val)
        if d:
            return d
    return None


def synthesize_voice_with_alignment(text: str, voice_id: str, output_dir: Path, *, model_id: str, output_format: str) -> Tuple[Path, Optional[Dict[str, Any]]]:
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
    response = client.text_to_speech.convert_with_timestamps(
        voice_id=voice_id,
        text=text,
        model_id=model_id,
        output_format=output_format,
    )

    # Debug: log which attributes exist on the response
    try:
        keys_or_attrs = list(response.keys()) if isinstance(response, dict) else dir(response)
        logger.debug("[tts] response attrs: %s", keys_or_attrs)
    except Exception:
        pass

    audio_b64 = _extract_audio_base64(response)
    alignment: Optional[Dict[str, Any]] = _extract_alignment(response)

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
        len(alignment.get("characters", [])) if isinstance(alignment, dict) else "n/a",
    )

    # Log alignment summary if available
    if isinstance(alignment, dict):
        try:
            chars = alignment.get("characters", []) or []
            starts = alignment.get("character_start_times_seconds", []) or []
            ends = alignment.get("character_end_times_seconds", []) or []
            logger.info(
                "[tts] alignment | characters=%d first_start=%.3f last_end=%.3f",
                len(chars),
                float(starts[0]) if starts else -1.0,
                float(ends[-1]) if ends else -1.0,
            )
        except Exception:
            logger.debug("[tts] alignment summary logging failed", exc_info=True)

    return out_path, alignment


def synthesize_voice(text: str, voice_id: str, output_dir: Path) -> Path:
    # Backwards-compatible wrapper using production defaults
    api_model = os.getenv("ELEVENLABS_TTS_MODEL", "eleven_multilingual_v2")
    api_format = os.getenv("ELEVENLABS_TTS_FORMAT", "mp3_44100_128")
    path, _ = synthesize_voice_with_alignment(text, voice_id, output_dir, model_id=api_model, output_format=api_format)
    return path