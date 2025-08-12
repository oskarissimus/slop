from __future__ import annotations

from pathlib import Path
from typing import List

from PIL import Image, ImageDraw, ImageFont
from tenacity import retry, stop_after_attempt, wait_exponential
from openai import OpenAI


def _fallback_generate_placeholder(text: str, output_dir: Path, index: int) -> Path:
    output_path = output_dir / f"frame_{index:03d}.png"
    width, height = 1080, 1920
    image = Image.new("RGB", (width, height), color=(20, 20, 20))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("Arial.ttf", 48)
    except Exception:
        font = ImageFont.load_default()
    wrapped = text[:100]
    draw.multiline_text((60, 60), wrapped, fill=(235, 235, 235), font=font, spacing=6)
    image.save(output_path)
    return output_path


@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3))
def _generate_single_image_openai(prompt: str, index: int, output_dir: Path) -> Path:
    client = OpenAI()
    resp = client.images.generate(
        model="gpt-image-1",
        prompt=prompt,
        size="1024x1024",
        quality="high",
        n=1,
    )
    b64 = resp.data[0].b64_json
    import base64

    img_bytes = base64.b64decode(b64)
    out_path = output_dir / f"frame_{index:03d}.png"
    with open(out_path, "wb") as f:
        f.write(img_bytes)
    return out_path


def split_script_into_prompts(script_text: str, num_images: int) -> List[str]:
    sentences = [s.strip() for s in script_text.split(".") if s.strip()]
    if not sentences:
        sentences = [script_text]
    # Evenly sample sentences to num_images
    step = max(1, len(sentences) // max(1, num_images))
    selected = sentences[::step][:num_images]
    # If too few, pad with last
    while len(selected) < num_images:
        selected.append(selected[-1])
    return selected


def generate_images(script_text: str, num_images: int, output_dir: Path, provider: str = "placeholder") -> List[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    prompts = split_script_into_prompts(script_text, num_images)
    image_paths: List[Path] = []
    for i, p in enumerate(prompts):
        if provider == "openai":
            try:
                image_paths.append(_generate_single_image_openai(p, i, output_dir))
            except Exception:
                # Graceful fallback if OpenAI Images is unavailable or permission denied
                image_paths.append(_fallback_generate_placeholder(p, output_dir, i))
        else:
            image_paths.append(_fallback_generate_placeholder(p, output_dir, i))
    return image_paths


