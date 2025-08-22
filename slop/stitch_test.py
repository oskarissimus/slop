from datetime import datetime
from pathlib import Path

from slop.stitch import build_concat_list_content, calculate_scenes_start_times, stitch_video


def test_build_concat_list_content():
    durations = [8.661, 9.009, 6.105999999999998, 7.6739999999999995, 6.722999999999999, 7.744, 7.813000000000002, 7.743000000000002, 8.150000000000006, 7.313999999999993, 9.21799999999999, 7.697000000000003]
    image_paths = [Path(f"/image{i}.png") for i in range(len(durations))]
    content = build_concat_list_content(image_paths, durations)
    assert content == """file /image0.png
duration 8.661
file /image1.png
duration 9.009
file /image2.png
duration 6.105999999999998
file /image3.png
duration 7.6739999999999995
file /image4.png
duration 6.722999999999999
file /image5.png
duration 7.744
file /image6.png
duration 7.813000000000002
file /image7.png
duration 7.743000000000002
file /image8.png
duration 8.150000000000006
file /image9.png
duration 7.313999999999993
file /image10.png
duration 9.21799999999999
file /image11.png
duration 7.697000000000003
file /image11.png
"""

def test_stitch_video(alignment, scenes):
    dir = Path("outputs/video_20250822_214810")
    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    image_paths = [dir / f"frame_{i:03d}.png" for i in range(12)]
    audio_path = dir / "voice.mp3"
    output_path = dir / f"test_video_{now}.mp4"
    width = 1080
    height = 1920
    fps = 24
    stitch_video(image_paths, audio_path, output_path, width, height, fps, alignment=alignment, scenes=scenes, show_clock=True)


def test_calculate_scenes_start_times(alignment, scenes):
    scenes_start_times = calculate_scenes_start_times(alignment, scenes)
    assert scenes_start_times == [0, 9.369, 18.553, 24.985, 32.937, 39.997, 48.031, 56.379, 64.505, 72.899, 80.596, 90.151, 97.848]