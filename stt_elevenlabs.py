import argparse
import os
from typing import Optional, Tuple

from elevenlabs import ElevenLabs


def transcribe(
    *,
    path: Optional[str],
    cloud_url: Optional[str],
    model: str = "scribe_v1",
    lang: Optional[str] = None,
    diarize: bool = True,
    tag_events: bool = True,
    multi_channel: bool = False,
) -> Tuple[str, object]:
    """
    Transcribe audio/video using ElevenLabs Speech-to-Text.

    Returns a tuple of (plain_text, raw_response_model).
    """
    client = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))
    if client is None:
        raise RuntimeError("Missing ELEVENLABS_API_KEY in environment")

    kwargs = dict(
        model_id=model,
        language_code=lang if lang else None,
        diarize=diarize,
        tag_audio_events=tag_events,
        use_multi_channel=multi_channel,
    )

    if cloud_url:
        response = client.speech_to_text.convert(cloud_storage_url=cloud_url, **kwargs)
    elif path:
        with open(path, "rb") as file_handle:
            response = client.speech_to_text.convert(file=file_handle, **kwargs)
    else:
        raise ValueError("Provide either a local --file or a public cloud --url")

    # Response union may be a chunk model or multichannel model.
    if hasattr(response, "transcripts") and isinstance(getattr(response, "transcripts"), list):
        texts = [getattr(t, "text", "") for t in response.transcripts]
        text = "\n".join([t for t in texts if t])
    else:
        text = getattr(response, "text", str(response))

    return text, response


def main() -> None:
    parser = argparse.ArgumentParser(description="Transcribe audio/video using ElevenLabs STT")
    parser.add_argument("--file", help="Path to local audio/video file")
    parser.add_argument("--url", help="Public cloud storage URL to media file (S3/R2/GCS presigned URL)")
    parser.add_argument("--model", default="scribe_v1", help="Model ID to use (default: scribe_v1)")
    parser.add_argument("--lang", help="ISO-639-1/3 language code, e.g. eng; defaults to auto-detect")
    parser.add_argument("--no-diarize", action="store_true", help="Disable speaker diarization")
    parser.add_argument("--no-tag-events", action="store_true", help="Disable tagging audio events like (laughter)")
    parser.add_argument("--multi-channel", action="store_true", help="Enable multi-channel transcription")
    parser.add_argument("--out", help="Optional path to save transcript text")
    args = parser.parse_args()

    text, _ = transcribe(
        path=args.file,
        cloud_url=args.url,
        model=args.model,
        lang=args.lang,
        diarize=not args.no_diarize,
        tag_events=not args.no_tag_events,
        multi_channel=args.multi_channel,
    )

    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
    print(text)


if __name__ == "__main__":
    main()
