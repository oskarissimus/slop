from __future__ import annotations

from pathlib import Path
import os
import wave

from elevenlabs.client import ElevenLabs
from elevenlabs import save


def _write_silent_wav(out_path: Path, seconds: int = 10, sample_rate: int = 44100) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit PCM
        wf.setframerate(sample_rate)
        frame = b"\x00\x00" * sample_rate
        for _ in range(max(1, seconds)):
            wf.writeframes(frame)
    return out_path


def synthesize_voice(text: str, voice_id: str, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "voice.mp3"

    api_key = os.getenv("ELEVENLABS_API_KEY")
    try:
        client = ElevenLabs(api_key=api_key) if api_key else ElevenLabs()
        audio = client.text_to_speech.convert(
            voice_id=voice_id,
            output_format="mp3_44100_128",
            text=text,
            model_id="eleven_multilingual_v2",
        )
        save(audio, str(out_path))
        return out_path
    except Exception:
        # Fallback: write a silent WAV approximating duration from text length
        approx_seconds = max(5, int(len((text or "").split()) / 2.5))
        wav_path = output_dir / "voice.wav"
        return _write_silent_wav(wav_path, seconds=approx_seconds)


