from __future__ import annotations

from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
import os
import json
import asyncio
import logging

from .config import AppConfig
from .utils import sanitize_title
from .scriptgen import generate_topic_and_scenes
from .images import generate_images, generate_images_async
from .voice import (
    synthesize_voice_with_alignment,
    synthesize_voice_with_alignment_async,
    synthesize_voice_with_alignment_chunked_async,
)
from .stitch import stitch_video


logger = logging.getLogger(__name__)

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

    logger.info(
        "[pipeline] start | basename=%s duration=%ds fps=%d size=%dx%d images=%d chat_model=%s image_model=%s",
        basename,
        config.duration_seconds,
        config.fps,
        config.resolution_width,
        config.resolution_height,
        config.num_images,
        config.chat_model,
        config.image_model,
    )

    # 1) Always use combined generator (no fallback).
    prompt_raw = os.getenv("PROMPT")
    num_scenes = max(1, config.num_images)
    user_input = prompt_raw.strip() if prompt_raw else ""
    logger.info("[pipeline] generating topic and scenes | words_target≈%d scenes=%d", int(config.duration_seconds * 2.5), num_scenes)
    topic, scenes = generate_topic_and_scenes(
        input_text=user_input,
        target_duration_seconds=config.duration_seconds,
        num_scenes=num_scenes,
        model=config.chat_model,
        temperature=config.temperature,
    )
    logger.info("[pipeline] got topic and scenes | topic=\"%s\" scenes=%d", topic, len(scenes))
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

    # Persist the intended title for downstream upload steps
    try:
        (work_dir / "title.txt").write_text(topic, encoding="utf-8")
    except Exception:
        pass

    # 3) Prepare image prompts and narration script
    image_prompts = [s.image_description for s in scenes]
    script_text = " ".join(s.script for s in scenes).strip()

    # 4 & 5) Generate images and synthesize audio concurrently
    logger.info("[pipeline] starting parallel image+audio generation")
    async def run_parallel() -> tuple[list[Path], Path, object, list[float]]:
        images_task = generate_images_async(
            image_prompts=image_prompts,
            num_images=config.num_images,
            output_dir=work_dir,
            image_model=config.image_model,
            image_size=f"{config.resolution_width}x{config.resolution_height}",
            image_quality=config.image_quality,
        )
        tts_task = synthesize_voice_with_alignment_chunked_async(
            scenes=scenes,
            voice_id=config.voice_id,
            output_dir=work_dir,
            model_id=config.tts_model_id,
            output_format=config.tts_output_format,
            concurrency=max(1, int(getattr(config, "tts_concurrency", 4))),
            stability=config.stability,
            similarity_boost=config.similarity_boost,
            style=config.style,
            use_speaker_boost=config.use_speaker_boost,
            speed=config.speed,
            api_key=getattr(config, "elevenlabs_api_key", None),
        )
        image_paths, (audio_path, durations_by_scene) = await asyncio.gather(images_task, tts_task)
        return image_paths, audio_path, None, durations_by_scene

    image_paths, audio_path, alignment, durations_by_scene = asyncio.run(run_parallel())
    logger.info(
        "[pipeline] finished image+audio | images=%d audio=%s",
        len(image_paths),
        str(audio_path),
    )

    # 6) Stitch video, using alignment to time images if available
    logger.info("[pipeline] stitching video")
    video_path = stitch_video(
        image_paths=image_paths,
        audio_path=audio_path,
        output_path=output_dir / f"{basename}.mp4",
        width=config.resolution_width,
        height=config.resolution_height,
        fps=config.fps,
        alignment=alignment,
        scenes=scenes,
        durations_by_scene=durations_by_scene,
    )

    logger.info("[pipeline] done | output=%s topic=\"%s\"", str(video_path), topic)
    return GeneratedVideo(video_path=video_path, topic=topic, script_text=script_text)


def render_video_from_scenes(
    *,
    config: AppConfig,
    scenes: list["Scene"],
    output_dir: Path,
    topic: str | None = None,
) -> GeneratedVideo:
    """Render a video from provided scenes without generating them.

    Uses the same image generation, TTS (chunked with durations), and stitching steps
    as the main pipeline. Writes working artifacts into a timestamped subdirectory
    under the provided output directory.
    """
    # Local import to avoid circular import at module load time
    from .scriptgen import Scene  # type: ignore

    if not scenes:
        raise ValueError("scenes must not be empty")

    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    basename = f"video_{timestamp}"
    work_dir = output_dir / basename
    work_dir.mkdir(parents=True, exist_ok=True)

    # Persist optional topic/title for downstream steps
    safe_topic = sanitize_title(topic or "Manual Scenes")
    try:
        (work_dir / "title.txt").write_text(safe_topic, encoding="utf-8")
    except Exception:
        pass

    # Always write scenes used for reproducibility
    try:
        scenario_dict = {"scenes": [s.model_dump() for s in scenes]}
        scenes_json_path = work_dir / "scenes.json"
        with open(scenes_json_path, "w", encoding="utf-8") as f:
            json.dump(scenario_dict, f, ensure_ascii=False, indent=2)
        print(f"[scenes] wrote {scenes_json_path}")
    except Exception:
        pass

    # Prepare image prompts and narration script
    image_prompts = [s.image_description for s in scenes]
    script_text = " ".join(s.script for s in scenes).strip()

    logger.info("[pipeline] starting parallel image+audio generation (render from scenes)")

    async def run_parallel() -> tuple[list[Path], Path, object, list[float]]:
        images_task = generate_images_async(
            image_prompts=image_prompts,
            num_images=len(scenes),
            output_dir=work_dir,
            image_model=config.image_model,
            image_size=f"{config.resolution_width}x{config.resolution_height}",
            image_quality=config.image_quality,
        )
        tts_task = synthesize_voice_with_alignment_chunked_async(
            scenes=scenes,
            voice_id=config.voice_id,
            output_dir=work_dir,
            model_id=config.tts_model_id,
            output_format=config.tts_output_format,
            concurrency=max(1, int(getattr(config, "tts_concurrency", 4))),
            stability=config.stability,
            similarity_boost=config.similarity_boost,
            style=config.style,
            use_speaker_boost=config.use_speaker_boost,
            speed=config.speed,
            api_key=getattr(config, "elevenlabs_api_key", None),
        )
        image_paths, (audio_path, durations_by_scene) = await asyncio.gather(images_task, tts_task)
        return image_paths, audio_path, None, durations_by_scene

    image_paths, audio_path, alignment, durations_by_scene = asyncio.run(run_parallel())

    logger.info(
        "[pipeline] finished image+audio (render from scenes) | images=%d audio=%s",
        len(image_paths),
        str(audio_path),
    )

    logger.info("[pipeline] stitching video (render from scenes)")
    video_path = stitch_video(
        image_paths=image_paths,
        audio_path=audio_path,
        output_path=output_dir / f"{basename}.mp4",
        width=config.resolution_width,
        height=config.resolution_height,
        fps=config.fps,
        alignment=alignment,
        scenes=scenes,
        durations_by_scene=durations_by_scene,
    )

    logger.info("[pipeline] done (render from scenes) | output=%s topic=\"%s\"", str(video_path), safe_topic)
    return GeneratedVideo(video_path=video_path, topic=safe_topic, script_text=script_text)


