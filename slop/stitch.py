from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Dict, Any
import subprocess
import tempfile
import logging

from .scriptgen import Scene


logger = logging.getLogger(__name__)


def _ffmpeg_bin() -> str:
    return "ffmpeg"


def _ffprobe_bin() -> str:
    return "ffprobe"


def _compute_durations_from_alignment(
    alignment: Optional[Dict[str, Any]],
    scenes: List[Scene],
    audio_duration_fallback: float,
) -> List[float]:
    """Compute per-image durations using character-level alignment per scene.

    The combined TTS input is " ".join(scene.script for scene in scenes).strip().
    We map each scene to a contiguous character index range in the combined text
    and compute the scene duration as (last_char_end - first_char_start).
    """
    if not isinstance(alignment, dict):
        raise ValueError("alignment must be provided and be a dict with character-level timings")
    if not scenes:
        raise ValueError("scenes must be provided")

    characters = alignment.get("characters")
    start_times = alignment.get("character_start_times_seconds")
    end_times = alignment.get("character_end_times_seconds")

    if not (isinstance(characters, list) and isinstance(start_times, list) and isinstance(end_times, list)):
        raise ValueError("alignment missing required character-level keys")
    if not (len(characters) == len(start_times) == len(end_times) and len(characters) > 0):
        raise ValueError("alignment character arrays must be same non-zero length")

    combined_text = " ".join(s.script for s in scenes).strip()
    if len(combined_text) != len(characters):
        logger.warning(
            "[stitch] combined_text length != characters length | combined=%d chars=%d",
            len(combined_text), len(characters)
        )
    # Compute index ranges for each scene based on join with single spaces
    ranges: List[tuple[int, int]] = []
    offset = 0
    for idx, scene in enumerate(scenes):
        scene_text = scene.script
        start_idx = offset
        end_idx_exclusive = start_idx + len(scene_text)
        ranges.append((start_idx, end_idx_exclusive))
        offset = end_idx_exclusive
        if idx < len(scenes) - 1:
            offset += 1  # single space between scenes

    durations: List[float] = []
    for (start_idx, end_idx_exclusive) in ranges:
        if start_idx < 0 or end_idx_exclusive <= start_idx or end_idx_exclusive > len(characters):
            raise ValueError("scene index range is out of alignment bounds")
        first_start = float(start_times[start_idx])
        last_end = float(end_times[end_idx_exclusive - 1])
        dur = max(0.1, last_end - first_start)
        durations.append(dur)

    total_duration_seconds = max(audio_duration_fallback, float(end_times[-1]))
    logger.info(
        "[stitch] durations by scenes | scenes=%d sum=%.3f audio=%.3f first=%.3f last=%.3f",
        len(durations), sum(durations), total_duration_seconds, durations[0], durations[-1]
    )

    return durations


def stitch_video(
    image_paths: List[Path],
    audio_path: Path,
    output_path: Path,
    width: int,
    height: int,
    fps: int,
    *,
    alignment: Optional[Dict[str, Any]] = None,
    scenes: Optional[List[Scene]] = None,
):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = _ffmpeg_bin()

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

    # Probe audio duration (raise on failure)
    ffprobe = _ffprobe_bin()
    probe_cmd = [
        ffprobe,
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
    durations = _compute_durations_from_alignment(alignment, scenes, audio_duration)

    with tempfile.TemporaryDirectory() as tmpdir:
        list_path = Path(tmpdir) / "images.txt"
        with open(list_path, "w", encoding="utf-8") as f:
            for img, dur in zip(image_paths, durations):
                abs_img = Path(img).resolve()
                f.write(f"file {abs_img}\n")
                f.write(f"duration {dur}\n")
            # Repeat last frame without duration to flush concat demuxer timing
            abs_last = Path(image_paths[-1]).resolve()
            f.write(f"file {abs_last}\n")

        logger.info("[stitch] concatenating images into silent video | list=%s", str(list_path))
        interim_video = Path(tmpdir) / "video_silent.mp4"
        cmd_video = [
            ffmpeg,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_path),
            "-vf",
            f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},format=yuv420p",
            "-r",
            str(fps),
            "-pix_fmt",
            "yuv420p",
            str(interim_video),
        ]
        subprocess.run(cmd_video, check=True)

        logger.info("[stitch] muxing video with audio | video=%s audio=%s", str(interim_video), str(audio_path))
        cmd_mux = [
            ffmpeg,
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