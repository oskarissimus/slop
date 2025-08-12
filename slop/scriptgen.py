from __future__ import annotations

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from .config import Personality


@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3))
def generate_script(topic: str, personality: Personality, target_duration_seconds: int) -> str:
    client = OpenAI()
    words_per_second = 2.5  # conservative speaking rate
    target_words = int(target_duration_seconds * words_per_second)
    prompt = (
        f"Write a voiceover script for a short-form vertical video about: '{topic}'. "
        f"Persona: {personality.name} ({personality.speaking_style}). {personality.description}. "
        f"Aim for around {target_words} words. Use simple, vivid language, natural pacing, and end with a brief closing line. "
        "Do not include scene directions or timestamps."
    )
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You write concise, engaging 2-minute scripts."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.8,
        max_tokens=1200,
    )
    return response.choices[0].message.content.strip()



