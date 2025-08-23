from __future__ import annotations

from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
import os
import json
import asyncio

from .config import AppConfig
from .utils import sanitize_title
from .scriptgen import generate_topic_and_scenes
from .images import generate_images, generate_images_async
from .voice import synthesize_voice_with_alignment, synthesize_voice_with_alignment_async
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

    # 1) Always use combined generator (no fallback).
    prompt_raw = os.getenv("PROMPT")
    num_scenes = max(1, config.num_images)
    user_input = prompt_raw.strip() if prompt_raw else ""
    topic, scenes = generate_topic_and_scenes(
        input_text=user_input,
        target_duration_seconds=config.duration_seconds,
        num_scenes=num_scenes,
        model=config.chat_model,
    )
    topic = sanitize_title(topic)

    # Write scenes to JSON for manual verification and print to stdout
    try:
        scenario_dict = {"scenes": [s.model_dump() for s in scenes]}
        scenes_json_path = work_dir / "scenes.json"
        with open(scenes_json_path, "w", encoding="utf-8") as f:
            json.dump(scenario_dict, f, ensure_ascii=False, indent=2)
        print(f"[scenes] wrote {scenes_json_path}")
        print(json.dumps(scenario_dict, ensure_ascii=False, indent=2))
    except Exception:
        pass

    # 3) Prepare image prompts and narration script
    image_prompts = [s.image_description for s in scenes]
    script_text = " ".join(s.script for s in scenes).strip()

    # 4 & 5) Generate images and synthesize audio concurrently
    async def run_parallel() -> tuple[list[Path], Path, object]:
        images_task = generate_images_async(
            image_prompts=image_prompts,
            num_images=config.num_images,
            output_dir=work_dir,
            image_model=config.image_model,
            image_size=f"{config.resolution_width}x{config.resolution_height}",
            image_quality=config.image_quality,
        )
        tts_task = synthesize_voice_with_alignment_async(
            text=script_text,
            voice_id=config.voice_id,
            output_dir=work_dir,
            model_id=config.tts_model_id,
            output_format=config.tts_output_format,
            style=config.style,
        )
        image_paths, (audio_path, alignment) = await asyncio.gather(images_task, tts_task)
        return image_paths, audio_path, alignment

    try:
        image_paths, audio_path, alignment = asyncio.run(run_parallel())
    except RuntimeError as e:
        # Fallback for environments where an event loop is already running
        # (e.g., executed under an existing asyncio loop). In that case, run sequentially.
        print(f"[pipeline] asyncio.run failed ({e}); falling back to sequential execution")
        image_paths = generate_images(
            image_prompts=image_prompts,
            num_images=config.num_images,
            output_dir=work_dir,
            image_model=config.image_model,
            image_size=f"{config.resolution_width}x{config.resolution_height}",
            image_quality=config.image_quality,
        )
        audio_path, alignment = synthesize_voice_with_alignment(
            text=script_text,
            voice_id=config.voice_id,
            output_dir=work_dir,
            model_id=config.tts_model_id,
            output_format=config.tts_output_format,
            style=config.style,
        )

    # 6) Stitch video, using alignment to time images if available
    video_path = stitch_video(
        image_paths=image_paths,
        audio_path=audio_path,
        output_path=output_dir / f"{basename}.mp4",
        width=config.resolution_width,
        height=config.resolution_height,
        fps=config.fps,
        alignment=alignment,
        scenes=scenes,
    )

    return GeneratedVideo(video_path=video_path, topic=topic, script_text=script_text)


