from __future__ import annotations

import shlex
from dataclasses import dataclass

from .ssh import CommandResult, SshClient

ENV_SOURCE = "set -a; source /etc/netcup-backup/restic.env; set +a"


@dataclass(frozen=True)
class ResticCommand:
    repository: str
    subcommand: str
    timeout: int = 120


def run(ssh: SshClient, command: ResticCommand) -> CommandResult:
    repo = shlex.quote(command.repository)
    full = f"{ENV_SOURCE}; restic -r {repo} {command.subcommand}"
    return ssh.run(full, timeout=command.timeout)
