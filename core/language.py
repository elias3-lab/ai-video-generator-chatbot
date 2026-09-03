"""Supported project languages for script generation and voice-over."""

from __future__ import annotations

from enum import Enum


class ContentLanguage(str, Enum):
    ENGLISH = "en"
    ARABIC = "ar"
    FRENCH = "fr"
    GERMAN = "de"


LANGUAGE_NAMES = {
    ContentLanguage.ENGLISH: "English",
    ContentLanguage.ARABIC: "Arabic",
    ContentLanguage.FRENCH: "French",
    ContentLanguage.GERMAN: "German",
}


def validate_language(language: str) -> ContentLanguage:
    """Return a supported language or raise a clear validation error."""
    try:
        return ContentLanguage(language.lower().strip())
    except (ValueError, AttributeError) as exc:
        supported = ", ".join(item.value for item in ContentLanguage)
        raise ValueError(f"Unsupported language. Choose: {supported}") from exc


def language_name(language: str | ContentLanguage) -> str:
    """Return the human-readable name for a supported language."""
    value = language if isinstance(language, ContentLanguage) else validate_language(language)
    return LANGUAGE_NAMES[value]
