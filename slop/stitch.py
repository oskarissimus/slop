from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Dict, Any
import subprocess
import tempfile
import logging


logger = logging.getLogger(__name__)


def _ffmpeg_bin() -> str:
    return "ffmpeg"


def _ffprobe_bin() -> str:
    return "ffprobe"


def _compute_durations_from_alignment(
    alignment: Optional[Dict[str, Any]],
    num_images: int,
    audio_duration_fallback: float,
) -> List[float]:
    """Compute per-image durations using character-level alignment only.

    We split the characters into nearly-equal contiguous groups per image and
    set each image duration to span from the first character's start to the
    last character's end in that group. This reflects character-level timing
    from ElevenLabs alignment.
    """
    if not isinstance(alignment, dict):
        raise ValueError("alignment must be provided and be a dict with character-level timings")

    characters = alignment.get("characters")
    start_times = alignment.get("character_start_times_seconds")
    end_times = alignment.get("character_end_times_seconds")

    if not (isinstance(characters, list) and isinstance(start_times, list) and isinstance(end_times, list)):
        raise ValueError("alignment missing required character-level keys")
    if not (len(characters) == len(start_times) == len(end_times) and len(characters) > 0):
        raise ValueError("alignment character arrays must be same non-zero length")

    total_chars = len(characters)
    total_images = max(1, num_images)

    logger.info(
        "[stitch] alignment received | chars=%d images=%d first_start=%.3f last_end=%.3f",
        total_chars,
        total_images,
        float(start_times[0]),
        float(end_times[-1]),
    )

    # Compute per-image group sizes (nearly equal partitioning of characters)
    base = total_chars // total_images
    remainder = total_chars % total_images
    group_sizes: List[int] = [(base + 1 if i < remainder else base) for i in range(total_images)]

    durations: List[float] = []
    char_index = 0
    total_duration_seconds = max(audio_duration_fallback, float(end_times[-1]))

    for i, size in enumerate(group_sizes):
        if size > 0:
            start_idx = char_index
            end_idx = char_index + size - 1
            start_t = float(start_times[start_idx])
            end_t = float(end_times[end_idx])
            dur = max(0.1, end_t - start_t)
            durations.append(dur)
            char_index += size
        else:
            # No characters assigned to this image; assign a reasonable slice
            durations.append(max(0.1, total_duration_seconds / total_images))

    # In rare cases, rounding can produce total > audio; that's acceptable for slideshow timing
    logger.info(
        "[stitch] durations by character chunks | count=%d sum=%.3f first=%.3f last=%.3f",
        len(durations),
        sum(durations),
        durations[0],
        durations[-1],
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

    # Compute per-image durations from alignment only
    durations = _compute_durations_from_alignment(alignment, total_images, audio_duration)

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