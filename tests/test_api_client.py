from utils.api_client import APIClient


def test_post_accepts_query_params(monkeypatch):
    client = APIClient("test-key", "https://example.com")
    captured = {}

    def fake_request(**kwargs):
        captured.update(kwargs)

        class Response:
            status_code = 200

        return Response()

    monkeypatch.setattr(client.session, "request", fake_request)
    client.post("/tts/voice", json={"text": "hello"}, params={"output_format": "mp3_44100_128"})
    assert captured["params"] == {"output_format": "mp3_44100_128"}
