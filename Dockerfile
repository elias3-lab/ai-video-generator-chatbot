FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl espeak-ng \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p outputs checkpoints models \
    && curl -fL --retry 3 -o models/kokoro-v1.0.int8.onnx https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/kokoro-v1.0.int8.onnx \
    && curl -fL --retry 3 -o models/voices-v1.0.bin https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/voices-v1.0.bin

# Local male documentary narrator by default. No external TTS API is required.
ENV KOKORO_VOICE=am_michael \
    KOKORO_SPEED=1.0

EXPOSE 7860

# launcher.py performs startup recovery for queued/running jobs, then starts Gradio.
CMD ["python", "launcher.py"]
