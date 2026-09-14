from __future__ import annotations

import logging
import posixpath
from dataclasses import dataclass

from ..config import Config
from .ssh import SshClient

log = logging.getLogger(__name__)

CONFIG_DIR = "/etc/netcup-backup"
PATHS_FILE = posixpath.join(CONFIG_DIR, "paths.conf")
EXCLUDE_FILE = posixpath.join(CONFIG_DIR, "exclude.conf")
ENV_FILE = posixpath.join(CONFIG_DIR, "restic.env")


@dataclass
class DeployResult:
    restic_installed: bool
    timer_started: bool

    @property
    def ok(self) -> bool:
        return self.restic_installed and self.timer_started


def deploy(client: SshClient, config: Config) -> DeployResult:
    _ensure_dirs(client)
    _upload_restic_env(client, config)
    _upload_paths(client, config)
    _upload_excludes(client, config)
    _push_bootstrap(client)
    boot = client.run("bash /tmp/netcup-bootstrap-agent.sh")
    if not boot.ok:
        log.error("bootstrap failed: %s", boot.stderr.strip() or boot.stdout.strip())
        return DeployResult(restic_installed=False, timer_started=False)
    restic = client.run("command -v restic")
    timer = client.run("systemctl is-enabled netcup-backup.timer")
    return DeployResult(
        restic_installed=bool(restic.ok and restic.stdout.strip()),
        timer_started=bool(timer.ok and "enabled" in timer.stdout),
    )


def _ensure_dirs(client: SshClient) -> None:
    res = client.run(f"install -d -m 0700 {CONFIG_DIR} /tmp")
    if not res.ok:
        raise RuntimeError(f"mkdir failed: {res.stderr}")


def _upload_restic_env(client: SshClient, config: Config) -> None:
    payload = "\n".join(config.restic_env_lines) + "\n"
    client.put(payload, ENV_FILE, mode=0o600)


def _upload_paths(client: SshClient, config: Config) -> None:
    payload = "\n".join(config.backup_paths) + "\n"
    client.put(payload, PATHS_FILE, mode=0o644)


def _upload_excludes(client: SshClient, config: Config) -> None:
    payload = "\n".join(config.exclude_paths) + "\n"
    client.put(payload, EXCLUDE_FILE, mode=0o644)


def _push_bootstrap(client: SshClient) -> None:
    from importlib import resources

    text = resources.files("netcup_backup").joinpath("bootstrap-agent.sh").read_text()
    target = "/tmp/netcup-bootstrap-agent.sh"
    client.put(text, target, mode=0o755)
