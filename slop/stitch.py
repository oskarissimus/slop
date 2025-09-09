from __future__ import annotations

from pathlib import Path
from typing import List, Optional
import subprocess
import logging

from elevenlabs.types.character_alignment_response_model import CharacterAlignmentResponseModel

from .scriptgen import Scene


logger = logging.getLogger(__name__)

def calculate_scenes_start_times(alignment: CharacterAlignmentResponseModel, scenes: List[Scene]) -> List[float]:
    """
    Calculate the start times of each scene based on the alignment.
    """
    scenes_start_times = [0]
    i = 0
    for scene in scenes:
        i+=len(scene.script)+1
        if i < len(alignment.character_start_times_seconds):
            scenes_start_times.append(alignment.character_start_times_seconds[i])
        else:
            logger.warning("[stitch] scene script is longer than alignment | scene=%s", scene.script)
            scenes_start_times.append(alignment.character_end_times_seconds[-1])
    return scenes_start_times


def build_concat_list_content(image_paths: List[Path], durations: List[float]) -> str:
    if not image_paths:
        raise ValueError("image_paths must not be empty")

    lines: List[str] = []
    for img, duration in zip(image_paths, durations):
        abs_img = Path(img).resolve()
        lines.append(f"file {abs_img}")
        lines.append(f"duration {duration}")

    # Repeat last frame without duration to flush concat demuxer timing
    abs_last = Path(image_paths[-1]).resolve()
    lines.append(f"file {abs_last}")

    return "\n".join(lines) + "\n"


def stitch_video(
    image_paths: List[Path],
    audio_path: Path,
    output_path: Path,
    width: int,
    height: int,
    fps: int,
    *,
    alignment: Optional[CharacterAlignmentResponseModel] = None,
    scenes: Optional[List[Scene]] = None,
    show_clock: bool = False,
    durations_by_scene: Optional[List[float]] = None,
):
    output_path.parent.mkdir(parents=True, exist_ok=True)

    total_images = max(1, len(image_paths))
    logger.info(
        "[stitch] start | images=%d audio=%s output=%s size=%dx%d fps=%d",
        total_images,
        str(audio_path),
        str(output_path),
        width,
        height,
        fps,
    )

    if not scenes or len(scenes) != total_images:
        raise ValueError("scenes must be provided and match number of images")

    probe_cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(audio_path),
    ]
    result = subprocess.run(probe_cmd, capture_output=True, text=True, check=True)
    audio_duration = float((result.stdout or "").strip())
    logger.info("[stitch] probed audio duration | seconds=%.3f", audio_duration)

    # Compute per-image durations from alignment by scenes
    if durations_by_scene is not None:
        if len(durations_by_scene) != total_images:
            raise ValueError("durations_by_scene length must match number of images")
        durations = list(durations_by_scene)
        logger.info("[stitch] using provided durations_by_scene | durations=%s", durations)
    else:
        if alignment is None:
            raise ValueError("alignment or durations_by_scene must be provided")
        scenes_start_times = calculate_scenes_start_times(alignment, scenes)
        durations = [scenes_start_times[i+1] - scenes_start_times[i] for i in range(len(scenes_start_times)-1)]
        durations.append(audio_duration - scenes_start_times[-1])
        logger.info("[stitch] computed durations from alignment | durations=%s", durations)


    # Save images.txt to disk in the same directory as the output video
    list_path = output_path.parent / "images.txt"
    content = build_concat_list_content(image_paths, durations)
    list_path.write_text(content, encoding="utf-8")

    logger.info("[stitch] concatenating images into silent video | list=%s", str(list_path))
    # Build video filter chain and optionally overlay a running clock
    base_filter = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},format=yuv420p"
    )
    if show_clock:
        # Reasonable font size relative to height; bottom-right with padding
        font_size = max(height // 32, 24)
        clock_filter = (
            "drawtext="
            f"fontcolor=white:fontsize={font_size}:"
            "box=1:boxcolor=black@0.5:boxborderw=6:"
            "text='%{pts\\:hms}':x=w-tw-24:y=h-th-24"
        )
        vf_filter = f"{base_filter},{clock_filter}"
        logger.info("[stitch] clock overlay enabled | fontsize=%d", font_size)
    else:
        vf_filter = base_filter

    interim_video = output_path.parent / "video_silent.mp4"
    cmd_video = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_path),
        "-vf",
        vf_filter,
        "-r",
        str(fps),
        "-pix_fmt",
        "yuv420p",
        str(interim_video),
    ]
    subprocess.run(cmd_video, check=True)

    logger.info("[stitch] muxing video with audio | video=%s audio=%s", str(interim_video), str(audio_path))
    cmd_mux = [
        "ffmpeg",
        "-y",
        "-i",
        str(interim_video),
        "-i",
        str(audio_path),
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        "-shortest",
        str(output_path),
    ]
    subprocess.run(cmd_mux, check=True)

    logger.info("[stitch] done | output=%s", str(output_path))
    return output_path