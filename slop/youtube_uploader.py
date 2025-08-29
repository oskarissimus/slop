from __future__ import annotations

import json
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional
import os

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
    privacy_status: str = "public"  # public | unlisted | private


class YouTubeUploader:
    def __init__(self, credentials_dir: Path) -> None:
        self.credentials_dir = credentials_dir
        self.credentials_dir.mkdir(parents=True, exist_ok=True)
        self.client_secret_path = self.credentials_dir / "client_secret.json"
        # Use a dedicated token file for YouTube
        self.token_path = self.credentials_dir / "youtube_token.json"

    def _materialize_oauth_files_from_env(self) -> None:
        """Best-effort: write client_secret.json and token.json from env vars if provided.

        Supported env vars (checked in order):
        - client secrets content: YOUTUBE_CLIENT_SECRETS, GOOGLE_OAUTH_CLIENT_JSON, YT_CLIENT_SECRET_JSON
        - client secrets path: YOUTUBE_CLIENT_SECRETS_JSON, GOOGLE_OAUTH_CLIENT_JSON_PATH
        - token content: YOUTUBE_TOKEN_JSON, YOUTUBE_OAUTH_TOKEN, GOOGLE_OAUTH_TOKEN_JSON, YT_TOKEN_JSON
        - token path: YOUTUBE_TOKEN_JSON_PATH, GOOGLE_OAUTH_TOKEN_JSON_PATH
        Values that look like JSON (start with '{') are treated as inline content; otherwise treated as paths.
        """
        # Client secrets
        if not self.client_secret_path.exists():
            candidates_content = [
                os.getenv("YOUTUBE_CLIENT_SECRETS"),
                os.getenv("GOOGLE_OAUTH_CLIENT_JSON"),
                os.getenv("YT_CLIENT_SECRET_JSON"),
            ]
            candidates_path = [
                os.getenv("YOUTUBE_CLIENT_SECRETS_JSON"),
                os.getenv("GOOGLE_OAUTH_CLIENT_JSON_PATH"),
            ]
            content_value = next((v for v in candidates_content if v and v.strip()), None)
            path_value = next((v for v in candidates_path if v and v.strip()), None)

            try:
                if content_value and content_value.strip().startswith("{"):
                    self.client_secret_path.write_text(content_value, encoding="utf-8")
                elif path_value:
                    src = Path(path_value)
                    if src.exists():
                        self.client_secret_path.write_text(src.read_text(encoding="utf-8"))
            except Exception:
                # Best-effort only
                pass

        # Token
        if not self.token_path.exists():
            token_content_candidates = [
                os.getenv("YOUTUBE_TOKEN_JSON"),
                os.getenv("YOUTUBE_OAUTH_TOKEN"),
                os.getenv("GOOGLE_OAUTH_TOKEN_JSON"),
                os.getenv("YT_TOKEN_JSON"),
            ]
            token_path_candidates = [
                os.getenv("YOUTUBE_TOKEN_JSON_PATH"),
                os.getenv("GOOGLE_OAUTH_TOKEN_JSON_PATH"),
            ]
            t_content = next((v for v in token_content_candidates if v and v.strip()), None)
            t_path = next((v for v in token_path_candidates if v and v.strip()), None)

            try:
                if t_content and t_content.strip().startswith("{"):
                    self.token_path.write_text(t_content, encoding="utf-8")
                elif t_path:
                    tsrc = Path(t_path)
                    if tsrc.exists():
                        self.token_path.write_text(tsrc.read_text(encoding="utf-8"))
            except Exception:
                pass

    def _get_credentials(self) -> Credentials:
        # Attempt to materialize OAuth files from env before reading
        self._materialize_oauth_files_from_env()

        creds: Optional[Credentials] = None
        if self.token_path.exists():
            creds = Credentials.from_authorized_user_file(str(self.token_path), YOUTUBE_UPLOAD_SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    # Save refreshed token
                    try:
                        self.token_path.write_text(creds.to_json())
                    except Exception:
                        pass
                except Exception:
                    # Refresh failed (e.g., invalid_grant: expired or revoked). Fall back to interactive flow.
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
                    try:
                        self.token_path.write_text(creds.to_json())
                    except Exception:
                        pass
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
                try:
                    self.token_path.write_text(creds.to_json())
                except Exception:
                    pass
        return creds

    def authorize(self) -> Path:
        """Run OAuth flow to generate or refresh token.json and return its path.

        Ensures `client_secret.json` exists (or can be materialized from env),
        launches the local server flow if needed, and writes `token.json`.
        """
        # This will perform refresh or interactive auth as needed and persist token
        _ = self._get_credentials()
        return self.token_path

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
            "status": {
                "privacyStatus": metadata.privacy_status,
                "selfDeclaredMadeForKids": False,
            },
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


