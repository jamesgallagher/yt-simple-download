# syntax=docker/dockerfile:1

########## deno (JS runtime yt-dlp uses to solve YouTube's challenges) ##########
FROM denoland/deno:bin-2.1.4 AS deno

########## runtime ##########
FROM python:3.12-slim

ARG S6_OVERLAY_VERSION=3.2.0.2
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    S6_KEEP_ENV=1 \
    S6_CMD_WAIT_FOR_SERVICES_MAXTIME=0

# System deps: redis, ffmpeg (mux/transcode), plus tools to fetch s6-overlay.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        xz-utils \
        ffmpeg \
        redis-server \
    && rm -rf /var/lib/apt/lists/*

# s6-overlay (single-container process supervisor).
ADD https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-noarch.tar.xz /tmp/
ADD https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-x86_64.tar.xz /tmp/
RUN tar -C / -Jxpf /tmp/s6-overlay-noarch.tar.xz \
    && tar -C / -Jxpf /tmp/s6-overlay-x86_64.tar.xz \
    && rm -f /tmp/s6-overlay-*.tar.xz

# Deno binary from the official image.
COPY --from=deno /deno /usr/local/bin/deno

# Python deps.
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code, static assets, and the s6 service tree.
COPY ytsd/ ./ytsd/
COPY root/ /
COPY icon.png ./ytsd/static/icon.png

# Make service scripts executable (git on some hosts drops the +x bit).
RUN chmod -R 0755 /etc/s6-overlay/scripts \
    && find /etc/s6-overlay/s6-rc.d -name run -exec chmod 0755 {} \;

ENV TMP_DIR=/downloads \
    QUEUE_NAME=downloads \
    PORT=8080 \
    WORKERS=1 \
    AUTO_UPDATE=true \
    RETENTION_HOURS=6

VOLUME ["/downloads", "/config"]
EXPOSE 8080

ENTRYPOINT ["/init"]
