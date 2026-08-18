#!/usr/bin/env bash
# Installs the Myra watchdog as a systemd --user timer inside WSL.
# Idempotent — safe to re-run. Unit files are machine-local (~/.config), matching
# how VOS III's services are managed on this box.
set -euo pipefail

UNIT_DIR="$HOME/.config/systemd/user"
SCRIPT="/mnt/c/Users/DELL/dev/gyygs.ke/infra/watchdog.sh"

[ -f "$SCRIPT" ] || { echo "watchdog.sh not found at $SCRIPT" >&2; exit 1; }
chmod +x "$SCRIPT"
mkdir -p "$UNIT_DIR"

cat > "$UNIT_DIR/myra-watchdog.service" <<UNIT
[Unit]
Description=Myra site watchdog (checks myra.vyybandasky.online end to end)
After=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/bin/env bash $SCRIPT
UNIT

cat > "$UNIT_DIR/myra-watchdog.timer" <<UNIT
[Unit]
Description=Run the Myra site watchdog every 5 minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=5min
AccuracySec=30s
Persistent=true

[Install]
WantedBy=timers.target
UNIT

systemctl --user daemon-reload
systemctl --user enable --now myra-watchdog.timer

echo "installed. next runs:"
systemctl --user list-timers myra-watchdog.timer --no-pager
