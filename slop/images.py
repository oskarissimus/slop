from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import List, Tuple, Optional

from tenacity import retry, stop_after_attempt, wait_exponential
from openai import AsyncOpenAI


def _fallback_generate_placeholder(text: str, output_dir: Path, index: int) -> Path:
	output_path = output_dir / f"frame_{index:03d}.png"
	width, height = 1080, 1920
	# Plain background without any text to avoid on-frame captions
	try:
		from PIL import Image, ImageDraw
		# Use a mid-gray background so it's not perceived as black
		image = Image.new("RGB", (width, height), color=(80, 80, 80))
		draw = ImageDraw.Draw(image)
		# add a subtle vignette rectangle to make placeholder less flat
		margin = 40
		draw.rectangle([margin, margin, width - margin, height - margin], outline=(180, 180, 180), width=4)
		# draw two diagonal lines to add some structure
		draw.line([(0, 0), (width, height)], fill=(130, 130, 130), width=3)
		draw.line([(width, 0), (0, height)], fill=(130, 130, 130), width=3)
		image.save(output_path)
		try:
			print(f"[images] placeholder saved: {output_path}")
		except Exception:
			pass
	except Exception:
		# If Pillow is not available, write a minimal PNG header with no content using raw bytes is complex;
		# instead, just create an empty file as a last resort placeholder.
		with open(output_path, "wb") as f:
			f.write(b"")
		try:
			print(f"[images] placeholder (no Pillow) wrote empty file: {output_path}")
		except Exception:
			pass
	return output_path


@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3))
async def _generate_single_image_openai_async(
	client: AsyncOpenAI,
	prompt: str,
	index: int,
	output_dir: Path,
	*,
	model: str,
	size: str,
	quality: Optional[str] = None,
) -> Path:
	# Strictly request vertical images from OpenAI; do not fall back to square sizes unless specified
	import base64
	params = {
		"model": model,
		"prompt": prompt,
		"size": size,
		"n": 1,
	}
	if quality:
		params["quality"] = quality
	try:
		try:
			print(f"[images/openai] request i={index} model={model} size={size} quality={quality} prompt_len={len(prompt)}")
		except Exception:
			pass
		resp = await client.images.generate(**params)
		b64 = resp.data[0].b64_json
		img_bytes = base64.b64decode(b64)
	except Exception:
		# Secondary attempt with gpt-image-1 if not already used
		fallback_model = "gpt-image-1" if model != "gpt-image-1" else "dall-e-3"
		try:
			print(f"[images/openai] fallback i={index} -> model={fallback_model}")
		except Exception:
			pass
		resp = await client.images.generate(
			model=fallback_model,
			prompt=prompt,
			size=size,
			n=1,
		)
		b64 = resp.data[0].b64_json
		img_bytes = base64.b64decode(b64)
	out_path = output_dir / f"frame_{index:03d}.png"
	with open(out_path, "wb") as f:
		f.write(img_bytes)
	try:
		sz = os.path.getsize(out_path)
		print(f"[images/openai] saved i={index} -> {out_path} ({sz} bytes)")
	except Exception:
		pass
	# Ensure no alpha channel (avoid transparent images turning into black frames after ffmpeg)
	try:
		from PIL import Image  # type: ignore
		from PIL import ImageStat, ImageOps, ImageEnhance  # type: ignore
		with Image.open(out_path) as im:
			if im.mode in ("RGBA", "LA", "P"):
				# Flatten on white background to avoid black frames when transparency dominates
				rgb = Image.new("RGB", im.size, (255, 255, 255))
				if im.mode in ("RGBA", "LA"):
					rgb.paste(im, mask=im.split()[-1])
				else:
					rgb.paste(im)
				rgb.save(out_path)
			elif im.mode != "RGB":
				im.convert("RGB").save(out_path)
		# Post-process: if image is extremely dark, attempt to auto-contrast and brighten
		with Image.open(out_path) as check:
			luma = check.convert("L")
			mean = ImageStat.Stat(luma).mean[0]
			if mean < 10:
				try:
					print(f"[images/openai] image too dark (mean={mean:.2f}), applying brighten+autocontrast i={index}")
				except Exception:
					pass
				auto = ImageOps.autocontrast(check, cutoff=1)
				bright = ImageEnhance.Brightness(auto).enhance(1.8)
				bright.save(out_path)
	except Exception:
		pass
	return out_path


## Removed: _describe_scenes_with_llm_async — the main flow now always supplies image prompts from structured scenes.


def generate_images(
	*,
	image_prompts: Optional[List[str]] = None,
	num_images: int,
	output_dir: Path,
	provider: str = "openai",
	image_model: str = "dall-e-3",
	image_size: str = "1024x1536",
	image_quality: Optional[str] = "standard",
) -> List[Path]:
	output_dir.mkdir(parents=True, exist_ok=True)
	if image_prompts is None:
		raise ValueError(
			"image_prompts must be provided; automatic scene description generation was removed. "
			"Use scriptgen.generate_topic_and_scenes to obtain prompts."
		)
	scene_prompts = image_prompts[:num_images]
	while len(scene_prompts) < num_images:
		scene_prompts.append(scene_prompts[-1])

	# Basic run metadata
	try:
		preview = (scene_prompts[0] if scene_prompts else "")[:160].replace("\n", " ")
		print(
			f"[images] provider={provider} model={image_model} size={image_size} quality={image_quality} "
			f"num_images={num_images} first_prompt_preview=\"{preview}\""
		)
	except Exception:
		pass

	# Save prompts for debugging
	try:
		prompts_file = output_dir / "scene_prompts.txt"
		with open(prompts_file, "w", encoding="utf-8") as f:
			for i, p in enumerate(scene_prompts):
				f.write(f"[{i:03d}] {p}\n")
	except Exception:
		pass

	# Always use async for OpenAI image generation with a conservative concurrency cap.
	concurrency = min(12, max(1, len(scene_prompts)))

	if provider == "openai":
		paths = asyncio.run(
			_generate_images_async_openai(
				scene_prompts, output_dir, concurrency, model=image_model, size=image_size, quality=image_quality
			)
		)
		# Print sizes for quick diagnostics
		try:
			for p in paths:
				print(f"[images] file {p} -> {os.path.getsize(p)} bytes")
		except Exception:
			pass
		return paths

	# Placeholder provider uses a simple synchronous loop
	image_paths: List[Path] = []
	for i, p in enumerate(scene_prompts):
		image_paths.append(_fallback_generate_placeholder(p, output_dir, i))

	return image_paths


async def _generate_images_async_openai(
	prompts: List[str],
	output_dir: Path,
	concurrency: int,
	*,
	model: str,
	size: str,
	quality: Optional[str],
) -> List[Path]:
	client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
	semaphore = asyncio.Semaphore(concurrency)

	async def run_one(i: int, prompt: str) -> Tuple[int, Path]:
		async with semaphore:
			try:
				path = await _generate_single_image_openai_async(client, prompt, i, output_dir, model=model, size=size, quality=quality)
			except Exception:
				# Surface generation failure explicitly; do not silently pad with placeholders
				raise
			return i, path

	tasks = [run_one(i, p) for i, p in enumerate(prompts)]
	results = await asyncio.gather(*tasks)
	ordered_paths: List[Path] = [output_dir / f"frame_{i:03d}.png" for i in range(len(prompts))]
	for i, path in results:
		ordered_paths[i] = path
	return ordered_paths


