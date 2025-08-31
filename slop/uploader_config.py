from __future__ import annotations

from typing import Literal, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class YouTubeUploadConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8')

    youtube_privacy_status: Literal["public", "unlisted", "private"] = "private"

    # OAuth credentials (optional, can rely on files on disk instead)
    oauth_client_json: Optional[str] = None
    youtube_token_json: Optional[str] = None


class DriveUploadConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8')

    # Default parent folder; optional to allow skipping when not using Drive
    drive_parent_folder_id: Optional[str] = None

    # OAuth credentials (optional, can rely on files on disk instead)
    oauth_client_json: Optional[str] = None
    drive_token_json: Optional[str] = None

