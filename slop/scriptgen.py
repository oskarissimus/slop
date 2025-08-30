from __future__ import annotations

from typing import List, Optional, Tuple
import json
import os
from pathlib import Path
import logging

from pydantic import BaseModel, ValidationError
from openai import OpenAI, RateLimitError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

from .prompts import (
    COMBINED_GENERATION_SYSTEM_MESSAGE,
    get_combined_generation_user_prompt,
)
from .youtube_analytics import YouTubeAnalytics
from .utils import is_openai_insufficient_quota_error, InsufficientOpenAIFundsError


logger = logging.getLogger(__name__)

class Scene(BaseModel):
    script: str
    image_description: str


class Scenario(BaseModel):
    scenes: List[Scene]


class CombinedOutput(BaseModel):
    """Top-level structured output expected from the LLM."""
    topic: str
    scenes: List[Scene]


@retry(
    wait=wait_exponential(multiplier=1, min=2, max=10),
    stop=stop_after_attempt(3),
    retry=retry_if_exception(lambda e: not isinstance(e, InsufficientOpenAIFundsError)),
)
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
    logger.info(
        "[scriptgen] start | model=%s temperature=%.2f target_seconds=%d scenes=%d",
        model,
        temperature,
        target_duration_seconds,
        num_scenes,
    )
    words_per_second = 2.5
    target_words = int(target_duration_seconds * words_per_second)

    # Detect BAU trigger and, if present, build analytics-driven context
    bau_triggered = bool(input_text) and ("business as usual" in (input_text or "").lower())
    if bau_triggered:
        logger.info("[scriptgen] BAU mode triggered; fetching channel analytics context")
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
        logger.info("[scriptgen] calling chat.completions with JSON schema format")
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            temperature=temperature,
            response_format=json_schema_payload,
        )
    except Exception as e:
        logger.warning("[scriptgen] schema format failed; retrying with json_object response_format")
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_msg},
                ],
                temperature=temperature,
                response_format={"type": "json_object"},
            )
        except Exception as e2:
            if is_openai_insufficient_quota_error(e2) or is_openai_insufficient_quota_error(e):
                logger.error("[scriptgen] OpenAI insufficient_quota detected — prompt user to top up funds")
                raise InsufficientOpenAIFundsError(
                    "OpenAI reports insufficient quota (429). Please check your OpenAI billing/funds: https://platform.openai.com/"
                ) from e2
            # Let other OpenAI exceptions propagate so tenacity can retry and then fail
            raise

    content = resp.choices[0].message.content or "{}"
    try:
        token_usage = getattr(resp, "usage", None)
        if token_usage:
            logger.info(
                "[scriptgen] response received | prompt_tokens=%s completion_tokens=%s total_tokens=%s",
                getattr(token_usage, "prompt_tokens", None),
                getattr(token_usage, "completion_tokens", None),
                getattr(token_usage, "total_tokens", None),
            )
    except Exception:
        pass

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
    logger.info("[scriptgen] parsed scenes | scenes=%d topic_preview=\"%s\"", len(scenes), raw_topic[:120])
    return raw_topic, scenes


