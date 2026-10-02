# syntax=docker/dockerfile:1
# Multi-stage Dockerfile
# Stage 1: Builder - Install Python dependencies into a venv via uv
# (mirrors .devcontainer/Dockerfile's venv-builder stage).
FROM python:3.13-slim AS builder

WORKDIR /app

# Install git in builder stage (needed for any pip install from git URLs)
RUN apt-get update && apt-get install -y \
    git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# uv (https://github.com/astral-sh/uv) for ~5-10x faster installs than pip.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# Build the venv at the path it will live at in the final image, so shebangs
# and console-scripts inside the venv reference the correct runtime location
# after COPY --from.
ENV VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH
RUN python -m venv "$VIRTUAL_ENV"

# Layer 1: API deps. Cache invalidates only when requirements.txt changes.
RUN --mount=type=bind,source=api/requirements.txt,target=/tmp/req.txt \
    --mount=type=cache,target=/root/.cache/uv \
    uv pip install -r /tmp/req.txt

# Layer 2: pipecat deps. Cache invalidates when pipecat source changes.
# Voice-only WebRTC: aiortc is installed explicitly in requirements.txt.
# Avoid the upstream webrtc extra, which also installs OpenCV for video.
RUN --mount=type=bind,source=pipecat,target=/tmp/pipecat,rw \
    --mount=type=cache,target=/root/.cache/uv \
    uv pip install '/tmp/pipecat[cartesia,deepgram,openai,elevenlabs,groq,google,azure,sarvam,soundfile,silero,speechmatics,openrouter,camb,mcp,inworld,smallest,aws-nova-sonic]'

# Strip cache files, test/example dirs, and type stubs from the venv
RUN uv pip uninstall pip setuptools || true
RUN find /opt/venv -type f -name '*.pyc' -delete && \
    find /opt/venv -type d -name '__pycache__' -prune -exec rm -rf {} + && \
    find /opt/venv -type f -name '*.pyo' -delete && \
    find /opt/venv -type d \( -name tests -o -name test -o -name examples \) -prune -exec rm -rf {} + && \
    find /opt/venv -name '*.pyi' -delete

# Stage 2: Node deps for ts_validator (built with full node:22-slim, only
# node_modules is copied into the runner).
FROM node:22-slim AS ts-deps
WORKDIR /ts_validator
COPY api/mcp_server/ts_validator/package*.json ./
RUN npm ci --omit=dev && npm cache clean --force
RUN apt-get update && apt-get install -y --no-install-recommends binutils \
 && cp /usr/local/bin/node /ts_validator/node-runtime \
 && strip --strip-unneeded /ts_validator/node-runtime

# Build an audio-only FFmpeg; compilers and source never enter the runner.
# Source archive is pinned by SHA256; both runtime architectures use the same source.
FROM debian:trixie-slim AS ffmpeg-static
ARG FFMPEG_VERSION=8.0.2
ARG FFMPEG_SHA256=5d16962332603c427b3d0887fc12b9166d6ee2cb1108b1865dd2d5eb06a09505
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential pkg-config nasm curl ca-certificates xz-utils libopus-dev libmp3lame-dev \
 && rm -rf /var/lib/apt/lists/*
RUN set -eu; \
    curl -fsSL --retry 3 --connect-timeout 20 --max-time 300 \
      "https://ffmpeg.org/releases/ffmpeg-${FFMPEG_VERSION}.tar.xz" -o /tmp/ffmpeg.tar.xz; \
    echo "${FFMPEG_SHA256}  /tmp/ffmpeg.tar.xz" | sha256sum -c -; \
    mkdir /tmp/ffmpeg; tar -xJf /tmp/ffmpeg.tar.xz -C /tmp/ffmpeg --strip-components=1; \
    cd /tmp/ffmpeg; \
    ./configure --prefix=/out --disable-everything --disable-autodetect \
      --disable-debug --disable-doc --disable-network --disable-avdevice \
      --disable-shared --enable-static --pkg-config-flags=--static \
      --enable-ffmpeg --enable-ffprobe --enable-avcodec --enable-avformat --enable-avfilter --enable-swresample \
      --enable-protocol=file,pipe \
      --enable-demuxer=wav,mp3,ogg,flac,mov,aac,matroska,pcm_s16le,pcm_s16be \
      --enable-muxer=wav,mp3,ogg,flac,pcm_s16le,pcm_s16be,adts \
      --enable-decoder=pcm_s16le,pcm_s16be,pcm_s24le,pcm_s24be,pcm_s32le,pcm_f32le,pcm_f64le,pcm_alaw,pcm_mulaw,mp3,mp3float,aac,flac,vorbis,opus \
      --enable-parser=mpegaudio,aac,flac,opus,vorbis \
      --enable-libopus --enable-libmp3lame --enable-encoder=pcm_s16le,pcm_s16be,flac,aac,libopus,libmp3lame \
      --enable-filter=aresample,aformat,anull,atrim,asetpts,concat,volume,adelay; \
    make -j2; make install; \
    mkdir -p /out/licenses; cp COPYING.LGPLv2.1 COPYING.LGPLv3 LICENSE.md /out/licenses/

# Prepare application files without tests or developer artifacts in the image.
FROM python:3.13-slim AS source
WORKDIR /source
COPY api ./api
RUN find api -type d \( -name tests -o -name __pycache__ -o -name .pytest_cache \) -prune -exec rm -rf {} + \
 && rm -rf api/load_tests api/conftest.py api/pytest.ini api/requirements.dev.txt

# Stage 4: Runtime - Minimal image with only runtime dependencies
FROM python:3.13-slim AS runner

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends libopus0 libmp3lame0 \
 && rm -rf /var/lib/apt/lists/*

RUN groupadd --system dograh \
 && useradd --system --gid dograh --no-log-init --home-dir /app --shell /usr/sbin/nologin dograh \
 && chown dograh:dograh /app

# Static ffmpeg + ffprobe (used by audio_converter, audio_file_cache, etc.)
COPY --from=ffmpeg-static /out/bin/ffmpeg /usr/local/bin/ffmpeg
COPY --from=ffmpeg-static /out/bin/ffprobe /usr/local/bin/ffprobe
COPY --from=ffmpeg-static /out/licenses /usr/share/licenses/ffmpeg

# Node.js 22 binary only (ts_validator subprocess needs node >=22.6 for
# native TypeScript stripping; see api/mcp_server/ts_bridge.py). python:3.13-slim
# already provides libstdc++6, libgcc-s1, and ca-certificates that node needs.
COPY --from=ts-deps /ts_validator/node-runtime /usr/local/bin/node

# Copy the populated venv from the builder stage.
COPY --from=builder /opt/venv /opt/venv

# Activate the venv for subsequent RUN/CMD layers.
ENV VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH

# Set Python to not generate .pyc files in runtime
ENV PYTHONDONTWRITEBYTECODE=1
# Unbuffered output for better container logging
ENV PYTHONUNBUFFERED=1

# Copy application code (chown at copy-time avoids a duplicate /app layer
# from a later `RUN chown -R`, which would double the on-disk size of /app).
COPY --from=source --chown=dograh:dograh /source/api ./api

# Entrypoint scripts.
#   start_services_docker.sh — single-container (docker-compose) entrypoint
#     that runs every service in one process tree.
#   run_*.sh                 — per-service entrypoints used by the Helm chart,
#     which runs each workload (web, arq-worker, ari-manager,
#     campaign-orchestrator, migrate) as its own pod. Keep this list in sync
#     with the command:[] entries in deploy/helm/dograh/templates/*.yaml.
#   drain_web.sh             — web pod preStop hook (call-safe scale-down); see
#     lifecycle.preStop in deploy/helm/dograh/templates/web-deployment.yaml.
COPY --chown=dograh:dograh \
     ./scripts/start_services_docker.sh \
     ./scripts/run_migrate.sh \
     ./scripts/run_web.sh \
     ./scripts/run_arq_worker.sh \
     ./scripts/run_ari_manager.sh \
     ./scripts/run_campaign_orchestrator.sh \
     ./scripts/drain_web.sh \
     ./scripts/

# Existing Windows checkouts can retain CRLF despite .gitattributes.
# Normalize entrypoints inside the image before Linux executes their shebangs.
RUN sed -i 's/\r$//' ./scripts/*.sh

# ts_validator Node deps (built in ts-deps stage with full node:22-slim image).
# The validator runs as a short-lived subprocess from api/mcp_server/ts_bridge.py.
COPY --from=ts-deps --chown=dograh:dograh /ts_validator/node_modules ./api/mcp_server/ts_validator/node_modules

# Product documentation — read at runtime by the MCP docs tools
# (search_dograh_docs / fetch_dograh_doc) so agents can learn Dograh.
COPY --chown=dograh:dograh ./docs ./docs
COPY --chown=dograh:dograh ./LICENSE /usr/share/licenses/dograh/LICENSE

ENV PYTHONPATH=/app

# Disable file logging in Docker - logs go to stdout for docker logs
ENV LOG_TO_FILE=false

USER dograh

# Expose the port FastAPI will run on
EXPOSE 8000

# Run the FastAPI app with uvicorn
CMD ["./scripts/start_services_docker.sh"]

# Explicit test target; production builds select runner and contain no pytest.
FROM runner AS test
USER root
COPY --from=builder /usr/local/bin/uv /usr/local/bin/uv
RUN uv pip install pytest pytest-asyncio pytest-mock pytest-aiohttp hypothesis faker
COPY api/tests ./api/tests
COPY api/load_tests ./api/load_tests
COPY api/conftest.py api/pytest.ini ./api/
COPY sdk/python/src ./sdk/python/src
COPY sdk/typescript ./sdk/typescript
COPY pipecat/src/pipecat/tests /opt/venv/lib/python3.13/site-packages/pipecat/tests
USER dograh

# Keep the default output as the production image.
FROM runner AS production
