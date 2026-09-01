"""Utilities package for AI Video Generator."""

from .logger import logger, setup_logger
from .errors import (
    VideoGeneratorError,
    ConfigurationError,
    APIError,
    MissingAPIKeyError,
    VideoGenerationError,
    VideoDownloadError,
    AudioProcessingError,
    VoiceOverGenerationError,
    VideoProcessingError,
    FileValidationError,
    InvalidVideoError,
    InvalidAudioError,
    SegmentationError,
    PollingError,
    TimeoutError,
)

__all__ = [
    "logger",
    "setup_logger",
    "VideoGeneratorError",
    "ConfigurationError",
    "APIError",
    "MissingAPIKeyError",
    "VideoGenerationError",
    "VideoDownloadError",
    "AudioProcessingError",
    "VoiceOverGenerationError",
    "VideoProcessingError",
    "FileValidationError",
    "InvalidVideoError",
    "InvalidAudioError",
    "SegmentationError",
    "PollingError",
    "TimeoutError",
]
