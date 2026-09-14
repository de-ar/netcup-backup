from __future__ import annotations

import logging
from collections.abc import Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from .agent import backup as agent_backup
from .agent import deploy as agent_deploy
from .agent import prune as agent_prune
from .agent.ssh import SshClient
from .config import Config
from .netcup import snapshots as scp_snapshots
from .netcup.client import ScpClient

log = logging.getLogger(__name__)


class Orchestrator:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._scp = ScpClient(_auth_for(config))
        self._snapshots = scp_snapshots.Snapshots(self._scp, config.netcup_server_id)
        self._ssh = SshClient(
            config.ssh_host,
            port=config.ssh_port,
            user=config.ssh_user,
            private_key_pem=config.ssh_private_key,
            host_keys_pem=config.ssh_host_keys,
        )

    def snapshot_and_rotate(self) -> str:
        name = scp_snapshots.now_snapshot_name(prefix="auto")
        log.info("creating online snapshot %s", name)
        task_id = self._snapshots.create_and_wait(name)
        deleted = self._snapshots.prune_to(self._config.netcup_keep)
        log.info("snapshot %s created (task %s), pruned %d", name, task_id or "n/a", deleted)
        return name

    def run_agent_backup(self) -> None:
        result = agent_backup.run_backup(self._ssh)
        if not result.ok:
            log.warning("agent backup returned %d", result.exit_code)

    def run_prune(self) -> None:
        result = agent_prune.forget_and_prune(self._ssh, self._config)
        if not result.ok:
            log.warning("prune returned %d", result.exit_code)

    def deploy_agent(self) -> None:
        result = agent_deploy.deploy(self._ssh, self._config)
        if not result.ok:
            raise RuntimeError(f"agent deploy failed: {result}")
        log.info(
            "agent deployed (restic=%s, timer=%s)", result.restic_installed, result.timer_started
        )


def _auth_for(config: Config):
    from .netcup.auth import Auth

    return Auth(config.netcup_refresh_token)


def build_scheduler(orch: Orchestrator, config: Config) -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=_resolve_tz())

    scheduler.add_job(
        orch.snapshot_and_rotate,
        CronTrigger.from_crontab(config.backup_cron),
        id="snapshot",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=900,
    )
    scheduler.add_job(
        orch.run_agent_backup,
        CronTrigger.from_crontab(config.restic_cron),
        id="agent_backup",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        orch.run_prune,
        CronTrigger.from_crontab(config.prune_cron),
        id="prune",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=86400,
    )
    return scheduler


def _resolve_tz() -> str | None:
    import os

    tz = os.environ.get("TZ")
    return tz or None


def run_now(orch: Orchestrator, action: str) -> None:
    actions: dict[str, Callable[[], object]] = {
        "snapshot": orch.snapshot_and_rotate,
        "backup": orch.run_agent_backup,
        "prune": orch.run_prune,
        "deploy": orch.deploy_agent,
    }
    fn = actions.get(action)
    if fn is None:
        raise SystemExit(f"unknown action: {action}; choices: {sorted(actions)}")
    fn()
