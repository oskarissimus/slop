from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone, timedelta
import logging
import os
import re
import requests


@dataclass
class ChannelLatestVideo:
    video_id: str
    title: str
    published_at: str


class YouTubePublicMonitor:
    def __init__(self, credentials_dir: Path) -> None:
        self.credentials_dir = Path(credentials_dir)
        self.logger = logging.getLogger(__name__ + ".YouTubePublicMonitor")

    def _rapidapi_headers(self) -> dict:
        api_key = os.getenv("RAPIDAPI_KEY") or ""
        if not api_key:
            self.logger.warning("RAPIDAPI_KEY is not set; RapidAPI calls will fail")
        return {
            "x-rapidapi-key": api_key,
            "x-rapidapi-host": "yt-api.p.rapidapi.com",
        }

    def _rapidapi_get(self, path: str, params: dict) -> Optional[dict]:
        try:
            resp = requests.get(
                f"https://yt-api.p.rapidapi.com/{path.lstrip('/')}",
                headers=self._rapidapi_headers(),
                params=params,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict):
                return data
            if isinstance(data, list):
                return {"data": data}
            return None
        except Exception:
            self.logger.exception("RapidAPI request failed for %s", path)
            return None

    def resolve_channel_id(self, handle_or_id: str) -> Optional[str]:
        """Resolve a channel handle (e.g., @SwaruuOficial) to a channel ID (UC...).
        If an ID is passed, return it as-is. Uses RapidAPI yt-api.
        """
        handle = handle_or_id.strip()
        if handle.startswith("UC") and len(handle) >= 12:
            self.logger.debug("Using provided channel ID: %s", handle)
            return handle
        if not handle.startswith("@"):
            handle = f"@{handle}"
        resp = self._rapidapi_get("channel/videos", {"forUsername": handle})
        if not resp:
            return None
        meta = resp.get("meta") or {}
        cid = meta.get("channelId") or meta.get("id")
        if isinstance(cid, str) and cid.startswith("UC"):
            return cid
        items = resp.get("data") or []
        if isinstance(items, list) and items:
            first = items[0] or {}
            cid2 = first.get("channelId") or first.get("authorId")
            if isinstance(cid2, str) and cid2.startswith("UC"):
                return cid2
        return None

    def fetch_latest_video(self, channel_id: str) -> Optional[ChannelLatestVideo]:
        try:
            resp = self._rapidapi_get("channel/videos", {"id": channel_id, "sort_by": "newest"})
            if not resp:
                return None
            items = resp.get("data") or []
            if not isinstance(items, list) or not items:
                return None
            it = items[0]
            vid = (it.get("videoId") or it.get("id") or "")
            title = it.get("title", "")
            published_at = _extract_iso_published_at(it) or ""
            return ChannelLatestVideo(video_id=str(vid), title=str(title), published_at=published_at)
        except Exception:
            return None

    def fetch_recent_videos(self, channel_id: str, max_results: int = 5) -> list[ChannelLatestVideo]:
        videos: list[ChannelLatestVideo] = []
        try:
            resp = self._rapidapi_get("channel/videos", {"id": channel_id, "sort_by": "newest"})
            if not resp:
                return videos
            items = resp.get("data") or []
            if not isinstance(items, list):
                return videos
            for it in items[:max_results]:
                vid = (it.get("videoId") or it.get("id") or "")
                if not vid:
                    continue
                title = it.get("title", "")
                published_at = _extract_iso_published_at(it) or ""
                videos.append(
                    ChannelLatestVideo(video_id=str(vid), title=str(title), published_at=published_at)
                )
        except Exception:
            self.logger.exception("Failed to fetch recent videos for channel: %s", channel_id)
        return videos


def _extract_iso_published_at(item: dict) -> Optional[str]:
    """Attempt to derive ISO8601 UTC timestamp from various yt-api fields."""
    for key in ("publishedAt", "publishDate", "publishedDate", "uploadedAt"):
        val = item.get(key)
        if isinstance(val, str) and val:
            try:
                dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
                return dt.astimezone(timezone.utc).isoformat()
            except Exception:
                pass
    rel = item.get("publishedTimeText") or item.get("publishedText") or item.get("published")
    if isinstance(rel, str) and rel:
        s = rel.strip().lower()
        m = re.match(r"(\d+)\s+(second|minute|hour|day|week|month|year)s?\s+ago", s)
        if m:
            qty = int(m.group(1))
            unit = m.group(2)
            delta = {
                "second": timedelta(seconds=qty),
                "minute": timedelta(minutes=qty),
                "hour": timedelta(hours=qty),
                "day": timedelta(days=qty),
                "week": timedelta(weeks=qty),
                "month": timedelta(days=30 * qty),
                "year": timedelta(days=365 * qty),
            }[unit]
            dt = datetime.now(timezone.utc) - delta
            return dt.isoformat()
    return None


def _fetch_transcript_via_rapidapi(video_id: str, preferred_languages: Optional[list[str]] = None) -> Optional[str]:
    """Fetch transcript text via RapidAPI yt-api subtitles endpoint by selecting a preferred track and downloading it."""
    api_key = os.getenv("RAPIDAPI_KEY")
    if not api_key:
        return None
    headers = {
        "x-rapidapi-key": api_key,
        "x-rapidapi-host": "yt-api.p.rapidapi.com",
    }
    # 1) Query available subtitle tracks
    try:
        meta_resp = requests.get(
            "https://yt-api.p.rapidapi.com/subtitles",
            headers=headers,
            params={"id": video_id},
            timeout=30,
        )
        meta_resp.raise_for_status()
        meta = meta_resp.json()
    except Exception:
        return None

    tracks = []
    if isinstance(meta, dict):
        tracks = meta.get("subtitles") or []
    if not isinstance(tracks, list) or not tracks:
        return None

    # 2) Choose best track according to preferred_languages
    prefs = preferred_languages or []
    # Build preference list including base codes (e.g., en-US -> en)
    expanded_prefs: list[str] = []
    for code in prefs:
        expanded_prefs.append(code)
        if "-" in code:
            expanded_prefs.append(code.split("-", 1)[0])
    # Always consider English and the video's own primary language entries as fallbacks
    if "en" not in expanded_prefs:
        expanded_prefs.append("en")

    def track_score(t: dict) -> int:
        code = (t.get("languageCode") or "").lower()
        # Highest priority for exact matches by order, then base code
        for idx, pref in enumerate(expanded_prefs):
            if code == pref.lower():
                return 1000 - idx
        base = code.split("-", 1)[0]
        for idx, pref in enumerate(expanded_prefs):
            if base == pref.lower():
                return 500 - idx
        # Prefer non-empty url
        return 0 if t.get("url") else -100

    tracks_sorted = sorted(tracks, key=track_score, reverse=True)
    chosen = next((t for t in tracks_sorted if t.get("url")), None)
    if not chosen:
        return None

    subtitle_url = chosen.get("url")
    if not isinstance(subtitle_url, str) or not subtitle_url:
        return None

    # 3) Download and parse subtitle content (JSON or XML)
    try:
        sub_resp = requests.get(subtitle_url, timeout=30)
        sub_resp.raise_for_status()
        text: Optional[str] = None
        # Try JSON first
        try:
            jd = sub_resp.json()
            # JSON formats generally have events -> segs -> utf8
            events = []
            if isinstance(jd, dict):
                events = jd.get("events") or jd.get("body") or []
            if isinstance(events, list) and events:
                pieces: list[str] = []
                for ev in events:
                    if not isinstance(ev, dict):
                        continue
                    segs = ev.get("segs") or []
                    if isinstance(segs, list):
                        for sg in segs:
                            if isinstance(sg, dict):
                                s = sg.get("utf8")
                                if isinstance(s, str) and s.strip():
                                    pieces.append(s.strip())
                if pieces:
                    text = " ".join(" ".join(pieces).split())
        except Exception:
            text = None

        if text is None:
            # Fallback: XML timedtext
            import xml.etree.ElementTree as ET
            import html as _html
            try:
                root = ET.fromstring(sub_resp.text)
                pieces: list[str] = []
                for node in root.findall('.//text'):
                    t = node.text or ""
                    if t:
                        pieces.append(_html.unescape(t).strip())
                if pieces:
                    text = " ".join(" ".join(pieces).split())
            except Exception:
                text = None
        return text
    except Exception:
        return None


def fetch_transcript_text(video_id: str, preferred_languages: Optional[list[str]] = None, max_chars: int = 8000, use_generated_fallback: bool = True) -> Optional[str]:
    langs = preferred_languages
    if langs is None:
        env_langs = os.getenv("YOUTUBE_TRANSCRIPT_LANGS", "").strip()
        if env_langs:
            langs = [lang.strip() for lang in env_langs.split(",") if lang.strip()]
        else:
            langs = ["en"]

    for lang in langs:
        text = _fetch_transcript_via_rapidapi(video_id, [lang])
        if text:
            text = " ".join(text.split())
            if len(text) > max_chars:
                text = text[:max_chars].rsplit(" ", 1)[0] + "…"
            return text
    return None


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
    freshness_hours: int = 24,
    max_candidates: int = 5,
    use_generated_fallback: bool = True,
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
        transcript = fetch_transcript_text(vid.video_id, preferred_languages=preferred_languages, use_generated_fallback=use_generated_fallback)
        if transcript:
            return vid.video_id, transcript

    return None