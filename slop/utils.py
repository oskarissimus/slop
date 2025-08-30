from __future__ import annotations


_QUOTE_CHARS = "\"'“”‘’`"


class InsufficientOpenAIFundsError(RuntimeError):
    """Raised when OpenAI returns 429 with insufficient_quota, indicating no funds."""


def is_openai_insufficient_quota_error(exc: BaseException) -> bool:
    """Best-effort detection of OpenAI 'insufficient_quota' 429 errors.

    Works across SDK versions by inspecting known attributes and message text.
    """
    try:
        from openai import RateLimitError  # type: ignore
    except Exception:
        RateLimitError = tuple()  # type: ignore

    if isinstance(exc, RateLimitError):  # type: ignore[arg-type]
        # 1) Try structured response JSON
        response = getattr(exc, "response", None)
        if response is not None:
            try:
                data = response.json()
                code = (
                    (data or {}).get("error", {}).get("code")
                    if isinstance(data, dict)
                    else None
                )
                if code == "insufficient_quota":
                    return True
            except Exception:
                pass
        # 2) Fallback to message heuristics
        text = str(exc) or ""
        if ("insufficient_quota" in text) or ("exceeded your current quota" in text):
            return True
    return False


def sanitize_title(raw_title: str) -> str:
    """Return a clean title without wrapping quotes or extra spaces.

    Removes common straight and curly quotes from both ends and trims whitespace.
    """
    if raw_title is None:
        return ""
    title = raw_title.strip()
    # Strip any wrapping quote characters and surrounding whitespace
    title = title.strip(_QUOTE_CHARS + " ")
    return title


