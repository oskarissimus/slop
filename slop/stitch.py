from __future__ import annotations

from pathlib import Path
from typing import List
import subprocess
import tempfile
import shutil
import wave

try:
    import imageio_ffmpeg  # type: ignore
except Exception:  # pragma: no cover
    imageio_ffmpeg = None  # type: ignore


def _resolve_ffmpeg() -> str:
    # Prefer system ffmpeg if available
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        return ffmpeg_path
    # Try imageio-ffmpeg bundled binary
    if imageio_ffmpeg is not None:
        try:
            return imageio_ffmpeg.get_ffmpeg_exe()  # type: ignore[attr-defined]
        except Exception:
            pass
    raise FileNotFoundError(
        "ffmpeg not found. Install system ffmpeg or `pip install imageio-ffmpeg` to download a local binary."
    )


def _ffprobe_bin() -> str:
    # Use system ffprobe if available; otherwise fall back to best effort
    ffprobe = shutil.which("ffprobe")
    return ffprobe or "ffprobe"


def _wav_duration_seconds(path: Path) -> float | None:
    try:
        if path.suffix.lower() == ".wav" and path.exists():
            with wave.open(str(path), "rb") as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                return frames / float(rate)
    except Exception:
        return None
    return None


def stitch_video(
    image_paths: List[Path],
    audio_path: Path,
    output_path: Path,
    width: int,
    height: int,
    fps: int,
):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = _resolve_ffmpeg()

    total_images = max(1, len(image_paths))
    # Probe audio duration, fallback if ffprobe missing
    audio_duration = _wav_duration_seconds(audio_path) or 120.0
    if audio_duration == 120.0:
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
            pass
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


