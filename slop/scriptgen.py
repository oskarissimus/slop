from __future__ import annotations

from typing import List, Optional, Tuple
import json
import os
from pathlib import Path

from pydantic import BaseModel, ValidationError
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from .prompts import (
    COMBINED_GENERATION_SYSTEM_MESSAGE,
    get_combined_generation_user_prompt,
)
from .youtube_analytics import YouTubeAnalytics


class Scene(BaseModel):
    script: str
    image_description: str


class Scenario(BaseModel):
    scenes: List[Scene]


class CombinedOutput(BaseModel):
    """Top-level structured output expected from the LLM."""
    topic: str
    scenes: List[Scene]


@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3))
def generate_topic_and_scenes(
    *,
    input_text: Optional[str],
    target_duration_seconds: int,
    num_scenes: int,
    model: str = "gpt-4o-mini",
    temperature: float = 0.7,
) -> Tuple[str, List[Scene]]:
    """Generate both a topic and structured scenes in a single model call.

    Returns (topic, scenes).
    """
    client = OpenAI()
    words_per_second = 2.5
    target_words = int(target_duration_seconds * words_per_second)

    # Detect BAU trigger and, if present, build analytics-driven context
    bau_triggered = bool(input_text) and ("business as usual" in (input_text or "").lower())
    if bau_triggered:
        try:
            credentials_dir = Path(os.getenv("YOUTUBE_CREDENTIALS_DIR", str(Path.cwd())))
            yt = YouTubeAnalytics(credentials_dir=credentials_dir)
            videos = yt.fetch_recent_uploads_with_stats(max_videos=30, max_comments_per_video=3)
            summary = yt.build_summary(videos, max_items=10)
            input_for_prompt = (
                "Tryb 'business as usual': zignoruj dosłowne wejście użytkownika. "
                "Na podstawie poniższej analizy wyników mojego kanału YouTube zaproponuj NOWY temat, "
                "który maksymalizuje zaangażowanie (wyświetlenia, polubienia, komentarze). "
                "Wyciągnij wzorce (motywy, stylistyka, słowa kluczowe) i zaproponuj świeży wariant, "
                "bez kopiowania istniejących tytułów.\n\n"
                f"{summary}"
            )
        except Exception:
            # Fallback to original input if analytics are unavailable
            input_for_prompt = input_text or ""
    else:
        input_for_prompt = input_text or ""

    system_msg = COMBINED_GENERATION_SYSTEM_MESSAGE
    user_msg = get_combined_generation_user_prompt(input_for_prompt, target_words, num_scenes)
    # Prefer strict structured outputs with a JSON Schema. Fallback to json_object if unsupported.
    json_schema_payload = {
        "type": "json_schema",
        "json_schema": {
            "name": "scene_generation_output",
            "strict": True,
            "schema": CombinedOutput.model_json_schema(),
        },
    }

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            temperature=temperature,
            response_format=json_schema_payload,
        )
    except Exception:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            temperature=temperature,
            response_format={"type": "json_object"},
        )

    content = resp.choices[0].message.content or "{}"

    # Validate and parse via Pydantic to ensure structure is correct
    try:
        combined = CombinedOutput.model_validate_json(content)
    except ValidationError:
        data = json.loads(content)
        combined = CombinedOutput.model_validate(data)

    raw_topic = str(combined.topic).strip()
    scenes = list(combined.scenes)
    if len(scenes) > num_scenes:
        scenes = scenes[:num_scenes]
    elif len(scenes) < num_scenes and scenes:
        while len(scenes) < num_scenes:
            scenes.append(scenes[-1])
    return raw_topic, scenes


