from __future__ import annotations

import json
import logging
import shlex

from ..config import Config
from .ssh import CommandResult, SshClient

log = logging.getLogger(__name__)


def restic_snapshots(ssh: SshClient, config: Config) -> CommandResult:
    repo = shlex.quote(config.restic_repository)
    cmd = f"set -a; source /etc/netcup-backup/restic.env; set +a; restic -r {repo} snapshots --json"
    return ssh.run(cmd, timeout=120)


def restic_stats(ssh: SshClient, config: Config) -> CommandResult:
    repo = shlex.quote(config.restic_repository)
    cmd = f"set -a; source /etc/netcup-backup/restic.env; set +a; restic -r {repo} stats --json"
    return ssh.run(cmd, timeout=120)


def last_backup_summary(ssh: SshClient) -> dict | None:
    cmd = (
        "journalctl -u netcup-backup.service -n 1 -o json --no-pager "
        "| python3 -c 'import json,sys; d=json.loads(sys.stdin.read()); "
        'print(json.dumps({"ts": d.get("__REALTIME_TIMESTAMP"), '
        '"msg": d.get("MESSAGE")}))\''
    )
    res = ssh.run(cmd, timeout=30)
    if not res.ok:
        return None
    try:
        return json.loads(res.stdout.strip())
    except json.JSONDecodeError:
        return None
