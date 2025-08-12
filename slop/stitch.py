from __future__ import annotations

from pathlib import Path
from typing import List
import subprocess
import tempfile


def _ffmpeg_bin() -> str:
    return "ffmpeg"


def _ffprobe_bin() -> str:
    return "ffprobe"


def stitch_video(
    image_paths: List[Path],
    audio_path: Path,
    output_path: Path,
    width: int,
    height: int,
    fps: int,
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
    duration_per_image = max(0.1, audio_duration / total_images)

    with tempfile.TemporaryDirectory() as tmpdir:
        list_path = Path(tmpdir) / "images.txt"
        with open(list_path, "w", encoding="utf-8") as f:
            for img in image_paths:
                abs_img = Path(img).resolve()
                f.write(f"file {abs_img}\n")
                f.write(f"duration {duration_per_image}\n")
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
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
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


