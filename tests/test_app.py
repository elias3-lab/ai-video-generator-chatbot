from app import (
    CONTENT_TYPES,
    DEFAULT_CONTENT_TYPE,
    DEFAULT_DURATION,
    DEFAULT_VIDEO_FORMAT,
    DURATION_OPTIONS,
    VIDEO_FORMATS,
    _content_style,
    _duration_seconds,
    _video_dimensions,
    _sanitize_error,
)


def test_studio_duration_contract():
    assert tuple(DURATION_OPTIONS) == ("30s", "3 min", "4 min", "5 min")
    assert DEFAULT_DURATION == "4 min"
    assert DURATION_OPTIONS[DEFAULT_DURATION] == 240


def test_studio_type_and_format_contract():
    assert CONTENT_TYPES == ("Documentary", "Film")
    assert VIDEO_FORMATS == ("YouTube 16:9", "Shorts 9:16")
    assert DEFAULT_CONTENT_TYPE == "Documentary"
    assert DEFAULT_VIDEO_FORMAT == "YouTube 16:9"
    assert _content_style("Documentary")
    assert _content_style("Film")
    assert _video_dimensions("YouTube 16:9") == (1920, 1080)
    assert _video_dimensions("Shorts 9:16") == (1080, 1920)


def test_invalid_studio_options_fail_fast():
    for func, value in (
        (_duration_seconds, "bad"),
        (_content_style, "bad"),
        (_video_dimensions, "bad"),
    ):
        try:
            func(value)
        except ValueError:
            pass
        else:
            raise AssertionError(f"{func.__name__} accepted invalid value")


def test_sanitize_error_redacts_credentials():
    value = "https://example.test/api?key=SECRET123&x=1 token=SECRET456"
    safe = _sanitize_error(value)
    assert "SECRET123" not in safe
    assert "SECRET456" not in safe
    assert "REDACTED" in safe
