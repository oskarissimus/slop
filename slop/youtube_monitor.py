from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import os

from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound, VideoUnavailable

from .youtube_uploader import YouTubeUploader


@dataclass
class ChannelLatestVideo:
    video_id: str
    title: str
    published_at: str


class YouTubePublicMonitor:
    def __init__(self, credentials_dir: Path) -> None:
        self.credentials_dir = Path(credentials_dir)

    def _service(self):
        uploader = YouTubeUploader(credentials_dir=self.credentials_dir)
        return uploader._build_service()

    def resolve_channel_id(self, handle_or_id: str) -> Optional[str]:
        """Resolve a channel handle (e.g., @SwaruuOficial) to a channel ID (UC...).
        If an ID is passed, return it as-is.
        """
        handle = handle_or_id.strip()
        if handle.startswith("UC") and len(handle) >= 12:
            return handle
        # Fallback: search the channel by query
        yt = self._service()
        try:
            resp = yt.search().list(part="snippet", q=handle, type="channel", maxResults=1).execute()
            items = resp.get("items", [])
            if not items:
                return None
            return items[0]["snippet"]["channelId"]
        except Exception:
            return None

    def fetch_latest_video(self, channel_id: str) -> Optional[ChannelLatestVideo]:
        yt = self._service()
        try:
            resp = yt.search().list(part="snippet", channelId=channel_id, order="date", type="video", maxResults=1).execute()
            items = resp.get("items", [])
            if not items:
                return None
            it = items[0]
            vid = it.get("id", {}).get("videoId", "")
            sn = it.get("snippet", {})
            title = sn.get("title", "")
            published_at = sn.get("publishedAt", "")
            return ChannelLatestVideo(video_id=vid, title=title, published_at=published_at)
        except Exception:
            return None


def _state_file_for(channel_key: str, state_dir: Path) -> Path:
    safe_key = "".join(c for c in channel_key if c.isalnum() or c in ("-", "_")).strip("-")
    return state_dir / f"last_{safe_key}_video_id.txt"


def load_last_processed_video_id(channel_key: str, state_dir: Path) -> Optional[str]:
    state_dir.mkdir(parents=True, exist_ok=True)
    f = _state_file_for(channel_key, state_dir)
    if not f.exists():
        return None
    try:
        return f.read_text(encoding="utf-8").strip() or None
    except Exception:
        return None


def save_last_processed_video_id(channel_key: str, video_id: str, state_dir: Path) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    f = _state_file_for(channel_key, state_dir)
    try:
        f.write_text(video_id, encoding="utf-8")
    except Exception:
        pass


def fetch_transcript_text(video_id: str, preferred_languages: Optional[list[str]] = None, max_chars: int = 8000) -> Optional[str]:
    langs = preferred_languages or ["es", "en", "pl"]
    try:
        segments = YouTubeTranscriptApi.get_transcript(video_id, languages=langs)
    except (TranscriptsDisabled, NoTranscriptFound, VideoUnavailable):
        return None
    except Exception:
        return None
    text = " ".join((seg.get("text", "") or "").replace("\n", " ").strip() for seg in segments)
    text = " ".join(text.split())
    if not text:
        return None
    if len(text) > max_chars:
        text = text[:max_chars].rsplit(" ", 1)[0] + "…"
        
    return text


def check_for_new_video_and_get_transcript(
    *,
    channel_handle_or_id: str,
    credentials_dir: Path,
    state_dir: Path,
    preferred_languages: Optional[list[str]] = None,
) -> Optional[tuple[str, str]]:
    """If there's a new video on the channel, return (video_id, transcript). Otherwise None."""
    monitor = YouTubePublicMonitor(credentials_dir=credentials_dir)
    channel_id = monitor.resolve_channel_id(channel_handle_or_id)
    if not channel_id:
        return None
    latest = monitor.fetch_latest_video(channel_id)
    if not latest or not latest.video_id:
        return None

    last_id = load_last_processed_video_id(channel_key=channel_handle_or_id, state_dir=state_dir)
    if last_id and last_id == latest.video_id:
        return None

    transcript = fetch_transcript_text(latest.video_id, preferred_languages=preferred_languages)
    if not transcript:
        return None

    save_last_processed_video_id(channel_key=channel_handle_or_id, video_id=latest.video_id, state_dir=state_dir)
    return latest.video_id, transcript