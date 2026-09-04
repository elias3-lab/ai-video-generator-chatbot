---
title: CASTELOU AI Documentary Studio
emoji: 🎬
colorFrom: gray
colorTo: yellow
sdk: docker
app_port: 7860
---

# CASTELOU AI DOCUMENTARY STUDIO

CASTELOU is a phone-friendly AI cinematic video pipeline for documentary and narrative projects.

## Production pipeline

`Prompt → Director → Visual DNA → Scene plan → AI video/fallback media → scene narration → measured audio sync → subtitles → final MP4`

### Current capabilities

- English-first documentary/film generation with `en`, `ar`, `fr`, and `de` language support.
- 30-second, 3-minute, 4-minute, and 5-minute project targets.
- Global `MAX_VIDEO_DURATION=120` remains enforced; longer projects are represented as short scenes.
- Cinematic Director beats: Hook → Journey → Discovery → Ending.
- Stable Visual DNA and continuity context across scenes.
- MiniMax → Runway → free-media fallback routing.
- ElevenLabs scene-by-scene voice generation with real audio-duration measurement.
- Scene-synchronized SRT subtitles muxed into the final MP4 as a selectable subtitle track.
- Checkpointed scene execution and resume support.
- FFmpeg normalization to 16:9 or 9:16 output at 30 fps / H.264 / yuv420p.
- Automated pytest coverage and Docker smoke testing in GitHub Actions.

## Environment variables

Required for the full AI pipeline:

- `MINIMAX_API_KEY`
- `RUNWAY_API_KEY`
- `ELEVENLABS_API_KEY`
- `ELEVENLABS_VOICE_ID`

Optional free-media providers:

- `PEXELS_API_KEY`
- `PIXABAY_API_KEY`

See `.env.example` for the complete configuration template. Never commit real API keys.

## Run locally

```bash
pip install -r requirements.txt
python app.py
```

The Gradio app listens on port `7860`.

## Docker / Hugging Face Spaces

The repository includes a Dockerfile that installs FFmpeg, Python dependencies, and launches the Gradio application on port `7860`.
