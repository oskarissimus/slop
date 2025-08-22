from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Dict, Any
import subprocess
import tempfile


def _ffmpeg_bin() -> str:
    return "ffmpeg"


def _ffprobe_bin() -> str:
    return "ffprobe"


def _compute_durations_from_alignment(
    alignment: Optional[Dict[str, Any]],
    num_images: int,
    audio_duration_fallback: float,
) -> List[float]:
    """Compute per-image durations using alignment if available; otherwise even split.

    Alignment schema may vary. We accept a generic structure with optional word or sentence timestamps.
    If alignment lacks enough info, fall back to even split.
    """
    if not alignment:
        return [max(0.1, audio_duration_fallback / max(1, num_images))] * max(1, num_images)
    # Try to parse segments of form [{start, end, text}]
    segments = None
    # Prefer character-level if available
    chars = alignment.get("characters") if isinstance(alignment, dict) else None
    starts = alignment.get("character_start_times_seconds") if isinstance(alignment, dict) else None
    ends = alignment.get("character_end_times_seconds") if isinstance(alignment, dict) else None
    if isinstance(chars, list) and isinstance(starts, list) and isinstance(ends, list) and len(chars) == len(starts) == len(ends) and len(chars) > 0:
        segments = [{"start": float(s), "end": float(e), "text": c} for c, s, e in zip(chars, starts, ends)]
    else:
        for key in ("segments", "words", "sentences"):
            value = alignment.get(key) if isinstance(alignment, dict) else None
            if isinstance(value, list) and value:
                segments = value
                break
    if not segments:
        return [max(0.1, audio_duration_fallback / max(1, num_images))] * max(1, num_images)
    # Map segments into contiguous buckets of num_images
    try:
        starts_list: List[float] = []
        ends_list: List[float] = []
        for seg in segments:
            start = float(seg.get("start", 0.0))
            end = float(seg.get("end", start))
            starts_list.append(start)
            ends_list.append(end)
        total_dur = max(audio_duration_fallback, max(ends_list) if ends_list else 0.0)
        # Split timeline into num_images bins and compute durations per bin
        bin_edges = [i * (total_dur / max(1, num_images)) for i in range(max(1, num_images) + 1)]
        durations: List[float] = []
        for i in range(max(1, num_images)):
            bin_start = bin_edges[i]
            bin_end = bin_edges[i + 1]
            # Sum portion of segments overlapping this bin
            acc = 0.0
            for s, e in zip(starts_list, ends_list):
                overlap = max(0.0, min(bin_end, e) - max(bin_start, s))
                acc += overlap
            # Ensure minimum sensible duration
            durations.append(max(0.1, acc if acc > 0 else (total_dur / max(1, num_images))))
        return durations
    except Exception:
        return [max(0.1, audio_duration_fallback / max(1, num_images))] * max(1, num_images)


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
    # Probe audio duration, fallback if ffprobe missing
    try:
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
    except Exception:
        audio_duration = 120.0

    # Compute per-image durations (either alignment-driven or even-split)
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

    return output_path