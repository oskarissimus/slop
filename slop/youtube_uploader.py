from __future__ import annotations

import json
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload


YOUTUBE_UPLOAD_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]


@dataclass
class UploadMetadata:
    title: str
    description: str = ""
    tags: Optional[Iterable[str]] = None
    category_id: str = "22"
    privacy_status: str = "private"  # public | unlisted | private


class YouTubeUploader:
    def __init__(self, credentials_dir: Path) -> None:
        self.credentials_dir = credentials_dir
        self.credentials_dir.mkdir(parents=True, exist_ok=True)
        self.client_secret_path = self.credentials_dir / "client_secret.json"
        self.token_path = self.credentials_dir / "token.json"

    def _get_credentials(self) -> Credentials:
        creds: Optional[Credentials] = None
        if self.token_path.exists():
            creds = Credentials.from_authorized_user_file(str(self.token_path), YOUTUBE_UPLOAD_SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not self.client_secret_path.exists():
                    raise FileNotFoundError(
                        f"Missing client secrets at {self.client_secret_path}. "
                        f"Download OAuth client credentials (Desktop app) from Google Cloud Console and save as client_secret.json"
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.client_secret_path), scopes=YOUTUBE_UPLOAD_SCOPES
                )
                creds = flow.run_local_server(port=0)
            # Save the credentials for the next run
            self.token_path.write_text(creds.to_json())
        return creds

    def _build_service(self):
        creds = self._get_credentials()
        return build("youtube", "v3", credentials=creds)

    def upload_video(self, video_path: Path, metadata: UploadMetadata) -> str:
        youtube = self._build_service()

        mime_type, _ = mimetypes.guess_type(video_path)
        if not mime_type:
            mime_type = "video/mp4"

        media = MediaFileUpload(
            filename=str(video_path),
            mimetype=mime_type,
            chunksize=1024 * 1024 * 8,  # 8MB chunks
            resumable=True,
        )

        body = {
            "snippet": {
                "title": metadata.title,
                "description": metadata.description,
                "tags": list(metadata.tags) if metadata.tags else None,
                "categoryId": metadata.category_id,
            },
            "status": {"privacyStatus": metadata.privacy_status},
        }

        request = youtube.videos().insert(
            part=",".join(body.keys()), body=body, media_body=media
        )

        response = None
        try:
            while response is None:
                status, response = request.next_chunk()
                # status may be None at the final chunk
        except HttpError as http_error:  # type: ignore[reportUnknownVariableType]
            # Improve common error messaging, especially youtubeSignupRequired
            try:
                content_text = http_error.content.decode("utf-8") if hasattr(http_error, "content") else ""
            except Exception:
                content_text = ""
            reason = None
            message = None
            try:
                import json as _json

                payload = _json.loads(content_text) if content_text else {}
                errors = payload.get("error", {}).get("errors", [])
                if errors:
                    reason = errors[0].get("reason")
                    message = errors[0].get("message") or payload.get("error", {}).get("message")
            except Exception:
                pass

            if reason == "youtubeSignupRequired":
                raise RuntimeError(
                    "Unauthorized: The authorized Google account must have an active YouTube channel. "
                    "Open youtube.com with that account, create a channel or accept terms, then retry."
                ) from http_error
            raise
        if "id" not in response:
            raise RuntimeError(f"Unexpected response from YouTube API: {json.dumps(response, indent=2)}")
        return response["id"]

    def set_thumbnail(self, video_id: str, thumbnail_path: Path) -> None:
        youtube = self._build_service()
        mime_type, _ = mimetypes.guess_type(thumbnail_path)
        media = MediaFileUpload(str(thumbnail_path), mimetype=mime_type or "image/jpeg")
        youtube.thumbnails().set(videoId=video_id, media_body=media).execute()


