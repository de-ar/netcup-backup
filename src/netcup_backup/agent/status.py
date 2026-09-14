from __future__ import annotations

import json
import logging

from ..config import Config
from .restic import ResticCommand
from .restic import run as run_restic
from .ssh import CommandResult, SshClient

log = logging.getLogger(__name__)


def restic_snapshots(ssh: SshClient, config: Config) -> CommandResult:
    return run_restic(
        ssh,
        ResticCommand(
            repository=config.restic_repository,
            subcommand="snapshots --json",
        ),
    )


def restic_stats(ssh: SshClient, config: Config) -> CommandResult:
    return run_restic(
        ssh,
        ResticCommand(
            repository=config.restic_repository,
            subcommand="stats --json",
        ),
    )


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
