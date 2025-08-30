from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from .config import AppConfig

DRIVE_SCOPES = [
    "https://www.googleapis.com/auth/drive.file",  # App-created or opened files
]


@dataclass
class DriveUploadResult:
    file_id: str
    web_view_link: Optional[str]


class DriveUploader:
    def __init__(self, credentials_dir: Path, config: AppConfig | None = None) -> None:
        self.credentials_dir = Path(credentials_dir)
        self.credentials_dir.mkdir(parents=True, exist_ok=True)
        # Use separate token filename for Drive to avoid conflicts
        self.client_secret_path = self.credentials_dir / "client_secret.json"
        self.token_path = self.credentials_dir / "drive_token.json"
        self._config = config

    def _materialize_oauth_files_from_config_or_env(self) -> None:
        # Use only AppConfig-provided JSON if available; otherwise rely on existing files
        if not self.client_secret_path.exists():
            content_value = None
            if self._config and getattr(self._config, "oauth_client_json", None):
                content_value = self._config.oauth_client_json
            try:
                if content_value and content_value.strip().startswith("{"):
                    self.client_secret_path.write_text(content_value, encoding="utf-8")
            except Exception:
                pass

        if not self.token_path.exists():
            token_value = None
            if self._config and getattr(self._config, "drive_token_json", None):
                token_value = self._config.drive_token_json
            try:
                if token_value and token_value.strip().startswith("{"):
                    self.token_path.write_text(token_value, encoding="utf-8")
            except Exception:
                pass

    def _get_credentials(self) -> Credentials:
        self._materialize_oauth_files_from_config_or_env()
        # Fail fast if required files are missing
        if not self.client_secret_path.exists():
            raise FileNotFoundError(
                f"Missing client secrets at {self.client_secret_path}. "
                "Provide oauth_client_json in settings or place client_secret.json in the credentials directory."
            )
        if not self.token_path.exists():
            raise FileNotFoundError(
                f"Missing Drive token at {self.token_path}. "
                "Provide drive_token_json in settings or place drive_token.json in the credentials directory."
            )

        # Load token and validate
        try:
            creds: Optional[Credentials] = Credentials.from_authorized_user_file(str(self.token_path), DRIVE_SCOPES)
        except Exception as e:
            raise RuntimeError(
                f"Invalid Drive OAuth token JSON at {self.token_path}: {e}. "
                "Ensure a valid token with scopes: " + ", ".join(DRIVE_SCOPES)
            )

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
                        "Failed to refresh Google Drive OAuth token. Re-authorize locally and update the stored token."
                    ) from e
            else:
                raise RuntimeError(
                    "Invalid Google Drive OAuth token (no refresh token or token invalid). "
                    "Re-authorize and provide a valid token with required scopes."
                )

        # Ensure required scopes are present
        existing_scopes = set(creds.scopes or [])
        required_scopes = set(DRIVE_SCOPES)
        if not required_scopes.issubset(existing_scopes):
            raise RuntimeError(
                "Drive OAuth token is missing required scopes. "
                f"Required: {', '.join(required_scopes)} | Present: {', '.join(sorted(existing_scopes))}. "
                "Generate a new token with the required scopes."
            )
        return creds

    def authorize(self) -> Path:
        _ = self._get_credentials()
        return self.token_path

    def _build_service(self):
        creds = self._get_credentials()
        return build("drive", "v3", credentials=creds)

    def create_folder(self, name: str, *, parent_folder_id: Optional[str] = None, make_shareable: bool = True) -> str:
        drive = self._build_service()
        body = {
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
        }
        if parent_folder_id:
            body["parents"] = [parent_folder_id]
        folder = drive.files().create(body=body, fields="id").execute()
        folder_id = folder.get("id")
        if make_shareable and folder_id:
            try:
                drive.permissions().create(
                    fileId=folder_id,
                    body={"role": "reader", "type": "anyone"},
                ).execute()
            except Exception:
                pass
        return str(folder_id)

    def upload_file(self, file_path: Path, *, parent_folder_id: Optional[str] = None, make_shareable: bool = True) -> DriveUploadResult:
        drive = self._build_service()
        mime_type, _ = mimetypes.guess_type(file_path)
        media = MediaFileUpload(str(file_path), mimetype=mime_type or "application/octet-stream", resumable=True)

        body = {
            "name": file_path.name,
        }
        if parent_folder_id:
            body["parents"] = [parent_folder_id]

        try:
            created = drive.files().create(body=body, media_body=media, fields="id, webViewLink").execute()
        except HttpError:
            raise

        file_id = created.get("id")
        web_link = created.get("webViewLink")

        if make_shareable and file_id:
            try:
                # Set anyone-with-link reader permission
                drive.permissions().create(
                    fileId=file_id,
                    body={"role": "reader", "type": "anyone"},
                ).execute()
                # Refetch link with shortcut to ensure it's available
                meta = drive.files().get(fileId=file_id, fields="webViewLink").execute()
                web_link = meta.get("webViewLink") or web_link
            except Exception:
                pass

        return DriveUploadResult(file_id=str(file_id), web_view_link=str(web_link) if web_link else None)

    def upload_directory(self, dir_path: Path, *, parent_folder_id: Optional[str] = None, make_shareable: bool = True) -> str:
        """Create a folder on Drive and upload all files from dir_path into it (non-recursive)."""
        if not dir_path.exists() or not dir_path.is_dir():
            raise FileNotFoundError(f"Directory not found: {dir_path}")
        folder_id = self.create_folder(dir_path.name, parent_folder_id=parent_folder_id, make_shareable=make_shareable)
        for item in sorted(dir_path.iterdir()):
            if item.is_file():
                try:
                    self.upload_file(item, parent_folder_id=folder_id, make_shareable=make_shareable)
                except Exception:
                    # Continue best-effort even if one file fails
                    pass
        return folder_id


