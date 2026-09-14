from __future__ import annotations

import logging

from ..config import Config
from .restic import ResticCommand
from .restic import run as run_restic
from .ssh import CommandResult, SshClient

log = logging.getLogger(__name__)


def forget_and_prune(ssh: SshClient, config: Config) -> CommandResult:
    spec = ResticCommand(
        repository=config.restic_repository,
        subcommand=f"forget --keep-last {config.r2_keep} --prune",
        timeout=3600,
    )
    res = run_restic(ssh, spec)
    if not res.ok:
        log.error("prune failed: %s", res.stderr.strip())
    return res
