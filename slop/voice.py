from __future__ import annotations

from pathlib import Path
import os
from typing import Dict, Any, Tuple, Optional

from elevenlabs.client import ElevenLabs
from elevenlabs import save


def synthesize_voice_with_alignment(text: str, voice_id: str, output_dir: Path, *, model_id: str, output_format: str) -> Tuple[Path, Optional[Dict[str, Any]]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "voice.mp3"

    api_key = os.getenv("ELEVENLABS_API_KEY")
    client = ElevenLabs(api_key=api_key) if api_key else ElevenLabs()

    # Attempt to request timestamps/alignment if supported by SDK
    alignment: Optional[Dict[str, Any]] = None
    try:
        # Newer SDKs may support include_timestamps / enable_timestamps; fall back if not.
        audio = client.text_to_speech.convert(
            voice_id=voice_id,
            output_format=output_format,
            text=text,
            model_id=model_id,
            # Hypothetical kwargs, ignored by older SDKs
            # type: ignore[arg-type]
            # include_timestamps=True,
        )
        # Some SDKs expose audio.bytes and audio.alignment; we try to access safely
        try:
            alignment = getattr(audio, "alignment", None)
        except Exception:
            alignment = None
        save(audio, str(out_path))
    except Exception:
        # Fallback to basic call
        audio = client.text_to_speech.convert(
            voice_id=voice_id,
            output_format=output_format,
            text=text,
            model_id=model_id,
        )
        save(audio, str(out_path))

    return out_path, alignment


def synthesize_voice(text: str, voice_id: str, output_dir: Path) -> Path:
    # Backwards-compatible wrapper using production defaults
    api_model = os.getenv("ELEVENLABS_TTS_MODEL", "eleven_multilingual_v2")
    api_format = os.getenv("ELEVENLABS_TTS_FORMAT", "mp3_44100_128")
    path, _ = synthesize_voice_with_alignment(text, voice_id, output_dir, model_id=api_model, output_format=api_format)
    return path


