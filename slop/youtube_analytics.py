from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from googleapiclient.discovery import Resource

from .youtube_uploader import YouTubeUploader


@dataclass
class VideoAnalytics:
    video_id: str
    title: str
    published_at: str
    view_count: int
    like_count: int
    comment_count: int
    top_comments: List[str]


class YouTubeAnalytics:
    def __init__(self, credentials_dir: Path) -> None:
        self.credentials_dir = Path(credentials_dir)

    def _build_service(self) -> Resource:  # type: ignore[valid-type]
        uploader = YouTubeUploader(credentials_dir=self.credentials_dir)
        return uploader._build_service()  # reuse authenticated client

    def fetch_recent_uploads_with_stats(
        self,
        *,
        max_videos: int = 20,
        max_comments_per_video: int = 3,
    ) -> List[VideoAnalytics]:
        youtube = self._build_service()

        channels_resp = youtube.channels().list(part="contentDetails", mine=True).execute()
        items = channels_resp.get("items", [])
        if not items:
            return []
        uploads_playlist_id = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]

        # Collect recent uploads from playlist
        video_ids: List[str] = []
        video_snippets: Dict[str, Dict] = {}
        next_page_token: Optional[str] = None
        while len(video_ids) < max_videos:
            req = youtube.playlistItems().list(
                part="snippet,contentDetails",
                playlistId=uploads_playlist_id,
                maxResults=min(50, max_videos - len(video_ids)),
                pageToken=next_page_token,
            )
            resp = req.execute()
            for it in resp.get("items", []):
                vid = it.get("contentDetails", {}).get("videoId")
                sn = it.get("snippet", {})
                if vid and vid not in video_ids:
                    video_ids.append(vid)
                    video_snippets[vid] = sn
            next_page_token = resp.get("nextPageToken")
            if not next_page_token:
                break

        if not video_ids:
            return []

        # Fetch statistics in batches of up to 50
        analytics: List[VideoAnalytics] = []
        for i in range(0, len(video_ids), 50):
            batch_ids = video_ids[i:i + 50]
            vresp = youtube.videos().list(part="snippet,statistics", id=",".join(batch_ids)).execute()
            for v in vresp.get("items", []):
                vid = v.get("id")
                sn = v.get("snippet", {})
                st = v.get("statistics", {})
                title = sn.get("title", "")
                published_at = sn.get("publishedAt", "")
                views = int(st.get("viewCount", 0))
                likes = int(st.get("likeCount", 0))
                comments_cnt = int(st.get("commentCount", 0))

                top_comments: List[str] = []
                if comments_cnt > 0 and max_comments_per_video > 0:
                    try:
                        c_resp = youtube.commentThreads().list(
                            part="snippet",
                            videoId=vid,
                            maxResults=max_comments_per_video,
                            order="relevance",
                            textFormat="plainText",
                        ).execute()
                        for ct in c_resp.get("items", []):
                            comment_sn = ct.get("snippet", {}).get("topLevelComment", {}).get("snippet", {})
                            text = comment_sn.get("textOriginal") or comment_sn.get("textDisplay")
                            if text:
                                # Truncate to keep prompts compact
                                text = text.replace("\n", " ").strip()
                                if len(text) > 200:
                                    text = text[:200] + "…"
                                top_comments.append(text)
                    except Exception:
                        # Comments disabled or insufficient permissions; ignore
                        pass

                analytics.append(
                    VideoAnalytics(
                        video_id=vid or "",
                        title=title,
                        published_at=published_at,
                        view_count=views,
                        like_count=likes,
                        comment_count=comments_cnt,
                        top_comments=top_comments,
                    )
                )

        # Sort by view count desc as a proxy for engagement
        analytics.sort(key=lambda a: a.view_count, reverse=True)
        return analytics

    @staticmethod
    def build_summary(videos: List[VideoAnalytics], *, max_items: int = 10) -> str:
        if not videos:
            return "Brak danych analitycznych kanału."
        lines: List[str] = []
        lines.append("Analiza ostatnich filmów (posortowane wg wyświetleń):")
        for v in videos[:max_items]:
            date = (v.published_at or "")[:10]
            base = f"- {v.title} ({date}): {v.view_count} wyśw., {v.like_count} polub., {v.comment_count} kom."
            if v.top_comments:
                comments_sample = "; ".join(v.top_comments[:2])
                lines.append(base + f"; komentarze: {comments_sample}")
            else:
                lines.append(base)
        return "\n".join(lines)