# yt-simple-download

A tiny, private, self-hosted YouTube downloader. Paste a link, pick **Audio (mp3)**
or **Video (mkv)** and a quality, hit **Download** — the finished file streams
straight to your phone or PC.

<p align="center"><img src="icon.png" width="112" alt="app icon"></p>

Built for a home server (Unraid) as a single all-in-one Docker container.

## What's inside (one container)

| Piece | Role |
|-------|------|
| **FastAPI** (uvicorn) | Web UI + JSON API; only ever writes to the queue |
| **Redis** | Job queue + status (loopback only, never exposed) |
| **RQ worker pool** | 1–5 workers running `yt-dlp` |
| **yt-dlp + ffmpeg** | Download, merge to mkv, or extract to mp3 |
| **Deno** | JS runtime yt-dlp uses to solve YouTube's challenges |
| **s6-overlay** | Supervises all of the above in one image |

## How it works

```
browser ──POST /api/jobs──▶ FastAPI ──enqueue──▶ Redis ──▶ worker ──▶ yt-dlp
   ▲                           │                                        │
   └──poll /api/jobs/{id}──────┘◀────────── status hash ◀───────────────┘
   └──GET  /api/jobs/{id}/file ─────────────▶ finished file (once ready)
```

- **Ephemeral & self-cleaning.** The temp dir is purged on every container start
  (kills zombie/ghost downloads) and finished files are swept after
  `RETENTION_HOURS`.
- **Single videos only.** Playlist URLs are rejected with
  *"Playlists are not supported"*.
- **Filenames** are PascalCased: `James Gallagher - Best Video Highlights` →
  `JamesGallagher-BestVideoHighlights.mkv`.

## Configuration

All settings are environment variables — see [`.env.example`](.env.example).
Nothing secret is committed to the repo.

| Var | Default | Notes |
|-----|---------|-------|
| `APP_USER` / `APP_PASSWORD` | `admin` / `changeme` | Basic auth. **Clear both to disable** (e.g. behind Cloudflare + SSO). |
| `WORKERS` | `1` | Concurrent downloads, clamped 1–5. |
| `AUTO_UPDATE` | `true` | Self-update yt-dlp on start. |
| `RETENTION_HOURS` | `6` | Auto-delete window. |
| `YT_COOKIES` | *(empty)* | Optional path to a mounted `cookies.txt` for age-restricted content. |
| `EXTRA_YTDLP_ARGS` | *(empty)* | Advanced escape hatch. |
| `TMP_DIR` | `/downloads` | Ephemeral working dir. |
| `PORT` | `8080` | Web UI port. |

## Run it

### Docker

```bash
docker run -d --name yt-simple-download \
  -p 8080:8080 \
  -e APP_USER=admin -e APP_PASSWORD='change-me' \
  -e WORKERS=2 \
  -v /path/to/downloads:/downloads \
  ghcr.io/jamesgallagher/yt-simple-download:latest
```

Open `http://<host>:8080/`.

### Unraid

Add the template [`unraid/yt-simple-download.xml`](unraid/yt-simple-download.xml)
(or install from Community Applications once published). Set a password, pick your
worker count, map a downloads path, and go.

## Cookies (optional)

Ordinary public videos download anonymously. For **age-restricted / members-only**
content, export a Netscape-format `cookies.txt` from a browser logged into a
**throwaway** Google account (a cookie file grants full account access), mount it,
and set `YT_COOKIES=/config/cookies.txt`.

## Development

```bash
pip install -r requirements.txt
# needs a local redis on 127.0.0.1:6379
python -m uvicorn ytsd.web:app --reload --port 8080   # terminal 1
rq worker-pool --num-workers 1 downloads              # terminal 2
```

## Notes

- Downloading may be against YouTube's Terms of Service; use for content you have
  the right to download. This is a personal tool.
- Built to run behind Cloudflare Tunnel + Google SSO; the built-in basic auth is
  defence-in-depth, not a substitute for a proper front door if exposed.
