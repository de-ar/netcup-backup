from __future__ import annotations

import logging

from .ssh import CommandResult, SshClient

log = logging.getLogger(__name__)


def run_backup(ssh: SshClient, *, timeout: int = 3600) -> CommandResult:
    res = ssh.run(
        "systemctl start netcup-backup.service && "
        "journalctl -u netcup-backup.service -n 200 --no-pager",
        timeout=timeout,
    )
    if not res.ok:
        log.error("backup run failed: %s", res.stderr.strip())
    return res
