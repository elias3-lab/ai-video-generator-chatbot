"""
Custom exception classes for AI Video Generator.
"""


class VideoGeneratorError(Exception):
    """Base exception for video generator."""

    pass


class ConfigurationError(VideoGeneratorError):
    """Raised when configuration is invalid or missing."""

    pass


class APIError(VideoGeneratorError):
    """Raised when API call fails."""

    pass


class MissingAPIKeyError(ConfigurationError):
    """Raised when a required API key is missing."""

    pass


class VideoGenerationError(VideoGeneratorError):
    """Raised when video generation fails."""

    pass


class VideoDownloadError(VideoGeneratorError):
    """Raised when video download fails."""

    pass


class AudioProcessingError(VideoGeneratorError):
    """Raised when audio processing fails."""

    pass


class VoiceOverGenerationError(AudioProcessingError):
    """Raised when voice-over generation fails."""

    pass


class VideoProcessingError(VideoGeneratorError):
    """Raised when video processing (FFmpeg) fails."""

    pass


class FileValidationError(VideoGeneratorError):
    """Raised when file validation fails."""

    pass


class InvalidVideoError(FileValidationError):
    """Raised when video file is invalid or corrupted."""

    pass


class InvalidAudioError(FileValidationError):
    """Raised when audio file is invalid or corrupted."""

    pass


class SegmentationError(VideoGeneratorError):
    """Raised when video segmentation fails."""

    pass


class PollingError(VideoGeneratorError):
    """Raised when polling for async task completion fails."""

    pass


class TimeoutError(VideoGeneratorError):
    """Raised when polling exceeds maximum timeout."""

    pass
