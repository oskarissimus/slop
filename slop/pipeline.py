from __future__ import annotations

from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
import os
import json

from .config import AppConfig, apply_env_overrides
from .topics import generate_topic
from .scriptgen import generate_script, generate_scenes, Scene
from .images import generate_images
from .voice import synthesize_voice_with_alignment
from .stitch import stitch_video


@dataclass
class GeneratedVideo:
    video_path: Path
    topic: str
    script_text: str


def generate_video_pipeline(config: AppConfig, output_dir: Path) -> GeneratedVideo:
    output_dir.mkdir(parents=True, exist_ok=True)
    # Apply environment overrides for test/production model switching
    config = apply_env_overrides(config)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    basename = f"video_{timestamp}"
    work_dir = output_dir / basename
    work_dir.mkdir(parents=True, exist_ok=True)

    # 1) Determine prompt/topic. If PROMPT provided via env/workflow, use it; else auto-generate.
    prompt_raw = os.getenv("PROMPT")
    if prompt_raw:
        prompt_detail = prompt_raw.strip()
        topic = prompt_detail[:120]
    else:
        prompt_detail = None
        topic = generate_topic()

    # 2) Generate structured scenes
    num_scenes = max(1, config.num_images)
    scenes: List[Scene] = generate_scenes(
        prompt_detail=prompt_detail or topic,
        target_duration_seconds=config.duration_seconds,
        num_scenes=num_scenes,
        model=config.chat_model,
    )

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

    # 4) Generate images asynchronously per scene (provider-configurable)
    image_paths = generate_images(
        image_prompts=image_prompts,
        script_text=None,
        num_images=config.num_images,
        output_dir=work_dir,
        provider=config.image_provider,
        image_model=config.image_model,
        image_size=config.image_size,
        image_quality=config.image_quality,
        scene_llm_model=config.scene_llm_model,
    )

    # 5) Synthesize audio with alignment information
    audio_path, alignment = synthesize_voice_with_alignment(
        text=script_text,
        voice_id=config.voice_id,
        output_dir=work_dir,
        model_id=config.tts_model_id,
        output_format=config.tts_output_format,
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
    )

    return GeneratedVideo(video_path=video_path, topic=topic, script_text=script_text)


