"""
Configuration management for AI Video Generator.
Loads and validates all settings from environment variables.
"""

import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field, validator


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # API Keys (Required)
    minimax_api_key: str = Field(default="", alias="MINIMAX_API_KEY")
    minimax_group_id: Optional[str] = Field(default=None, alias="MINIMAX_GROUP_ID")
    runway_api_key: str = Field(default="", alias="RUNWAY_API_KEY")
    elevenlabs_api_key: str = Field(default="", alias="ELEVENLABS_API_KEY")
    elevenlabs_voice_id: Optional[str] = Field(default=None, alias="ELEVENLABS_VOICE_ID")

    # Video Generation
    max_video_duration: int = Field(default=120, alias="MAX_VIDEO_DURATION")
    default_aspect_ratio: str = Field(default="16:9", alias="DEFAULT_ASPECT_RATIO")
    default_quality: str = Field(default="1080p", alias="DEFAULT_QUALITY")
    default_provider: str = Field(default="minimax", alias="DEFAULT_PROVIDER")

    # Audio Configuration
    background_music_enabled: bool = Field(default=True, alias="BACKGROUND_MUSIC_ENABLED")
    voice_over_volume: float = Field(default=0.8, alias="VOICE_OVER_VOLUME")
    background_music_volume: float = Field(default=0.3, alias="BACKGROUND_MUSIC_VOLUME")

    # Directories
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_file: str = Field(default="app.log", alias="LOG_FILE")
    logs_dir: str = Field(default="logs", alias="LOGS_DIR")
    temp_dir: str = Field(default="temp", alias="TEMP_DIR")
    segments_dir: str = Field(default="segments", alias="SEGMENTS_DIR")
    downloads_dir: str = Field(default="downloads", alias="DOWNLOADS_DIR")
    audio_dir: str = Field(default="audio", alias="AUDIO_DIR")
    output_dir: str = Field(default="output", alias="OUTPUT_DIR")

    # Provider Limits
    minimax_max_duration: int = Field(default=60, alias="MINIMAX_MAX_DURATION")
    runway_max_duration: int = Field(default=60, alias="RUNWAY_MAX_DURATION")
    elevenlabs_max_chars: int = Field(default=5000, alias="ELEVENLABS_MAX_CHARS")

    # Polling Configuration
    polling_interval_seconds: int = Field(default=5, alias="POLLING_INTERVAL_SECONDS")
    polling_timeout_seconds: int = Field(default=600, alias="POLLING_TIMEOUT_SECONDS")
    polling_max_retries: int = Field(default=120, alias="POLLING_MAX_RETRIES")

    # Connection Configuration
    request_timeout_seconds: int = Field(default=30, alias="REQUEST_TIMEOUT_SECONDS")
    connection_timeout_seconds: int = Field(default=10, alias="CONNECTION_TIMEOUT_SECONDS")

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "allow"

    @validator("log_level")
    def validate_log_level(cls, v):
        """Validate log level."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in valid_levels:
            raise ValueError(f"Invalid log level: {v}. Must be one of {valid_levels}")
        return v.upper()

    @validator("default_aspect_ratio")
    def validate_aspect_ratio(cls, v):
        """Validate aspect ratio format."""
        if ":" not in v:
            raise ValueError(f"Aspect ratio must be in format 'W:H', got: {v}")
        return v

    @validator("voice_over_volume", "background_music_volume")
    def validate_volume(cls, v):
        """Validate volume is between 0 and 1."""
        if not 0 <= v <= 1:
            raise ValueError(f"Volume must be between 0 and 1, got: {v}")
        return v

    def ensure_directories(self):
        """Create all required directories if they don't exist."""
        for dir_name in [
            self.logs_dir,
            self.temp_dir,
            self.segments_dir,
            self.downloads_dir,
            self.audio_dir,
            self.output_dir,
        ]:
            Path(dir_name).mkdir(parents=True, exist_ok=True)

    def validate_provider_keys(self):
        """Validate that required API keys are set."""
        errors = []
        if not self.minimax_api_key:
            errors.append("MINIMAX_API_KEY not set")
        if not self.runway_api_key:
            errors.append("RUNWAY_API_KEY not set")
        if not self.elevenlabs_api_key:
            errors.append("ELEVENLABS_API_KEY not set")

        if errors:
            raise ValueError(
                f"Missing required API keys: {', '.join(errors)}. "
                "Please set them in .env file or environment variables."
            )


# Load settings
settings = Settings()

# Ensure directories exist
settings.ensure_directories()

# Optional: validate keys on startup (commented to allow testing without all keys)
# settings.validate_provider_keys()
