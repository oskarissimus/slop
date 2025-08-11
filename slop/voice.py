from __future__ import annotations

from pathlib import Path
import os
import shutil
import subprocess
from glob import glob
from typing import Optional

from elevenlabs.client import ElevenLabs
from elevenlabs import save
from tenacity import retry, stop_after_attempt, wait_exponential


@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3))
def _ffmpeg_bin() -> str:
    return os.getenv("FFMPEG_BINARY") or "ffmpeg"


def _estimate_seconds_from_text(text: str, words_per_second: float = 2.5) -> float:
    words = max(1, len(text.split()))
    return max(5.0, words / words_per_second)


def _generate_silent_mp3(output_path: Path, seconds: float) -> None:
    ffmpeg = _ffmpeg_bin()
    cmd = [
        ffmpeg,
        "-y",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=r=44100:cl=mono",
        "-t",
        f"{seconds:.2f}",
        "-c:a",
        "libmp3lame",
        "-q:a",
        "4",
        str(output_path),
    ]
    subprocess.run(cmd, check=True)


def _find_existing_voice_mp3() -> Optional[Path]:
    files = sorted(glob("outputs/**/voice.mp3", recursive=True), reverse=True)
    return Path(files[0]) if files else None


def synthesize_voice(text: str, voice_id: str, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "voice.mp3"

    # Mock mode to save tokens during testing
    if os.getenv("SLOP_MOCK_TTS", "0") not in ("", "0", "false", "False", "FALSE"):
        preferred = os.getenv("SLOP_TTS_MP3")
        if preferred and Path(preferred).exists():
            shutil.copy(preferred, out_path)
            return out_path
        existing = _find_existing_voice_mp3()
        if existing and existing.exists():
            shutil.copy(existing, out_path)
            return out_path
        # Fallback: create silent mp3 sized roughly to text length
        seconds = _estimate_seconds_from_text(text)
        _generate_silent_mp3(out_path, seconds)
        return out_path

    # Real ElevenLabs synthesis
    api_key = os.getenv("ELEVENLABS_API_KEY") or os.getenv("ELEVEN_API_KEY")
    client = ElevenLabs(api_key=api_key) if api_key else ElevenLabs()
    audio = client.text_to_speech.convert(
        voice_id=voice_id,
        output_format="mp3_44100_128",
        text=text,
        model_id="eleven_multilingual_v2",
    )
    save(audio, str(out_path))
    return out_path


