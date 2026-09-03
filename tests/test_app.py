from app import DEFAULT_DURATION, DURATION_OPTIONS


def test_studio_duration_contract():
    assert tuple(DURATION_OPTIONS) == ("30s", "3 min", "4 min", "5 min")
    assert DEFAULT_DURATION == "4 min"
    assert DURATION_OPTIONS[DEFAULT_DURATION] == 240
