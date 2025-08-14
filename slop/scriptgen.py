from __future__ import annotations

from tenacity import retry, stop_after_attempt, wait_exponential

from .config import Personality
from .openai_utils import chat_completion_with_fallback


@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3))
def generate_script(topic: str, personality: Personality, target_duration_seconds: int) -> str:
    words_per_second = 2.5  # conservative speaking rate
    target_words = int(target_duration_seconds * words_per_second)
    prompt = (
        f"Write a voiceover script for a short-form vertical video about: '{topic}'. "
        f"Persona: {personality.name} ({personality.speaking_style}). {personality.description}. "
        f"Aim for around {target_words} words. Use simple, vivid language, natural pacing, and end with a brief closing line. "
        "Do not include scene directions or timestamps."
    )
    content, _used_model = chat_completion_with_fallback(
        messages=[
            {"role": "system", "content": "You write concise, engaging 2-minute scripts."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.8,
        max_tokens=1200,
    )
    return content.strip()



