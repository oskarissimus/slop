from __future__ import annotations


_QUOTE_CHARS = "\"'“”‘’`"


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


