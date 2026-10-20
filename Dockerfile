# VideoMind Gateway 服务端镜像（不含 GUI / PySide6）
#
# 构建（仅服务端）:
#   docker build -t videomind-gateway .
# 构建（带 SenseVoice 运行时，模型仍需挂载）:
#   docker build --build-arg PIP_EXTRAS=sensevoice -t videomind-gateway .
#
# 运行:
#   docker run --rm -p 8787:8787 \
#     -e VIDEOMIND_API_TOKEN=change-me \
#     -v vmb-config:/home/videomind/.config/VideoMind \
#     -v vmb-cache:/home/videomind/.cache \
#     -v vmb-data:/data \
#     videomind-gateway

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/home/videomind \
    VMB_MEDIA_DIR=/data/media \
    VMB_PUBLIC_URL=http://127.0.0.1:8787

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 10001 videomind

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY scripts ./scripts
COPY web ./web
COPY main.py ./

ARG PIP_EXTRAS=""
ARG PIP_INDEX_URL=""
RUN PIP_ARGS=""; \
    if [ -n "$PIP_INDEX_URL" ]; then PIP_ARGS="--index-url $PIP_INDEX_URL"; fi; \
    if [ -n "$PIP_EXTRAS" ]; then \
        pip install $PIP_ARGS --no-cache-dir ".[$PIP_EXTRAS]"; \
    else \
        pip install $PIP_ARGS --no-cache-dir .; \
    fi

RUN mkdir -p /app/data /home/videomind/.config/VideoMind /home/videomind/.cache \
        /home/videomind/Downloads/VideoMind /data/media /models/sense-voice \
    && chown -R videomind:videomind /app /home/videomind /data /models

USER videomind

EXPOSE 8787

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8787/health || exit 1

CMD ["python", "main.py", "--api", "--host", "0.0.0.0", "--port", "8787"]