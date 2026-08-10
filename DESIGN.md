# Design

The locked design this repo implements.

## Goals & constraints

- **Private, single-user** YouTube downloader for a home server.
- **All-in-one container** — one Unraid template, no external dependencies.
- **Ephemeral / self-cleaning** — no library to manage; nothing accumulates.
- **Secrets out of the repo** — everything via env vars.
- **Builds itself** — push to GitHub → image on GHCR → Unraid installs it.

## Providers (multi-service)

Each supported service is its own pipeline: an abstract `Provider` base
(`ytsd/providers/base.py`) carries the shared, YouTube-proven machinery (format
ladder, mp3/mkv contract, trim sections, escape hatch), and one subclass per
service declares what differs — domains, quality ceilings, cookies, `curl_cffi`
impersonation, playlist policy, and thumbnails.

| Service | Impersonation | Cookies | Playlist | Notes |
|---|---|---|---|---|
| YouTube | no | optional (`YT_COOKIES`) | reject | Unchanged from the original. |
| Facebook | yes | `FB_COOKIES` (private) | reject | Public best-effort. |
| Reddit | no | `REDDIT_COOKIES` (NSFW) | reject | ffmpeg merges v.redd.it A/V. |
| X | yes | `X_COOKIES` (sensitive) | first | Multi-clip tweet → first video. |
| Instagram | yes | `IG_COOKIES` (**usually required**) | first | Login-walled; gentle request pace. |
| TikTok | yes | `TIKTOK_COOKIES` (region/age) | reject | Public works; photo posts may not. |

URL detection is authoritative (`detect(url)`); the UI service selector is a
convenience that auto-syncs to the detected service. Impersonation targets are
resolved from what yt-dlp reports as actually available, so a missing/mismatched
`curl_cffi` degrades to plain requests instead of hard-failing.

## Architecture

Single Docker image supervised by **s6-overlay**, running three long services
plus a one-shot init:

- `init-prep` (oneshot): purge `TMP_DIR`, optionally `pip install -U yt-dlp`.
- `redis` (longrun): loopback-only queue/state store, no persistence.
- `web` (longrun): FastAPI/uvicorn — UI + API; enqueues jobs, reads status.
- `worker` (longrun): `rq worker-pool -n $WORKERS` running the download job.

`web` and `worker` depend on `redis` and `init-prep`.

### Request flow

1. Browser `POST /api/jobs {url, format, quality}` → job enqueued, id returned.
2. Browser polls `GET /api/jobs/{id}` every ~1.5 s.
3. Worker: probe (reject playlists) → compute filename → `yt-dlp` download →
   progress written to a Redis status hash → mark `ready` with the file path.
4. Browser sees `ready`, hits `GET /api/jobs/{id}/file`, file streams to device.

State lives in `ytsd:job:<id>` (a Redis hash) with a TTL, decoupled from RQ's
own bookkeeping. RQ uses a separate raw (non-decoded) Redis connection.

## Key decisions

| Decision | Choice | Why |
|----------|--------|-----|
| Web framework | FastAPI | Async, tiny, easy auth + status endpoints |
| Queue | Redis + RQ | Lightweight; native N-worker pool |
| Concurrency | `rq worker-pool -n 1..5` | One service, configurable, robust supervision |
| Progress | yt-dlp progress hooks → Redis | Real % for the poll |
| Auth | HTTP Basic, env-gated | Enabled by default; blank creds disable it |
| Storage | Ephemeral, purge-on-start + sweeper | Self-cleaning, no zombies |
| yt-dlp freshness | `AUTO_UPDATE` on start | YouTube breaks pinned builds fast |
| JS runtime | Deno (from official image) | yt-dlp needs it for YouTube challenges |
| Extra control | `EXTRA_YTDLP_ARGS` via `parse_options` | Escape hatch without losing the mp3/mkv contract |
| Playlists | Rejected | Out of scope by design |

## Filename rule

`pascal_filename()` — fold unicode → ASCII, drop illegal chars, PascalCase each
whitespace-separated word, keep `-` as a joiner, truncate to 150 chars, fall back
to `download`. Per-job subdirectories prevent cross-job collisions.

## Quality

- **Video (mkv):** Best / 2160p / 1440p / 1080p / 720p / 480p / 360p →
  `bv*[height<=N]+ba/...`, merged to mkv via ffmpeg.
- **Audio (mp3):** Best (320k) / 320 / 192 / 128 → `FFmpegExtractAudio`.

## Security posture

Designed to sit behind **Cloudflare Tunnel + Google SSO**. Built-in basic auth is
defence-in-depth. Redis is loopback-only. yt-dlp egresses from the host's
residential IP (only the inbound UI goes through the tunnel), which sidesteps most
datacenter-IP bot checks; cookies are the fallback for gated content.

## Out of scope (v1)

Playlists, a persistent library, user accounts, SSE/WebSocket push, subtitle/
thumbnail embedding, multi-arch images (amd64 only — Unraid).
