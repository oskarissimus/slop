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

    Requires alignment to include characters and per-character start/end times.
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

    logger.info(
        "[stitch] alignment received | chars=%d first_start=%.3f last_end=%.3f",
        len(characters),
        float(start_times[0]),
        float(end_times[-1]),
    )

    # Build simple segments from per-character timings
    segments = [{"start": float(s), "end": float(e)} for s, e in zip(start_times, end_times)]

    total_duration_seconds = max(audio_duration_fallback, float(end_times[-1]))
    bin_edges = [i * (total_duration_seconds / max(1, num_images)) for i in range(max(1, num_images) + 1)]

    durations: List[float] = []
    for i in range(max(1, num_images)):
        bin_start = bin_edges[i]
        bin_end = bin_edges[i + 1]
        overlap_sum = 0.0
        for seg in segments:
            s = seg["start"]
            e = seg["end"]
            overlap = max(0.0, min(bin_end, e) - max(bin_start, s))
            overlap_sum += overlap
        durations.append(max(0.1, overlap_sum or (total_duration_seconds / max(1, num_images))))

    logger.info(
        "[stitch] computed durations | count=%d total=%.3f first=%.3f last=%.3f",
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