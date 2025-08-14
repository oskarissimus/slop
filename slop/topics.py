from __future__ import annotations

from typing import List

from tenacity import retry, stop_after_attempt, wait_exponential

from .config import Personality
from .utils import sanitize_title
from .openai_utils import chat_completion_with_fallback


@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3))
def generate_topic(personality: Personality) -> str:
    prompt = (
        "You are an assistant creating short-form video topics. Given a persona,"
        " return a single catchy, specific topic title suitable for a 2-minute video."
        f" Persona: {personality.name}. Description: {personality.description}."
        " Avoid generic titles. Make it concrete. Return only the title."
    )
    content, _used_model = chat_completion_with_fallback(
        messages=[
            {"role": "system", "content": "You create concise, engaging video topics."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.9,
        max_tokens=48,
    )
    raw = content.strip()
    return sanitize_title(raw)



