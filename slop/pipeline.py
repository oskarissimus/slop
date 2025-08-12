from __future__ import annotations

from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import List

from .config import AppConfig
from .topics import generate_topic
from .scriptgen import generate_script
from .images import generate_images
from .voice import synthesize_voice
from .stitch import stitch_video


@dataclass
class GeneratedVideo:
    video_path: Path
    topic: str
    script_text: str


def generate_video_pipeline(config: AppConfig, output_dir: Path) -> GeneratedVideo:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    basename = f"video_{timestamp}"
    work_dir = output_dir / basename
    work_dir.mkdir(parents=True, exist_ok=True)

    topic = generate_topic(config.personality)
    script_text = generate_script(topic=topic, personality=config.personality, target_duration_seconds=config.duration_seconds)
    image_paths = generate_images(
        script_text=script_text,
        num_images=config.num_images,
        output_dir=work_dir,
        provider=config.image_provider,
    )
    audio_path = synthesize_voice(text=script_text, voice_id=config.personality.voice_id, output_dir=work_dir)

    video_path = stitch_video(
        image_paths=image_paths,
        audio_path=audio_path,
        output_path=output_dir / f"{basename}.mp4",
        width=config.resolution_width,
        height=config.resolution_height,
        fps=config.fps,
    )

    return GeneratedVideo(video_path=video_path, topic=topic, script_text=script_text)


