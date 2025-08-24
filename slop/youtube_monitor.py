from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone, timedelta
import logging
import os
import requests

try:
    from youtube_transcript_api import (
        YouTubeTranscriptApi,
        TranscriptsDisabled,
        NoTranscriptFound,
        VideoUnavailable,
    )
    _YT_EXC_TUPLE = (TranscriptsDisabled, NoTranscriptFound, VideoUnavailable)
except Exception:  # pragma: no cover - make optional for environments without the package
    YouTubeTranscriptApi = None  # type: ignore[assignment]
    _YT_EXC_TUPLE = (Exception,)

from .youtube_uploader import YouTubeUploader

try:
    import yt_dlp  # type: ignore
except Exception:  # pragma: no cover
    yt_dlp = None  # type: ignore


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


def _fetch_captions_with_ytdlp(video_id: str, preferred_languages: list[str]) -> Optional[list[dict]]:
    if yt_dlp is None:
        return None
    # Try to extract subtitles using yt-dlp
    url = f"https://www.youtube.com/watch?v={video_id}"
    cookies_file = os.getenv("YTDLP_COOKIES_FILE", "").strip() or None
    cookies_from_browser = os.getenv("YTDLP_COOKIES_FROM_BROWSER", "").strip() or None
    ydl_opts: dict = {
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitlesformat": "vtt",
        "quiet": True,
        "no_warnings": True,
        "forcejson": True,
        "extract_flat": False,
        "simulate": True,
    }
    if cookies_file:
        ydl_opts["cookies"] = cookies_file
    elif cookies_from_browser:
        ydl_opts["cookiesfrombrowser"] = cookies_from_browser
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:  # type: ignore[attr-defined]
            info = ydl.extract_info(url, download=False)
        # Prefer automatic captions in preferred languages
        auto = (info.get("automatic_captions") or {}) if isinstance(info, dict) else {}
        subs = (info.get("subtitles") or {}) if isinstance(info, dict) else {}
        # Build ordered list of language preferences
        lang_order = preferred_languages + [l.split("-")[0] for l in preferred_languages]
        seen = set()
        lang_order = [l for l in lang_order if not (l in seen or seen.add(l))]
        tracks = None
        for lang in lang_order:
            if lang in auto and auto[lang]:
                tracks = auto[lang]
                break
        if tracks is None:
            for lang in lang_order:
                if lang in subs and subs[lang]:
                    tracks = subs[lang]
                    break
        if not tracks:
            return None
        # Download the first track URL and parse VTT to segments
        import io, re, requests
        vtt_url = tracks[0].get("url")
        if not vtt_url:
            return None
        resp = requests.get(vtt_url, timeout=20)
        resp.raise_for_status()
        content = resp.text
        # Simple VTT cue parsing
        segments: list[dict] = []
        buf = io.StringIO(content)
        for line in buf:
            if "-->" in line:
                # Next line should be text
                text = buf.readline().strip()
                if text and not text.startswith("WEBVTT"):
                    # Normalize whitespace
                    text = re.sub(r"\s+", " ", text)
                    segments.append({"text": text})
        return segments
    except Exception:
        return None


def _fetch_transcript_via_rapidapi(video_id: str, lang: str) -> Optional[str]:
    """Fetch transcript text via RapidAPI youtube-transcriptor.
    Returns a normalized single string or None on failure.
    """
    api_key = os.getenv("RAPIDAPI_KEY") or os.getenv("RAPIDAPI_YOUTUBE_TRANSCRIPT_KEY")
    if not api_key:
        return None
    url = "https://youtube-transcriptor.p.rapidapi.com/transcript"
    headers = {
        "x-rapidapi-key": api_key,
        "x-rapidapi-host": "youtube-transcriptor.p.rapidapi.com",
    }
    try:
        resp = requests.get(url, headers=headers, params={"video_id": video_id, "lang": lang}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict):
            transcript_str = data.get("transcript")
            if isinstance(transcript_str, str) and transcript_str.strip():
                return " ".join(transcript_str.split())
            segments = None
            for key in ("data", "segments", "result"):
                val = data.get(key)
                if isinstance(val, list):
                    segments = val
                    break
            if isinstance(segments, list):
                texts: list[str] = []
                for seg in segments:
                    if isinstance(seg, dict):
                        t = seg.get("text") or seg.get("caption") or seg.get("transcript")
                        if isinstance(t, str) and t.strip():
                            texts.append(" ".join(t.split()))
                    elif isinstance(seg, str) and seg.strip():
                        texts.append(" ".join(seg.split()))
                if texts:
                    return " ".join(texts)
        elif isinstance(data, list):
            texts: list[str] = []
            for seg in data:
                if isinstance(seg, dict):
                    t = seg.get("text") or seg.get("caption") or seg.get("transcript")
                    if isinstance(t, str) and t.strip():
                        texts.append(" ".join(t.split()))
                elif isinstance(seg, str) and seg.strip():
                    texts.append(" ".join(seg.split()))
            if texts:
                return " ".join(texts)
    except Exception:
        return None
    return None


def fetch_transcript_text(video_id: str, preferred_languages: Optional[list[str]] = None, max_chars: int = 8000, use_generated_fallback: bool = True) -> Optional[str]:
    # Allow override via env var; otherwise use a broad default set
    if preferred_languages is None:
        env_langs = os.getenv("YOUTUBE_TRANSCRIPT_LANGS", "").strip()
        if env_langs:
            langs = [lang.strip() for lang in env_langs.split(",") if lang.strip()]
        else:
            langs = [
                "en", "en-US", "en-GB",
                "es", "es-419", "es-MX", "es-ES",
                "pl",
                "pt", "pt-BR", "pt-PT",
                "fr", "de", "it",
                "ru", "uk", "tr",
                "ar", "fa", "ur",
                "hi", "bn", "ta", "te", "ml",
                "id", "ms", "fil", "vi", "th",
                "ja", "ko",
                "zh", "zh-Hans", "zh-Hant",
            ]
    else:
        langs = preferred_languages

    # Try RapidAPI first with the most preferred languages, in order
    for lang in langs:
        via_rapidapi = _fetch_transcript_via_rapidapi(video_id, lang)
        if via_rapidapi:
            text = via_rapidapi
            if len(text) > max_chars:
                text = text[:max_chars].rsplit(" ", 1)[0] + "…"
            return text

    segments = None
    # Prefer explicit listing to choose manual vs generated
    if YouTubeTranscriptApi is not None:
        try:
            transcripts = YouTubeTranscriptApi.list_transcripts(video_id)
            transcript_obj = None
            # Try manually created first
            try:
                transcript_obj = transcripts.find_manually_created_transcript(langs)
            except Exception:
                transcript_obj = None
            # Fallback to generated if allowed
            if transcript_obj is None and use_generated_fallback:
                try:
                    transcript_obj = transcripts.find_generated_transcript(langs)
                except Exception:
                    transcript_obj = None
            if transcript_obj is not None:
                segments = transcript_obj.fetch()
        except _YT_EXC_TUPLE:
            segments = None
        except Exception:
            segments = None

    # As a last resort, try generic get_transcript (may succeed in some cases)
    if segments is None and YouTubeTranscriptApi is not None:
        try:
            segments = YouTubeTranscriptApi.get_transcript(video_id, languages=langs)
        except _YT_EXC_TUPLE:
            segments = None
        except Exception:
            segments = None

    # Try yt-dlp fallback if still no segments
    if segments is None and os.getenv("SLOP_ENABLE_YTDLP_FALLBACK", "1").strip() not in ("0", "false", "False"):
        segments = _fetch_captions_with_ytdlp(video_id, langs) or None
        if segments is None:
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