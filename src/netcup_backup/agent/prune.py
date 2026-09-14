from __future__ import annotations

import logging
import shlex

from ..config import Config
from .ssh import CommandResult, SshClient

log = logging.getLogger(__name__)


def forget_and_prune(ssh: SshClient, config: Config) -> CommandResult:
    repo = shlex.quote(config.restic_repository)
    keep = config.r2_keep
    cmd = (
        f"set -a; source /etc/netcup-backup/restic.env; set +a; "
        f"restic -r {repo} forget --keep-last {keep} --prune"
    )
    res = ssh.run(cmd, timeout=3600)
    if not res.ok:
        log.error("prune failed: %s", res.stderr.strip())
    return res
