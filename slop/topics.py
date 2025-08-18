from __future__ import annotations

from typing import List

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from .config import AppConfig
from .utils import sanitize_title
from .prompts import TOPIC_GENERATION_SYSTEM_MESSAGE, TOPIC_GENERATION_USER_PROMPT


@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3))
def generate_topic() -> str:
    client = OpenAI()
    prompt = TOPIC_GENERATION_USER_PROMPT
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": TOPIC_GENERATION_SYSTEM_MESSAGE},
            {"role": "user", "content": prompt},
        ],
        temperature=0.9,
        max_tokens=48,
    )
    raw = response.choices[0].message.content.strip()
    return sanitize_title(raw)
