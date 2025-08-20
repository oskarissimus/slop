from __future__ import annotations

from typing import List, Optional, Tuple
import json

from pydantic import BaseModel, ValidationError
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from .config import AppConfig
from .prompts import (
    COMBINED_GENERATION_SYSTEM_MESSAGE,
    get_combined_generation_user_prompt,
)


class Scene(BaseModel):
    script: str
    image_description: str


class Scenario(BaseModel):
    scenes: List[Scene]


@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3))
def generate_topic_and_scenes(
    *,
    input_text: Optional[str],
    target_duration_seconds: int,
    num_scenes: int,
    model: str = "gpt-4o-mini",
) -> Tuple[str, List[Scene]]:
    """Generate both a topic and structured scenes in a single model call.

    Returns (topic, scenes).
    """
    client = OpenAI()
    words_per_second = 2.5
    target_words = int(target_duration_seconds * words_per_second)

    system_msg = COMBINED_GENERATION_SYSTEM_MESSAGE
    user_msg = get_combined_generation_user_prompt(input_text or "", target_words, num_scenes)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.7,
        max_tokens=2200,
        response_format={"type": "json_object"},
    )
    content = resp.choices[0].message.content or "{}"
    data = json.loads(content)
    raw_topic = str(data.get("topic", "")).strip()
    scenario_data = {"scenes": data.get("scenes", [])}
    scenario = Scenario.model_validate(scenario_data)
    scenes = list(scenario.scenes)
    if len(scenes) > num_scenes:
        scenes = scenes[:num_scenes]
    elif len(scenes) < num_scenes and scenes:
        while len(scenes) < num_scenes:
            scenes.append(scenes[-1])
    return raw_topic, scenes


