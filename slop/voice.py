from __future__ import annotations

from pathlib import Path
import os
from typing import Dict, Any, Tuple, Optional, List
import base64
import logging
import subprocess
import shutil

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



async def synthesize_voice_with_alignment_chunked_async(
    scenes: List["Scene"],
    voice_id: str,
    output_dir: Path,
    *,
    model_id: str,
    output_format: str,
    concurrency: int = 4,
    stability: Optional[float] = None,
    similarity_boost: Optional[float] = None,
    style: Optional[float] = None,
    use_speaker_boost: Optional[bool] = None,
    speed: Optional[float] = None,
    api_key: Optional[str] = None,
) -> Tuple[Path, List[float]]:
    """Generate TTS per scene concurrently using ElevenLabs convert_with_timestamps.

    Provides previous_text/next_text for continuity and returns the concatenated audio path
    along with per-scene durations (seconds) to time the slideshow.
    """
    from elevenlabs.client import AsyncElevenLabs  # type: ignore
    from .scriptgen import Scene  # local import to avoid cycles in type checking

    if not scenes:
        raise ValueError("scenes must not be empty")

    output_dir.mkdir(parents=True, exist_ok=True)
    chunks_dir = output_dir / "audio_chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)
    final_audio_path = output_dir / "voice.mp3"

    logger.info(
        "[tts/async/chunked] start | scenes=%d model_id=%s format=%s concurrency=%d",
        len(scenes),
        model_id,
        output_format,
        concurrency,
    )

    client = AsyncElevenLabs(api_key=api_key) if api_key else AsyncElevenLabs()  # type: ignore

    # Guard: Some models don't support previous_text/next_text
    unsupported_models = {"eleven_v3"}
    if model_id in unsupported_models:
        raise RuntimeError(
            f"Model '{model_id}' does not support previous_text/next_text for convert_with_timestamps. "
            "Use a context-enabled model like 'eleven_turbo_v2'."
        )

    # Build base voice settings once
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

    voice_settings = None
    if requested_settings:
        settings_kwargs = {k: v for k, v in requested_settings.items() if not allowed_fields or k in allowed_fields}
        if settings_kwargs:
            voice_settings = VoiceSettings(**settings_kwargs)

    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def run_one(index: int) -> Tuple[int, Path, float]:
        async with semaphore:
            scene = scenes[index]
            previous_text = scenes[index - 1].script if index > 0 else None
            next_text = scenes[index + 1].script if index + 1 < len(scenes) else None
            tts_kwargs: Dict[str, Any] = {
                "voice_id": voice_id,
                "text": scene.script,
                "model_id": model_id,
                "output_format": output_format,
            }
            if previous_text:
                tts_kwargs["previous_text"] = previous_text
            if next_text:
                tts_kwargs["next_text"] = next_text
            if voice_settings is not None:
                tts_kwargs["voice_settings"] = voice_settings

            logger.info(
                "[tts/async/chunked] request | i=%d text_len=%d prev=%s next=%s",
                index,
                len(scene.script or ""),
                "y" if previous_text else "n",
                "y" if next_text else "n",
            )
            response = await client.text_to_speech.convert_with_timestamps(**tts_kwargs)  # type: ignore[attr-defined]
            audio_b64 = _extract_audio_base64(response)
            if not audio_b64:
                keys_or_attrs = list(response.keys()) if isinstance(response, dict) else dir(response)
                logger.error(
                    "[tts/async/chunked] Missing audio | i=%d type=%s keys=%s",
                    index,
                    type(response),
                    keys_or_attrs,
                )
                raise RuntimeError("ElevenLabs chunk convert_with_timestamps returned no audio")

            audio_bytes = base64.b64decode(audio_b64)
            out_path = chunks_dir / f"chunk_{index:03d}.mp3"
            with open(out_path, "wb") as f:
                f.write(audio_bytes)

            # Compute duration from alignment end time (avoid ffprobe dependency)
            duration = 0.0
            align_obj = getattr(response, "alignment", None)
            if align_obj is None and isinstance(response, dict):
                align_obj = response.get("alignment")
            if align_obj is None:
                align_obj = getattr(response, "normalized_alignment", None)
                if align_obj is None and isinstance(response, dict):
                    align_obj = response.get("normalized_alignment")
            try:
                end_times = None
                if hasattr(align_obj, "character_end_times_seconds"):
                    end_times = getattr(align_obj, "character_end_times_seconds")
                elif isinstance(align_obj, dict):
                    end_times = align_obj.get("character_end_times_seconds")
                if end_times and len(end_times) > 0:
                    duration = float(end_times[-1])
            except Exception:
                duration = 0.0
            logger.info(
                "[tts/async/chunked] saved | i=%d path=%s bytes=%d duration=%.3f",
                index,
                str(out_path),
                len(audio_bytes),
                duration,
            )
            return index, out_path, duration

    tasks = [run_one(i) for i in range(len(scenes))]
    results = await asyncio.gather(*tasks)

    # Order results by index
    ordered_paths: List[Path] = [chunks_dir / f"chunk_{i:03d}.mp3" for i in range(len(scenes))]
    durations_by_scene: List[float] = [0.0 for _ in range(len(scenes))]
    for index, path, duration in results:
        ordered_paths[index] = path
        durations_by_scene[index] = duration

    # Concat with ffmpeg concat demuxer
    list_path = output_dir / "audio_chunks.txt"
    with open(list_path, "w", encoding="utf-8") as fh:
        for p in ordered_paths:
            fh.write(f"file {p.resolve()}\n")

    if not shutil.which("ffmpeg"):
        raise RuntimeError(
            "ffmpeg is required to concatenate audio chunks. Please install ffmpeg or make it available in PATH."
        )
    concat_cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_path),
        "-c",
        "copy",
        str(final_audio_path),
    ]
    subprocess.run(concat_cmd, check=True)
    logger.info(
        "[tts/async/chunked] concatenated audio | chunks=%d output=%s",
        len(ordered_paths),
        str(final_audio_path),
    )

    return final_audio_path, durations_by_scene

