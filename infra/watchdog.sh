#!/usr/bin/env bash
# Myra site watchdog — runs in WSL, driven by a systemd --user timer.
#
# Lives in WSL rather than a Windows scheduled task because Task Scheduler
# launching powershell.exe flashes a console window every run: -WindowStyle
# Hidden is applied by PowerShell *after* the console host is already created,
# so it cannot suppress it. Every five minutes, visibly, forever.
#
# WSL also matches how VOS III already runs on this machine (systemd --user +
# loginctl enable-linger), so there is one operational pattern, not two.
#
# Checks the PUBLIC url end to end, not a local process: the failure this
# project has actually seen is cloudflared alive but not serving, which every
# process-level check reports as healthy.
#
#   --force   run the recovery path even if the site looks fine (for testing)

set -uo pipefail

HEALTH_URL="https://myra.vyybandasky.online/api/health"
REPO_WSL="/mnt/c/Users/DELL/dev/gyygs.ke"
COMPOSE_WIN='C:\Users\DELL\dev\gyygs.ke\infra\docker-compose.yml'
DOCKER="/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe"
DOCKER_DESKTOP="/mnt/c/Program Files/Docker/Docker/Docker Desktop.exe"
CMD="/mnt/c/Windows/System32/cmd.exe"
DOCKER_DESKTOP_WIN='C:\Program Files\Docker\Docker\Docker Desktop.exe'
LOG="$REPO_WSL/logs/watchdog.log"
TOPIC_FILE="$REPO_WSL/infra/.ntfy-topic"

FORCE=0
[ "${1:-}" = "--force" ] && FORCE=1

log() {
  mkdir -p "$(dirname "$LOG")"
  printf '%s  %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" >> "$LOG"
}

notify() {
  [ -f "$TOPIC_FILE" ] || return 0
  local topic; topic="$(tr -d '[:space:]' < "$TOPIC_FILE")"
  [ -n "$topic" ] || return 0
  curl -s -m 15 -H "Title: $1" -d "$2" "https://ntfy.sh/$topic" >/dev/null 2>&1 \
    || log "ntfy failed"
}

site_ok() {
  [ "$(curl -s -m 15 -o /dev/null -w '%{http_code}' "$HEALTH_URL" 2>/dev/null)" = "200" ]
}

engine_ok() {
  "$DOCKER" info --format '{{.ServerVersion}}' >/dev/null 2>&1
}

# 1. healthy? do nothing, quietly.
if site_ok && [ "$FORCE" -eq 0 ]; then
  exit 0
fi

log "site unhealthy — starting recovery"

# 2. Docker Desktop. Launched through WSL interop; it starts in the user's
#    Windows session, which is the only place a per-user GUI app can run.
if ! engine_ok; then
  if [ -f "$DOCKER_DESKTOP" ]; then
    # Hand the launch to the Windows shell. Exec'ing it straight from here
    # (nohup ... &) parents the GUI to the WSL process tree and Docker Desktop
    # comes up half-started: its own docker-desktop distro stays Stopped and the
    # engine never appears. Learned the hard way, 18 Aug 2026.
    log "engine down - starting Docker Desktop via the Windows shell"
    "$CMD" /c start "" "$DOCKER_DESKTOP_WIN" >/dev/null 2>&1       || log "cmd start returned non-zero"
  else
    log "Docker Desktop not found at $DOCKER_DESKTOP"
    notify "Myra is DOWN" "Docker Desktop is missing. Manual fix needed."
    exit 1
  fi
fi

# 3. wait for the engine — a cold start is not quick.
engine_up=0
for i in $(seq 1 36); do
  if engine_ok; then engine_up=1; log "engine up after ~$((i * 5))s"; break; fi
  sleep 5
done
if [ "$engine_up" -eq 0 ]; then
  log "engine did not come up within 180s"
  notify "Myra is DOWN" "Docker engine did not start within 3 minutes. Needs a look."
  exit 1
fi

# 4. containers. restart:unless-stopped usually handles this, but an explicit
#    up -d also covers one that was stopped by hand.
log "bringing the stack up"
"$DOCKER" compose -f "$COMPOSE_WIN" up -d 2>&1 | while IFS= read -r line; do
  log "  compose: $(echo "$line" | tr -d '\r')"
done

# 5. can a customer actually reach it again?
for i in $(seq 1 24); do
  if site_ok; then
    log "site healthy again after ~$((i * 5))s"
    notify "Myra recovered" "myra.vyybandasky.online was down and the watchdog brought it back."
    exit 0
  fi
  sleep 5
done

log "site still unhealthy after recovery attempt"
notify "Myra is DOWN" "The watchdog restarted everything and myra.vyybandasky.online is still unreachable."
exit 1
