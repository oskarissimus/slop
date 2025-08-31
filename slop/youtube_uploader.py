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

from pydantic_settings import BaseSettings

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
    def __init__(self, credentials_dir: Path, config: BaseSettings | None = None) -> None:
        self.credentials_dir = credentials_dir
        self.credentials_dir.mkdir(parents=True, exist_ok=True)
        self.client_secret_path = self.credentials_dir / "client_secret.json"
        # Use a dedicated token file for YouTube
        self.token_path = self.credentials_dir / "youtube_token.json"
        self._config = config

    def _materialize_oauth_files_from_config_or_env(self) -> None:
        """Write client_secret.json and youtube_token.json from AppConfig if provided.

        Values must be raw JSON (start with '{'). If not provided, and files
        already exist, do nothing.
        """
        # Client secret
        if not self.client_secret_path.exists():
            content_value = None
            if self._config and getattr(self._config, "oauth_client_json", None):
                content_value = self._config.oauth_client_json
            try:
                if content_value and content_value.strip().startswith("{"):
                    self.client_secret_path.write_text(content_value, encoding="utf-8")
            except Exception:
                pass

        # Token
        if not self.token_path.exists():
            token_value = None
            if self._config and getattr(self._config, "youtube_token_json", None):
                token_value = self._config.youtube_token_json
            try:
                if token_value and token_value.strip().startswith("{"):
                    self.token_path.write_text(token_value, encoding="utf-8")
            except Exception:
                pass

    def _get_credentials(self) -> Credentials:
        # Attempt to materialize OAuth files from AppConfig/env before reading
        self._materialize_oauth_files_from_config_or_env()

        creds: Optional[Credentials] = None
        # Fail fast if required files are missing
        if not self.client_secret_path.exists():
            raise FileNotFoundError(
                f"Missing client secrets at {self.client_secret_path}. "
                "Provide oauth_client_json in settings or place client_secret.json in the credentials directory."
            )
        if not self.token_path.exists():
            raise FileNotFoundError(
                f"Missing YouTube token at {self.token_path}. "
                "Provide youtube_token_json in settings or place youtube_token.json in the credentials directory."
            )

        # Load token and validate
        try:
            creds = Credentials.from_authorized_user_file(str(self.token_path), YOUTUBE_UPLOAD_SCOPES)
        except Exception as e:
            raise RuntimeError(
                f"Invalid YouTube OAuth token JSON at {self.token_path}: {e}. "
                "Ensure a valid token with scopes: " + ", ".join(YOUTUBE_UPLOAD_SCOPES)
            )

        # Refresh if expired and refresh_token present; otherwise fail
        if not creds.valid:
            if creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    try:
                        self.token_path.write_text(creds.to_json())
                    except Exception:
                        pass
                except Exception as e:
                    raise RuntimeError(
                        "Failed to refresh YouTube OAuth token. Re-authorize locally and update the stored token. "
                        "Run: `uv run slop-youtube auth --credentials-dir ./.youtube` and then update the token file."
                    ) from e
            else:
                raise RuntimeError(
                    "Invalid YouTube OAuth token (no refresh token or token invalid). "
                    "Re-authorize and provide a valid token with required scopes."
                )

        # Ensure required scopes are present
        existing_scopes = set(creds.scopes or [])
        required_scopes = set(YOUTUBE_UPLOAD_SCOPES)
        if not required_scopes.issubset(existing_scopes):
            raise RuntimeError(
                "YouTube OAuth token is missing required scopes. "
                f"Required: {', '.join(required_scopes)} | Present: {', '.join(sorted(existing_scopes))}. "
                "Generate a new token with the required scopes."
            )
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


