from __future__ import annotations

from typing import List, Mapping, Sequence, Tuple

from openai import OpenAI, APIStatusError, RateLimitError, OpenAIError
from rich.console import Console


console = Console()

DEFAULT_CHAT_MODEL_CANDIDATES: Tuple[str, ...] = (
    "gpt-4o-mini",
    "gpt-4o",
    "gpt-3.5-turbo",
)

_RATE_LIMIT_HEADER_KEYS = (
    "x-ratelimit-limit-requests",
    "x-ratelimit-remaining-requests",
    "x-ratelimit-reset-requests",
    "x-ratelimit-limit-tokens",
    "x-ratelimit-remaining-tokens",
    "x-ratelimit-reset-tokens",
    "retry-after",
    "x-request-id",
)


def _log_rate_limit_headers(headers: Mapping[str, str] | None, prefix: str = "") -> None:
    if not headers:
        return
    lower = {str(k).lower(): str(v) for k, v in headers.items()}
    lines: List[str] = []
    for key in _RATE_LIMIT_HEADER_KEYS:
        if key in lower:
            lines.append(f"{key}: {lower[key]}")
    if lines:
        console.print(f"[yellow]{prefix}Rate limit info:\n  " + "\n  ".join(lines))


def chat_completion_with_fallback(
    messages: List[dict],
    temperature: float,
    max_tokens: int,
    model_candidates: Sequence[str] = DEFAULT_CHAT_MODEL_CANDIDATES,
) -> tuple[str, str]:
    """Attempt a chat completion across multiple models.

    Returns: (content, used_model)
    Raises: last encountered exception if all models fail.
    """
    client = OpenAI()
    last_error: Exception | None = None

    for model_name in model_candidates:
        try:
            resp = client.chat.completions.with_raw_response.create(
                model=model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            if resp.status_code == 200:
                parsed = resp.parse()
                content = parsed.choices[0].message.content or ""
                return content.strip(), model_name
            # Non-200 without raising is unusual; log and fall through
            _log_rate_limit_headers(getattr(resp, "headers", None), prefix=f"[{model_name}] ")
            last_error = OpenAIError(f"HTTP {resp.status_code} on model {model_name}")
        except RateLimitError as e:
            console.print(f"[red]Rate limited on model {model_name}: insufficient quota or concurrency[/red]")
            try:
                _log_rate_limit_headers(getattr(e, "response", None).headers, prefix=f"[{model_name}] ")
            except Exception:
                pass
            last_error = e
            continue
        except APIStatusError as e:
            console.print(f"[red]OpenAI API error on model {model_name}: HTTP {getattr(e, 'status_code', 'unknown')}[/red]")
            try:
                _log_rate_limit_headers(getattr(e, "response", None).headers, prefix=f"[{model_name}] ")
            except Exception:
                pass
            last_error = e
            continue
        except Exception as e:
            console.print(f"[red]Error using model {model_name}: {e}[/red]")
            last_error = e
            continue

    if last_error is not None:
        raise last_error
    raise RuntimeError("All model attempts failed without an exception")