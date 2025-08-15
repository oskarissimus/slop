from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import List, Tuple

from tenacity import retry, stop_after_attempt, wait_exponential
from openai import AsyncOpenAI
import json
import re


def _fallback_generate_placeholder(text: str, output_dir: Path, index: int) -> Path:
	output_path = output_dir / f"frame_{index:03d}.png"
	width, height = 1080, 1920
	# Plain dark gradient-like background without any text to avoid on-frame captions
	try:
		from PIL import Image, ImageDraw
		image = Image.new("RGB", (width, height), color=(20, 20, 20))
		draw = ImageDraw.Draw(image)
		# add a subtle vignette rectangle to make placeholder less flat
		margin = 40
		draw.rectangle([margin, margin, width - margin, height - margin], outline=(35, 35, 35), width=4)
		image.save(output_path)
	except Exception:
		# If Pillow is not available, write a minimal PNG header with no content using raw bytes is complex;
		# instead, just create an empty file as a last resort placeholder.
		with open(output_path, "wb") as f:
			f.write(b"")
	return output_path


@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3))
async def _generate_single_image_openai_async(client: AsyncOpenAI, prompt: str, index: int, output_dir: Path) -> Path:
	# Strictly request vertical images from OpenAI; do not fall back to square sizes
	import base64
	try:
		resp = await client.images.generate(
			model="dall-e-3",
			prompt=prompt,
			size="1024x1536",
			quality="standard",
			n=1,
		)
		b64 = resp.data[0].b64_json
		img_bytes = base64.b64decode(b64)
	except Exception:
		# Secondary attempt with gpt-image-1, still enforcing vertical size
		resp = await client.images.generate(
			model="gpt-image-1",
			prompt=prompt,
			size="1024x1536",
			n=1,
		)
		b64 = resp.data[0].b64_json
		img_bytes = base64.b64decode(b64)
	out_path = output_dir / f"frame_{index:03d}.png"
	with open(out_path, "wb") as f:
		f.write(img_bytes)
	# Ensure no alpha channel (avoid transparent images turning into black frames after ffmpeg)
	try:
		from PIL import Image  # type: ignore
		with Image.open(out_path) as im:
			if im.mode in ("RGBA", "LA", "P"):
				rgb = Image.new("RGB", im.size, (0, 0, 0))
				if im.mode in ("RGBA", "LA"):
					rgb.paste(im, mask=im.split()[-1])
				else:
					rgb.paste(im)
				rgb.save(out_path)
			elif im.mode != "RGB":
				im.convert("RGB").save(out_path)
	except Exception:
		pass
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


def _extract_json_array(text: str) -> str:
	"""Extract a top-level JSON array from free-form text, stripping code fences if present."""
	# Remove common code fences
	clean = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE)
	# Find the first [ ... ] block
	start = clean.find("[")
	end = clean.rfind("]")
	if start != -1 and end != -1 and end > start:
		return clean[start : end + 1]
	return clean


async def _generate_storyboard_prompts_llm_async(script_text: str, num_images: int) -> List[dict]:
	"""Single-call storyboard prompt generation enforcing cross-frame continuity.

	Returns a list of dicts with at least a "prompt" key.
	"""
	client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
	system_msg = (
		"Jesteś doświadczonym storyboardzistą i art directorem. Tworzysz spójny zestaw opisów kadrów do pionowego wideo 9:16. "
		"Zachowujesz ciągłość postaci, rekwizytów, palety kolorów, epoki i nastroju między kolejnymi ujęciami. "
		"Nigdy nie umieszczasz tekstu na obrazie. Skupiasz się na fotorealizmie i filmowej kompozycji."
	)
	user_msg = (
		"Na podstawie poniższego skryptu przygotuj listę {n} spójnych kadrów (beats), które opowiadają historię od początku do końca. "
		"Każdy element listy powinien zawierać klucz 'prompt' (1–3 zdania po polsku, bez żadnego tekstu na obrazie) oraz krótkie 'continuity' (co utrzymać: bohater, strój, rekwizyty, pora dnia, paleta, miejsce). "
		"Zwróć WYŁĄCZNIE poprawny JSON: tablicę {n} obiektów. Bez komentarzy i bez dodatkowego tekstu.\n\n"
		f"Skrypt:\n{script}\n\n"
		"Wymagania wizualne dla każdego kadru: pion 9:16, pełny kadr, brak ramek, brak czarnych pasów, naturalne światło filmowe, wysoki realizm skóry i materiałów, brak znaków wodnych."
	).format(n=num_images, script=script_text)

	resp = await client.chat.completions.create(
		model="gpt-4o-mini",
		messages=[
			{"role": "system", "content": system_msg},
			{"role": "user", "content": user_msg},
		],
		temperature=0.5,
		max_tokens=2000,
	)
	content = (resp.choices[0].message.content or "").strip()
	json_text = _extract_json_array(content)
	data = json.loads(json_text)
	if not isinstance(data, list):
		raise ValueError("Storyboard response is not a list")
	# Normalize to list of dicts with 'prompt' and optional 'continuity'
	normalized: List[dict] = []
	for item in data:
		if isinstance(item, dict):
			prompt_text = item.get("prompt") or item.get("scene") or item.get("description") or ""
			continuity = item.get("continuity") or item.get("notes") or ""
			normalized.append({"prompt": str(prompt_text).strip(), "continuity": str(continuity).strip(), "raw": item})
		else:
			normalized.append({"prompt": str(item).strip(), "continuity": "", "raw": item})
	return normalized


async def _describe_scenes_with_llm_async(script_chunks: List[str]) -> List[str]:
	"""Turn each script chunk into a detailed, hyperrealistic, text-free image prompt in Polish.

	The guidance emphasizes: no on-frame text, cinematic lighting, realistic people and environments,
	period-appropriate details if historical, and faithful illustration of the chunk.
	Style note: imagery that supports a Jan Chryzostom Pasek-style narration (barokowa, sarmacka aura),
	but we avoid stylizing as a painting; target photorealism.
	"""
	client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
	system_msg = (
		"Jesteś asystentem, który tworzy szczegółowe opisy kadrów do generowania hiperrealistycznych obrazów. "
		"Nie dodawaj żadnego tekstu na obrazie. Zadbaj o fotorealizm, sugestywne, filmowe światło, ostre detale, "
		"charaktery i rekwizyty zgodne z kontekstem. Uwzględnij realia dawnej Rzeczypospolitej, stroje, uzbrojenie, "
		"arkady, dwory szlacheckie czy gościńce — tylko jeśli wynika to z fragmentu."
	)

	semaphore = asyncio.Semaphore(min(8, max(1, len(script_chunks))))

	async def _one(i: int, chunk: str) -> Tuple[int, str]:
		async with semaphore:
			user_msg = (
				"Na podstawie poniższego fragmentu skryptu napisz zwięzły opis fotorealistycznej sceny (1–3 zdania), "
				"który posłuży do generacji obrazu. Nie używaj dosłownych cytatów ani żadnego tekstu. "
				"Uwzględnij konkret: miejsce, porę dnia, rekwizyty, ujęcie i kompozycję, klimat, emocje.\n\n"
				f"Fragment: {chunk}"
			)
			resp = await client.chat.completions.create(
				model="gpt-4o-mini",
				messages=[
					{"role": "system", "content": system_msg},
					{"role": "user", "content": user_msg},
				],
				temperature=0.6,
				max_tokens=220,
			)
			core = (resp.choices[0].message.content or "").strip()
			final_prompt = (
				"Fotorealistyczna fotografia, brak tekstu, brak napisów, brak znaków wodnych. "
				"Bardzo szczegółowe, naturalne światło filmowe, wysoki realizm skóry i materiałów, głębia ostrości. "
				"Kompozycja pionowa 9:16, pełny kadr (full-bleed), bez ramek i bez czarnych pasów (bez letterboxingu). "
				f"Scena: {core}"
			)
			return i, final_prompt

	tasks = [_one(i, chunk) for i, chunk in enumerate(script_chunks)]
	results = await asyncio.gather(*tasks)
	results_sorted = sorted(results, key=lambda t: t[0])
	prompts = [p for _, p in results_sorted]
	return prompts


def generate_images(script_text: str, num_images: int, output_dir: Path, provider: str = "openai") -> List[Path]:
	output_dir.mkdir(parents=True, exist_ok=True)
	# Prefer a single-call cohesive storyboard for continuity
	try:
		storyboard_items = asyncio.run(_generate_storyboard_prompts_llm_async(script_text=script_text, num_images=num_images))
		# Trim/pad to requested length
		if len(storyboard_items) < num_images:
			last = storyboard_items[-1] if storyboard_items else {"prompt": script_text, "continuity": ""}
			while len(storyboard_items) < num_images:
				storyboard_items.append(last)
		elif len(storyboard_items) > num_images:
			storyboard_items = storyboard_items[:num_images]
		# Build final prompts with unified visual constraints and continuity note
		unified_prefix = (
			"Fotorealistyczna fotografia, brak tekstu, brak napisów, brak znaków wodnych. "
			"Bardzo szczegółowe, naturalne światło filmowe, wysoki realizm skóry i materiałów, głębia ostrości. "
			"Kompozycja pionowa 9:16, pełny kadr (full-bleed), bez ramek i bez czarnych pasów (bez letterboxingu). "
		)
		scene_prompts = []
		for it in storyboard_items:
			core = it.get("prompt", "").strip()
			cont = it.get("continuity", "").strip()
			continuity_hint = f" Zachowaj ciągłość: {cont}." if cont else ""
			scene_prompts.append(unified_prefix + f"Scena: {core}." + continuity_hint)
		# Save storyboard JSON for debugging
		try:
			with open(output_dir / "storyboard.json", "w", encoding="utf-8") as f:
				json.dump(storyboard_items, f, ensure_ascii=False, indent=2)
		except Exception:
			pass
	except Exception:
		# Fallback path: split and describe per chunk
		script_chunks = split_script_into_prompts(script_text, num_images)
		try:
			scene_prompts = asyncio.run(_describe_scenes_with_llm_async(script_chunks))
		except Exception:
			# Second fallback: use raw chunks directly
			scene_prompts = script_chunks

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
		return asyncio.run(_generate_images_async_openai(scene_prompts, output_dir, concurrency))

	# Placeholder provider uses a simple synchronous loop
	image_paths: List[Path] = []
	for i, p in enumerate(scene_prompts):
		image_paths.append(_fallback_generate_placeholder(p, output_dir, i))

	return image_paths


async def _generate_images_async_openai(prompts: List[str], output_dir: Path, concurrency: int) -> List[Path]:
	client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
	semaphore = asyncio.Semaphore(concurrency)

	async def run_one(i: int, prompt: str) -> Tuple[int, Path]:
		async with semaphore:
			try:
				path = await _generate_single_image_openai_async(client, prompt, i, output_dir)
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


