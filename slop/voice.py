from __future__ import annotations

from pathlib import Path
import os

from elevenlabs.client import ElevenLabs
from elevenlabs import save


def synthesize_voice(text: str, voice_id: str, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "voice.mp3"

    api_key = os.getenv("ELEVENLABS_API_KEY")
    client = ElevenLabs(api_key=api_key) if api_key else ElevenLabs()
    audio = client.text_to_speech.convert(
        voice_id=voice_id,
        output_format="mp3_44100_128",
        text=text,
        model_id="eleven_multilingual_v2",
    )
    save(audio, str(out_path))
    return out_path


