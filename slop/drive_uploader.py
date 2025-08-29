from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload


DRIVE_SCOPES = [
    "https://www.googleapis.com/auth/drive.file",  # App-created or opened files
]


@dataclass
class DriveUploadResult:
    file_id: str
    web_view_link: Optional[str]


class DriveUploader:
    def __init__(self, credentials_dir: Path) -> None:
        self.credentials_dir = Path(credentials_dir)
        self.credentials_dir.mkdir(parents=True, exist_ok=True)
        # Use separate token filename for Drive to avoid conflicts
        self.client_secret_path = self.credentials_dir / "client_secret.json"
        self.token_path = self.credentials_dir / "drive_token.json"

    def _materialize_oauth_files_from_env(self) -> None:
        # Accept the same env vars as YouTube for client secrets/token to avoid duplication
        if not self.client_secret_path.exists():
            content_candidates = [
                os.getenv("GOOGLE_OAUTH_CLIENT_JSON"),
                os.getenv("YOUTUBE_CLIENT_SECRETS"),
                os.getenv("YT_CLIENT_SECRET_JSON"),
            ]
            path_candidates = [
                os.getenv("GOOGLE_OAUTH_CLIENT_JSON_PATH"),
                os.getenv("YOUTUBE_CLIENT_SECRETS_JSON"),
            ]
            content_value = next((v for v in content_candidates if v and v.strip()), None)
            path_value = next((v for v in path_candidates if v and v.strip()), None)
            try:
                if content_value and content_value.strip().startswith("{"):
                    self.client_secret_path.write_text(content_value, encoding="utf-8")
                elif path_value:
                    src = Path(path_value)
                    if src.exists():
                        self.client_secret_path.write_text(src.read_text(encoding="utf-8"))
            except Exception:
                pass

        if not self.token_path.exists():
            token_content_candidates = [
                os.getenv("GOOGLE_OAUTH_TOKEN_JSON"),
                os.getenv("YOUTUBE_TOKEN_JSON"),
                os.getenv("YOUTUBE_OAUTH_TOKEN"),
                os.getenv("YT_TOKEN_JSON"),
            ]
            token_path_candidates = [
                os.getenv("GOOGLE_OAUTH_TOKEN_JSON_PATH"),
                os.getenv("YOUTUBE_TOKEN_JSON_PATH"),
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
        self._materialize_oauth_files_from_env()
        creds: Optional[Credentials] = None
        if self.token_path.exists():
            try:
                creds = Credentials.from_authorized_user_file(str(self.token_path), DRIVE_SCOPES)
            except Exception:
                creds = None
        # If existing token lacks required scopes, force re-auth to request them
        if creds and DRIVE_SCOPES:
            existing_scopes = set(creds.scopes or [])
            required_scopes = set(DRIVE_SCOPES)
            if not required_scopes.issubset(existing_scopes):
                creds = None
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    try:
                        self.token_path.write_text(creds.to_json())
                    except Exception:
                        pass
                except Exception:
                    if not self.client_secret_path.exists():
                        raise FileNotFoundError(
                            f"Missing client secrets at {self.client_secret_path}. "
                            f"Download OAuth client credentials (Desktop app) and save as client_secret.json"
                        )
                    flow = InstalledAppFlow.from_client_secrets_file(
                        str(self.client_secret_path), scopes=DRIVE_SCOPES
                    )
                    creds = flow.run_local_server(port=0)
                    try:
                        self.token_path.write_text(creds.to_json())
                    except Exception:
                        pass
            else:
                if not self.client_secret_path.exists():
                    raise FileNotFoundError(
                        f"Missing client secrets at {self.client_secret_path}. "
                        f"Download OAuth client credentials (Desktop app) and save as client_secret.json"
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.client_secret_path), scopes=DRIVE_SCOPES
                )
                creds = flow.run_local_server(port=0)
                try:
                    self.token_path.write_text(creds.to_json())
                except Exception:
                    pass
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


