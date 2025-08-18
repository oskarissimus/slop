from __future__ import annotations

from typing import List
import json

from pydantic import BaseModel, ValidationError
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from .config import AppConfig
from .prompts import (
    SCENE_GENERATION_SYSTEM_MESSAGE,
    get_scene_generation_user_prompt,
)


class Scene(BaseModel):
    script: str
    image_description: str


class Scenario(BaseModel):
    scenes: List[Scene]


@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3))
def generate_scenes(
    *,
    prompt_detail: str,
    target_duration_seconds: int,
    num_scenes: int,
    model: str = "gpt-4o-mini",
) -> List[Scene]:
    """Generate a structured scenario as a list of scenes (script + image_description).

    The output is enforced as JSON using OpenAI's JSON mode. The style is Jan Chryzostom Pasek.
    """
    client = OpenAI()
    words_per_second = 2.5
    target_words = int(target_duration_seconds * words_per_second)

    system_msg = SCENE_GENERATION_SYSTEM_MESSAGE
    user_msg = get_scene_generation_user_prompt(prompt_detail, target_words, num_scenes)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.7,
        max_tokens=2000,
        response_format={"type": "json_object"},
    )
    content = resp.choices[0].message.content or "{}"
    data = json.loads(content)
    scenario = Scenario.model_validate(data)
    # Enforce exact number of scenes; truncate or pad with last
    scenes = list(scenario.scenes)
    if len(scenes) > num_scenes:
        scenes = scenes[:num_scenes]
    elif len(scenes) < num_scenes and scenes:
        while len(scenes) < num_scenes:
            scenes.append(scenes[-1])
    return scenes



