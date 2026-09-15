from __future__ import annotations

import argparse
import logging
import signal
import sys
import time

from .config import Config
from .http_server import HealthState, Listener, build_server, serve_forever
from .logging_setup import configure
from .scheduler import Orchestrator, build_scheduler

log = logging.getLogger(__name__)

DISPATCH = ("snapshot", "backup", "prune")


def main() -> None:
    args = _parse_args()
    if args.action is None:
        args.action = "serve"
    config = Config()
    configure(config.log_level)
    state = HealthState()
    state.started_at = time.time()
    orch = Orchestrator(config)

    if args.action == "deploy":
        orch.deploy_agent()
        state.deployed = True
        return

    if args.action == "now":
        orch.deploy_agent()
        state.deployed = True
        _dispatch_now(orch, args.job)
        return

    if args.action == "restore":
        orch.deploy_agent()
        state.deployed = True
        orch.run_restore(target=args.target, snapshot=args.snapshot, include=args.include)
        return

    if args.action == "serve":
        orch.deploy_agent()
        state.deployed = True
        scheduler = build_scheduler(orch, config)
        scheduler.start()
        log.info(
            "scheduler up: snapshot=%s, backup=%s, prune=%s",
            config.backup_cron,
            config.restic_cron,
            config.prune_cron,
        )
        _install_signal_handlers(scheduler)
        listener = Listener(host=config.health_host, port=config.health_port)
        server = build_server(state, listener)
        log.info("health endpoint on %s:%d", listener.host, listener.port)
        try:
            serve_forever(server)
        finally:
            scheduler.shutdown(wait=False)
        return

    raise SystemExit(f"unknown action: {args.action}")


def _dispatch_now(orch: Orchestrator, job: str) -> None:
    actions = {
        "snapshot": orch.snapshot_and_rotate,
        "backup": orch.run_agent_backup,
        "prune": orch.run_prune,
    }
    fn = actions.get(job)
    if fn is None:
        raise SystemExit(f"unknown job: {job}; choices: {sorted(actions)}")
    fn()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="netcup-backup")
    parser.set_defaults(action="serve")
    sub = parser.add_subparsers(dest="action")

    sub.add_parser("serve", help="run scheduler + health endpoint (default)")
    sub.add_parser("deploy", help="bootstrap restic agent on the RS 2000 and exit")

    now = sub.add_parser("now", help="run one job synchronously and exit")
    now.add_argument("job", choices=DISPATCH, help="which job to run")

    restore = sub.add_parser(
        "restore", help="restore a snapshot to a scratch path on the server (not scheduled)"
    )
    restore.add_argument("--target", required=True, help="remote path to restore into")
    restore.add_argument("--snapshot", default="latest", help="restic snapshot id (default: latest)")
    restore.add_argument(
        "--include",
        action="append",
        default=None,
        help="restrict restore to this path (repeatable)",
    )

    return parser.parse_args()


def _install_signal_handlers(scheduler) -> None:
    def _stop(*_):
        log.info("shutting down")
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)


def cli() -> None:
    main()


if __name__ == "__main__":
    cli()
