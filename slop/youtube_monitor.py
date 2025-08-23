from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone, timedelta
import logging

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
        self.logger = logging.getLogger(__name__ + ".YouTubePublicMonitor")

    def _service(self):
        uploader = YouTubeUploader(credentials_dir=self.credentials_dir)
        return uploader._build_service()

    def resolve_channel_id(self, handle_or_id: str) -> Optional[str]:
        """Resolve a channel handle (e.g., @SwaruuOficial) to a channel ID (UC...).
        If an ID is passed, return it as-is.
        """
        handle = handle_or_id.strip()
        if handle.startswith("UC") and len(handle) >= 12:
            self.logger.debug("Using provided channel ID: %s", handle)
            return handle
        yt = self._service()
        try:
            # Prefer resolving handles explicitly if provided (best-effort)
            if handle.startswith("@"):
                try:
                    resp = yt.channels().list(part="id", forHandle=handle[1:]).execute()  # type: ignore[arg-type]
                    items = resp.get("items", [])
                    if items:
                        cid = items[0].get("id")
                        if cid:
                            self.logger.debug("Resolved handle %s to channel ID via channels.list: %s", handle, cid)
                            return cid
                except Exception:
                    # Fall back to search if forHandle is not supported or fails
                    pass

            resp = yt.search().list(part="id,snippet", q=handle, type="channel", maxResults=1).execute()
            items = resp.get("items", [])
            if not items:
                self.logger.info("No channel found for query: %s", handle)
                return None
            # Prefer id.channelId; snippet.channelId as fallback
            cid = items[0].get("id", {}).get("channelId") or items[0].get("snippet", {}).get("channelId")
            if cid:
                self.logger.debug("Resolved %s to channel ID via search: %s", handle, cid)
                return cid
            self.logger.info("Search result missing channelId fields for: %s", handle)
            return None
        except Exception:
            self.logger.exception("Failed to resolve channel ID for: %s", handle)
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

    def fetch_recent_videos(self, channel_id: str, max_results: int = 5) -> list[ChannelLatestVideo]:
        yt = self._service()
        videos: list[ChannelLatestVideo] = []
        try:
            # Resolve uploads playlist for the channel; this is more reliable than search
            ch_resp = yt.channels().list(part="contentDetails", id=channel_id).execute()
            uploads_playlist_id = None
            items = ch_resp.get("items", [])
            if items:
                uploads_playlist_id = (items[0].get("contentDetails", {}) or {}).get("relatedPlaylists", {}).get("uploads")
            if uploads_playlist_id:
                next_page_token = None
                while len(videos) < max_results:
                    pl_resp = yt.playlistItems().list(
                        part="snippet,contentDetails",
                        playlistId=uploads_playlist_id,
                        maxResults=min(50, max_results - len(videos)),
                        pageToken=next_page_token,
                    ).execute()
                    for it in pl_resp.get("items", []) or []:
                        vid = (it.get("contentDetails", {}) or {}).get("videoId", "")
                        sn = it.get("snippet", {}) or {}
                        if not vid:
                            continue
                        videos.append(
                            ChannelLatestVideo(
                                video_id=vid,
                                title=sn.get("title", ""),
                                published_at=sn.get("publishedAt", ""),
                            )
                        )
                        if len(videos) >= max_results:
                            break
                    next_page_token = pl_resp.get("nextPageToken")
                    if not next_page_token:
                        break
            # Fallback to search if uploads playlist not found or empty
            if not videos:
                resp = yt.search().list(part="snippet", channelId=channel_id, order="date", type="video", maxResults=max_results).execute()
                for it in resp.get("items", []) or []:
                    vid = (it.get("id", {}) or {}).get("videoId", "")
                    sn = it.get("snippet", {}) or {}
                    if not vid:
                        continue
                    videos.append(
                        ChannelLatestVideo(
                            video_id=vid,
                            title=sn.get("title", ""),
                            published_at=sn.get("publishedAt", ""),
                        )
                    )
        except Exception:
            self.logger.exception("Failed to fetch recent videos for channel: %s", channel_id)
        return videos


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


def parse_published_at_iso8601(ts: str) -> Optional[datetime]:
    if not ts:
        return None
    try:
        # YouTube returns e.g. 2024-08-23T12:34:56Z
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def check_for_new_video_and_get_transcript(
    *,
    channel_handle_or_id: str,
    credentials_dir: Path,
    preferred_languages: Optional[list[str]] = None,
    freshness_hours: int = 2400,
    max_candidates: int = 5,
) -> Optional[tuple[str, str]]:
    """If a recent video (within freshness_hours) has a transcript, return (video_id, transcript).
    Checks up to max_candidates newest videos, instead of only the very latest.
    """
    monitor = YouTubePublicMonitor(credentials_dir=credentials_dir)
    channel_id = monitor.resolve_channel_id(channel_handle_or_id)
    if not channel_id:
        return None

    # Iterate over recent uploads to avoid missing cases where the newest has no transcript
    recent_videos = monitor.fetch_recent_videos(channel_id, max_results=max_candidates)
    if not recent_videos:
        # Fallback to single latest
        latest = monitor.fetch_latest_video(channel_id)
        recent_videos = [latest] if latest else []

    now = datetime.now(timezone.utc)
    for vid in recent_videos:
        if not vid or not vid.video_id:
            continue
        published_dt = parse_published_at_iso8601(vid.published_at)
        if not published_dt:
            continue
        if now - published_dt > timedelta(hours=freshness_hours):
            continue
        transcript = fetch_transcript_text(vid.video_id, preferred_languages=preferred_languages)
        if transcript:
            return vid.video_id, transcript

    return None
