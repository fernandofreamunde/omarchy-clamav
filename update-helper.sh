#!/usr/bin/env bash
# Privileged virus-definition refresh. Invoked via pkexec from ctl.py.
set -euo pipefail

export PATH="/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

if ! command -v freshclam >/dev/null 2>&1; then
  echo "freshclam not found" >&2
  exit 127
fi

was_active=0
if systemctl is-active --quiet clamav-freshclam.service; then
  was_active=1
  systemctl stop clamav-freshclam.service
fi

cleanup() {
  if (( was_active )); then
    systemctl start clamav-freshclam.service >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

# freshclam returns 0 on success / already up to date; 1 often means "up to date"
# depending on version — treat only hard failures as errors.
set +e
out="$(freshclam 2>&1)"
code=$?
set -e

printf '%s\n' "$out"

if (( code == 0 || code == 1 )); then
  exit 0
fi
exit "$code"
