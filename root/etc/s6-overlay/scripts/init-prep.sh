#!/usr/bin/env bash
# Runs once at container start, before the web/worker services.
#   1. Purge the ephemeral temp dir (cull zombie/ghost downloads from last run).
#   2. Optionally self-update yt-dlp.
set -u

TMP="${TMP_DIR:-/downloads}"
echo "[ytsd] init: purging temp dir ${TMP}"
mkdir -p "${TMP}"
find "${TMP}" -mindepth 1 -maxdepth 1 -exec rm -rf {} + 2>/dev/null || true

AU="$(printf '%s' "${AUTO_UPDATE:-true}" | tr '[:upper:]' '[:lower:]')"
case "${AU}" in
  1|true|yes|on)
    echo "[ytsd] init: updating yt-dlp"
    # [default] keeps curl_cffi (impersonation backend) upgraded compatibly.
    pip install --no-cache-dir --upgrade "yt-dlp[default]" \
      || echo "[ytsd] WARN: yt-dlp update failed, continuing with bundled version"
    ;;
  *)
    echo "[ytsd] init: AUTO_UPDATE disabled, using bundled yt-dlp"
    ;;
esac

echo "[ytsd] init: complete"
