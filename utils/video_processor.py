"""
FFmpeg and FFprobe based video processing utilities.
"""

import subprocess
import json
import os
from pathlib import Path
from typing import Tuple, Optional, List
from utils.errors import VideoProcessingError, FileValidationError, InvalidVideoError, InvalidAudioError
from utils.logger import logger
from config import settings


class VideoProcessor:
    """Handle video processing with FFmpeg and FFprobe."""

    @staticmethod
    def validate_video_file(file_path: str) -> dict:
        """
        Validate video file using FFprobe.

        Args:
            file_path: Path to video file

        Returns:
            Dictionary with video metadata

        Raises:
            InvalidVideoError: If file is invalid or corrupted
            FileValidationError: If validation fails
        """
        if not os.path.exists(file_path):
            raise FileValidationError(f"File does not exist: {file_path}")

        if os.path.getsize(file_path) == 0:
            raise InvalidVideoError(f"File is empty: {file_path}")

        try:
            cmd = [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "format=duration,size,bit_rate:stream=width,height,codec_name,codec_type",
                "-of",
                "json",
                file_path,
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=settings.request_timeout_seconds,
            )

            if result.returncode != 0:
                raise InvalidVideoError(
                    f"FFprobe validation failed: {result.stderr[:200]}"
                )

            data = json.loads(result.stdout)

            # Check format
            if "format" not in data:
                raise InvalidVideoError("No format information found")

            # Extract metadata
            metadata = {
                "duration": float(data["format"].get("duration", 0)),
                "size": int(data["format"].get("size", 0)),
                "bit_rate": int(data["format"].get("bit_rate", 0)),
            }

            # Get video stream info
            streams = data.get("streams", [])
            for stream in streams:
                if stream.get("codec_type") == "video":
                    metadata["width"] = stream.get("width", 0)
                    metadata["height"] = stream.get("height", 0)
                    metadata["codec"] = stream.get("codec_name", "unknown")
                    break

            logger.info(f"Video validation passed: {file_path}")
            logger.debug(f"Video metadata: {metadata}")

            return metadata

        except subprocess.TimeoutExpired:
            raise FileValidationError(f"FFprobe timeout for: {file_path}")
        except json.JSONDecodeError as e:
            raise InvalidVideoError(f"Could not parse FFprobe output: {e}")
        except Exception as e:
            raise FileValidationError(f"Error validating video: {e}")

    @staticmethod
    def validate_audio_file(file_path: str) -> dict:
        """
        Validate audio file using FFprobe.

        Args:
            file_path: Path to audio file

        Returns:
            Dictionary with audio metadata

        Raises:
            InvalidAudioError: If file is invalid
        """
        if not os.path.exists(file_path):
            raise FileValidationError(f"File does not exist: {file_path}")

        if os.path.getsize(file_path) == 0:
            raise FileValidationError(f"File is empty: {file_path}")

        try:
            cmd = [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_entries",
                "format=duration,size:stream=codec_name,channels,sample_rate",
                "-of",
                "json",
                file_path,
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=settings.request_timeout_seconds,
            )

            if result.returncode != 0:
                raise FileValidationError(f"FFprobe validation failed: {result.stderr}")

            data = json.loads(result.stdout)

            metadata = {
                "duration": float(data["format"].get("duration", 0)),
                "size": int(data["format"].get("size", 0)),
            }

            # Get audio stream info
            streams = data.get("streams", [])
            for stream in streams:
                if stream.get("codec_type") == "audio":
                    metadata["channels"] = stream.get("channels", 0)
                    metadata["sample_rate"] = stream.get("sample_rate", 0)
                    metadata["codec"] = stream.get("codec_name", "unknown")
                    break

            logger.info(f"Audio validation passed: {file_path}")
            return metadata

        except subprocess.TimeoutExpired:
            raise FileValidationError(f"FFprobe timeout for: {file_path}")
        except json.JSONDecodeError as e:
            raise FileValidationError(f"Could not parse FFprobe output: {e}")
        except Exception as e:
            raise FileValidationError(f"Error validating audio: {e}")

    @staticmethod
    def merge_audio_video(
        video_path: str,
        audio_path: str,
        output_path: str,
        video_codec: str = "copy",
        audio_codec: str = "aac",
    ) -> None:
        """
        Merge audio and video into single file.

        Args:
            video_path: Path to video file
            audio_path: Path to audio file
            output_path: Path to output file
            video_codec: Video codec (default: copy)
            audio_codec: Audio codec (default: aac)

        Raises:
            VideoProcessingError: If merging fails
        """
        try:
            cmd = [
                "ffmpeg",
                "-i",
                video_path,
                "-i",
                audio_path,
                "-c:v",
                video_codec,
                "-c:a",
                audio_codec,
                "-shortest",
                "-y",
                output_path,
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=settings.request_timeout_seconds * 5,
            )

            if result.returncode != 0:
                raise VideoProcessingError(f"FFmpeg merge failed: {result.stderr[:200]}")

            logger.info(f"Audio merged with video: {output_path}")

        except subprocess.TimeoutExpired:
            raise VideoProcessingError(f"FFmpeg merge timeout for {output_path}")
        except Exception as e:
            raise VideoProcessingError(f"Error merging audio and video: {e}")

    @staticmethod
    def concatenate_videos(
        video_paths: List[str], output_path: str, temp_concat_file: Optional[str] = None
    ) -> None:
        """
        Concatenate multiple videos into single file.

        Args:
            video_paths: List of video file paths
            output_path: Path to output file
            temp_concat_file: Path to temporary concat demuxer file

        Raises:
            VideoProcessingError: If concatenation fails
        """
        if len(video_paths) == 0:
            raise VideoProcessingError("No videos to concatenate")

        if len(video_paths) == 1:
            # Single video, just copy
            cmd = ["ffmpeg", "-i", video_paths[0], "-c", "copy", "-y", output_path]
        else:
            # Multiple videos, use concat demuxer
            temp_concat_file = temp_concat_file or os.path.join(
                settings.temp_dir, "concat_list.txt"
            )

            # Create concat file
            with open(temp_concat_file, "w") as f:
                for video_path in video_paths:
                    f.write(f"file '{os.path.abspath(video_path)}'\n")

            cmd = [
                "ffmpeg",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                temp_concat_file,
                "-c",
                "copy",
                "-y",
                output_path,
            ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=settings.request_timeout_seconds * 10,
            )

            if result.returncode != 0:
                raise VideoProcessingError(
                    f"FFmpeg concatenation failed: {result.stderr[:200]}"
                )

            logger.info(f"Videos concatenated: {output_path}")

            # Clean up temp concat file
            if temp_concat_file and os.path.exists(temp_concat_file):
                try:
                    os.remove(temp_concat_file)
                except Exception as e:
                    logger.warning(f"Could not remove temp concat file: {e}")

        except subprocess.TimeoutExpired:
            raise VideoProcessingError(f"FFmpeg concatenation timeout for {output_path}")
        except Exception as e:
            raise VideoProcessingError(f"Error concatenating videos: {e}")

    @staticmethod
    def mix_audio(
        audio_paths: List[Tuple[str, float]],
        output_path: str,
        duration: Optional[float] = None,
    ) -> None:
        """
        Mix multiple audio streams.

        Args:
            audio_paths: List of (audio_path, volume) tuples
            output_path: Path to output audio
            duration: Target duration in seconds

        Raises:
            VideoProcessingError: If mixing fails
        """
        if not audio_paths:
            raise VideoProcessingError("No audio files to mix")

        try:
            inputs = []
            filters = []

            for i, (audio_path, volume) in enumerate(audio_paths):
                inputs.extend(["-i", audio_path])
                filters.append(f"[{i}]volume={volume}[a{i}]")

            # Combine filters
            filter_str = ";".join(filters)
            audio_labels = "".join([f"[a{i}]" for i in range(len(audio_paths))])
            filter_str += f";{audio_labels}amix=inputs={len(audio_paths)}:duration=longest[a]"

            cmd = (
                ["ffmpeg"]
                + inputs
                + [
                    "-filter_complex",
                    filter_str,
                    "-map",
                    "[a]",
                    "-y",
                    output_path,
                ]
            )

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=settings.request_timeout_seconds * 5,
            )

            if result.returncode != 0:
                raise VideoProcessingError(
                    f"FFmpeg audio mix failed: {result.stderr[:200]}"
                )

            logger.info(f"Audio mixed: {output_path}")

        except subprocess.TimeoutExpired:
            raise VideoProcessingError(f"FFmpeg audio mix timeout for {output_path}")
        except Exception as e:
            raise VideoProcessingError(f"Error mixing audio: {e}")

    @staticmethod
    def trim_video(
        input_path: str, output_path: str, start_time: float, end_time: float
    ) -> None:
        """
        Trim video to specific time range.

        Args:
            input_path: Input video path
            output_path: Output video path
            start_time: Start time in seconds
            end_time: End time in seconds

        Raises:
            VideoProcessingError: If trimming fails
        """
        duration = end_time - start_time

        try:
            cmd = [
                "ffmpeg",
                "-ss",
                str(start_time),
                "-i",
                input_path,
                "-t",
                str(duration),
                "-c",
                "copy",
                "-y",
                output_path,
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=settings.request_timeout_seconds * 5,
            )

            if result.returncode != 0:
                raise VideoProcessingError(
                    f"FFmpeg trim failed: {result.stderr[:200]}"
                )

            logger.info(f"Video trimmed: {output_path}")

        except subprocess.TimeoutExpired:
            raise VideoProcessingError(f"FFmpeg trim timeout for {output_path}")
        except Exception as e:
            raise VideoProcessingError(f"Error trimming video: {e}")

    @staticmethod
    def resize_video(
        input_path: str,
        output_path: str,
        width: int,
        height: int,
        maintain_aspect: bool = True,
    ) -> None:
        """
        Resize video to specific dimensions.

        Args:
            input_path: Input video path
            output_path: Output video path
            width: Target width
            height: Target height
            maintain_aspect: Maintain aspect ratio with padding

        Raises:
            VideoProcessingError: If resizing fails
        """
        try:
            if maintain_aspect:
                # Scale with padding to maintain aspect ratio
                scale_filter = (
                    f"scale=w={width}:h={height}:force_original_aspect_ratio=decrease,"
                    f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2"
                )
            else:
                scale_filter = f"scale={width}:{height}"

            cmd = [
                "ffmpeg",
                "-i",
                input_path,
                "-vf",
                scale_filter,
                "-c:a",
                "aac",
                "-y",
                output_path,
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=settings.request_timeout_seconds * 10,
            )

            if result.returncode != 0:
                raise VideoProcessingError(
                    f"FFmpeg resize failed: {result.stderr[:200]}"
                )

            logger.info(f"Video resized to {width}x{height}: {output_path}")

        except subprocess.TimeoutExpired:
            raise VideoProcessingError(f"FFmpeg resize timeout for {output_path}")
        except Exception as e:
            raise VideoProcessingError(f"Error resizing video: {e}")

    @staticmethod
    def get_video_duration(file_path: str) -> float:
        """
        Get video duration in seconds.

        Args:
            file_path: Path to video file

        Returns:
            Duration in seconds

        Raises:
            FileValidationError: If unable to determine duration
        """
        try:
            cmd = [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1:noescaping=1",
                file_path,
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=settings.request_timeout_seconds,
            )

            if result.returncode != 0:
                raise FileValidationError(f"Could not determine video duration")

            duration = float(result.stdout.strip())
            return duration

        except ValueError:
            raise FileValidationError(f"Invalid duration format")
        except Exception as e:
            raise FileValidationError(f"Error getting video duration: {e}")
