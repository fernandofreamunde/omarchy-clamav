#!/usr/bin/env bash
# Privileged ClamAV install + configure. Invoked via pkexec from ctl.py.
# Installs the Arch package if missing, downloads virus definitions, and
# enables clamav-freshclam + clamav-daemon.
set -euo pipefail

export PATH="/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

log() { printf '%s\n' "$*"; }

if ! command -v pacman >/dev/null 2>&1; then
  echo "pacman not found — this helper targets Arch / Omarchy" >&2
  exit 127
fi

log "Installing clamav package…"
pacman -S --needed --noconfirm clamav

if ! command -v freshclam >/dev/null 2>&1 || ! command -v clamscan >/dev/null 2>&1; then
  echo "clamav binaries missing after install" >&2
  exit 1
fi

# Packaging usually creates these; make sure the updater can write logs.
install -d -m 0755 -o clamav -g clamav /var/log/clamav 2>/dev/null \
  || mkdir -p /var/log/clamav

# Stop services so freshclam can take the lock for the first DB pull.
systemctl stop clamav-daemon.service 2>/dev/null || true
systemctl stop clamav-freshclam.service 2>/dev/null || true

log "Downloading virus definitions…"
set +e
fresh_out="$(freshclam 2>&1)"
fresh_code=$?
set -e
printf '%s\n' "$fresh_out"

# 0 = updated, 1 = already up to date on some versions
if (( fresh_code != 0 && fresh_code != 1 )); then
  echo "freshclam failed with exit $fresh_code" >&2
  exit "$fresh_code"
fi

log "Enabling clamav-freshclam and clamav-daemon…"
systemctl enable --now clamav-freshclam.service
systemctl enable --now clamav-daemon.service

# Socket unit comes with the daemon package on Arch.
systemctl enable --now clamav-daemon.socket 2>/dev/null || true

if ! systemctl is-active --quiet clamav-freshclam.service; then
  echo "clamav-freshclam failed to start" >&2
  systemctl --no-pager --full status clamav-freshclam.service >&2 || true
  exit 1
fi

if ! systemctl is-active --quiet clamav-daemon.service \
  && ! systemctl is-active --quiet clamav-daemon.socket; then
  echo "clamav-daemon failed to start" >&2
  systemctl --no-pager --full status clamav-daemon.service >&2 || true
  exit 1
fi

log "ClamAV is installed and configured."
exit 0
