from __future__ import annotations

import logging
import shlex

from ..config import Config
from .restic import ResticCommand
from .restic import run as run_restic
from .ssh import CommandResult, SshClient

log = logging.getLogger(__name__)


def restore(
    ssh: SshClient,
    config: Config,
    *,
    target: str,
    snapshot: str = "latest",
    include: list[str] | None = None,
) -> CommandResult:
    parts = [f"restore {shlex.quote(snapshot)} --target {shlex.quote(target)}"]
    for path in include or []:
        parts.append(f"--include {shlex.quote(path)}")
    spec = ResticCommand(
        repository=config.restic_repository,
        subcommand=" ".join(parts),
        timeout=3600,
    )
    res = run_restic(ssh, spec)
    if not res.ok:
        log.error("restore failed: %s", res.stderr.strip())
    return res
