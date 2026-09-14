from __future__ import annotations

import logging
import posixpath

from ..config import Config
from .ssh import SshClient, Upload

log = logging.getLogger(__name__)

CONFIG_DIR = "/etc/netcup-backup"
PATHS_FILE = posixpath.join(CONFIG_DIR, "paths.conf")
EXCLUDE_FILE = posixpath.join(CONFIG_DIR, "exclude.conf")
ENV_FILE = posixpath.join(CONFIG_DIR, "restic.env")


class DeployResult:
    def __init__(self, restic_installed: bool, timer_started: bool) -> None:
        self.restic_installed = restic_installed
        self.timer_started = timer_started

    @property
    def ok(self) -> bool:
        return self.restic_installed and self.timer_started


def deploy(client: SshClient, config: Config) -> DeployResult:
    _ensure_dirs(client)
    client.put(Upload(data=_lines(config.restic_env_lines), remote_path=ENV_FILE, mode=0o600))
    client.put(Upload(data=_lines(config.backup_paths), remote_path=PATHS_FILE, mode=0o644))
    client.put(Upload(data=_lines(config.exclude_paths), remote_path=EXCLUDE_FILE, mode=0o644))
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


def _push_bootstrap(client: SshClient) -> None:
    from importlib import resources

    text = resources.files("netcup_backup").joinpath("bootstrap-agent.sh").read_text()
    target = "/tmp/netcup-bootstrap-agent.sh"
    client.put(Upload(data=text, remote_path=target, mode=0o755))


def _lines(items: list[str]) -> str:
    return "\n".join(items) + "\n"
