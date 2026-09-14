#!/usr/bin/env bash
set -euo pipefail

CONFIG_DIR=/etc/netcup-backup
BACKUP_SCRIPT=/usr/local/sbin/netcup-backup.sh
SERVICE_FILE=/etc/systemd/system/netcup-backup.service
TIMER_FILE=/etc/systemd/system/netcup-backup.timer

if [[ $EUID -ne 0 ]]; then
    echo "must run as root" >&2
    exit 1
fi

detect_pkg() {
    if command -v apt-get >/dev/null 2>&1; then
        echo apt
    elif command -v dnf >/dev/null 2>&1; then
        echo dnf
    elif command -v yum >/dev/null 2>&1; then
        echo yum
    elif command -v apk >/dev/null 2>&1; then
        echo apk
    else
        echo unknown >&2
        exit 1
    fi
}

install_restic() {
    local mgr
    mgr=$(detect_pkg)
    case "$mgr" in
        apt)
            apt-get update -y
            DEBIAN_FRONTEND=noninteractive apt-get install -y restic
            ;;
        dnf|yum)
            "$mgr" install -y restic
            ;;
        apk)
            apk add --no-cache restic bash
            ;;
    esac
}

command -v restic >/dev/null 2>&1 || install_restic
mkdir -p "$CONFIG_DIR"
chmod 700 "$CONFIG_DIR"

if [[ ! -f "$CONFIG_DIR/restic.env" ]]; then
    echo "restic.env missing — populate it before enabling the timer" >&2
    exit 1
fi
chmod 600 "$CONFIG_DIR/restic.env"

if [[ ! -f "$CONFIG_DIR/paths.conf" ]]; then
    echo "paths.conf missing — populate it before enabling the timer" >&2
    exit 1
fi
chmod 644 "$CONFIG_DIR/paths.conf"

if [[ ! -x "$BACKUP_SCRIPT" ]]; then
    cat >"$BACKUP_SCRIPT" <<'SCRIPT'
#!/usr/bin/env bash
set -euo pipefail
set -a
# shellcheck disable=SC1091
source /etc/netcup-backup/restic.env
set +a

mapfile -t PATHS < /etc/netcup-backup/paths.conf
mapfile -t EXCLUDE_FILE < /etc/netcup-backup/exclude.conf 2>/dev/null || true

RESTIC_ARGS=(--tag netcup-backup)
if [[ -s /etc/netcup-backup/exclude.conf ]]; then
    RESTIC_ARGS+=(--exclude-file=/etc/netcup-backup/exclude.conf)
fi

exec /usr/bin/restic backup "${RESTIC_ARGS[@]}" "${PATHS[@]}"
SCRIPT
    chmod 755 "$BACKUP_SCRIPT"
fi

if [[ ! -f "$SERVICE_FILE" ]]; then
    cat >"$SERVICE_FILE" <<'UNIT'
[Unit]
Description=netcup-backup restic push to R2
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
EnvironmentFile=/etc/netcup-backup/restic.env
ExecStart=/usr/local/sbin/netcup-backup.sh
Nice=10
IOSchedulingClass=best-effort
IOSchedulingPriority=7
SuccessExitStatus=0 3
UNIT
fi

if [[ ! -f "$TIMER_FILE" ]]; then
    cat >"$TIMER_FILE" <<'UNIT'
[Unit]
Description=netcup-backup schedule

[Timer]
OnCalendar=*-*-* 03:30:00
Persistent=true
AccuracySec=60s
Unit=netcup-backup.service

[Install]
WantedBy=timers.target
UNIT
fi

systemctl daemon-reload
systemctl enable --now netcup-backup.timer
systemctl restart netcup-backup.timer

echo "netcup-backup agent installed"
echo "  config:   $CONFIG_DIR"
echo "  script:   $BACKUP_SCRIPT"
echo "  service:  $SERVICE_FILE"
echo "  timer:    $TIMER_FILE"
echo "next runs:"
systemctl list-timers --no-pager netcup-backup.timer || true
