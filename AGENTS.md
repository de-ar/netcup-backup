# netcup-backup

A zero-downtime backup orchestrator for a Netcup RS 2000 G12. Drives online
SC snapshots via the SCP REST API and file-level encrypted backups to
Cloudflare R2 via `restic` running on the source server. Runs as a Docker
container on a separate Coolify-managed host.

## Intent

- **Snapshot tier**: online (copy-on-write) snapshots inside the netcup SCP,
  kept by `NETCUP_KEEP` (default 1, the free tier). Instant local rollback.
- **Offsite tier**: `restic` backups on the RS 2000, pushing encrypted chunks
  to Cloudflare R2 (`s3:` backend). True offsite, survives host failure.
- **Orchestrator**: a Python container that owns the schedule, drives the
  netcup OAuth2 client, ssh's into the RS 2000 for agent bootstrap and
  retention, exposes a `/health` endpoint.

Do **not** try to export snapshots to R2 in this repo. Netcup snapshot
export needs the server offline and a paid export slot; the no-downtime
constraint rules it out.

## Layout

- `src/netcup_backup/netcup/` — OAuth2 + REST client, one module per resource.
- `src/netcup_backup/agent/` — SSH client + restic deploy/backup/prune/status.
- `src/netcup_backup/scheduler.py` — APScheduler wiring of the three jobs.
- `src/netcup_backup/http_server.py` — `/health` HTTP endpoint for Coolify.
- `scripts/bootstrap-agent.sh` — installs restic + systemd timer on the
  RS 2000 (pushed over SSH by `agent/deploy.py`).
- `scripts/reauth-netcup.sh` — walks through the OAuth2 device-code flow to
  (re)generate a long-lived `NETCUP_REFRESH_TOKEN`.
- `docker-compose.yml` — Coolify service template (metadata header + service).
- `svgs/netcup-backup.svg` — Coolify catalog logo.
- `.env.example` — every supported env var with its default and meaning.
- `tests/` — pytest; mock the netcup API and the SSH transport.

## Commands

`uv` is configured via `pyproject.toml`.

| Action | Command |
|---|---|
| Install deps + venv | `uv sync --all-extras` |
| Lint | `uv run ruff check src tests` |
| Format | `uv run ruff format src tests` |
| Test | `uv run pytest` |
| Build image | `docker build -t netcup-backup:0.1.0 .` |
| Validate Coolify template | `docker compose -f docker-compose.yml config -q` |
| Deploy locally (Docker Compose Empty) | `docker compose up -d` |
| Deploy via Coolify | paste `docker-compose.yml` into a Docker Compose resource |

Lint + format + test run on every CI push; no manual step required.

## Coolify service template

`docker-compose.yml` is shaped as a Coolify one-click service template:

- **Metadata header** (`# documentation:`, `# slogan:`, `# category:`,
  `# tags:`, `# logo:`, `# port:`) — required by Coolify's catalog. Keep it at
  the top of the file and keep the `port:` matching the exposed health port.
- **Env var pattern**: `${VAR:?}` = required (deploy fails if unset);
  `${VAR:-default}` = optional with default; `${VAR:?default}` = required with
  default (deploy fails only if empty). New required config goes through the
  pydantic `Config` validator — add the field there first, then mark `:?` here.
- **No `env_file:`**, no `container_name:`, no `ports:` mapping. Coolify hands
  the env in via its UI and proxies the `port:` automatically. Don't re-add
  them — they conflict with multi-deploy and with Coolify's port detection.
- **No persistent volume**. Restic state lives in R2; the orchestrator is
  stateless. Don't add a `${COOLIFY_VOLUME_*}` unless you also persist state.
- **Logo** must be an SVG at `svgs/netcup-backup.svg`; the path in the metadata
  header must match exactly. 1k+ GitHub stars required before Coolify accepts
  the PR into its catalog (currently a blocker for this repo).
- The `image:` tag is pinned to the `pyproject.toml` version. Bump both
  together when shipping a release.

## Critical netcup facts

Read these before changing anything in `netcup/`. They are not obvious from
the endpoint names and will burn you otherwise.

- **API base**: `https://www.servercontrolpanel.de/scp-core/api/v1`
- **Auth**: OAuth2 over Keycloak, realm `scp`, client `scp`.
  - Refresh flow: `POST /realms/scp/protocol/openid-connect/token` with
    `grant_type=refresh_token`, `client_id=scp`, `refresh_token=<…>`.
  - Access-token lifetime: 300 s. Refresh-token lifetime: 30 days of no use.
    Re-auth via `scripts/reauth-netcup.sh` if it expires.
- **Case-sensitive API** — only lowercase. `"Running"` or `"OFF"` fails.
- **PATCH on `/servers/{id}`** requires `Content-Type:
  application/merge-patch+json` (not `application/json`). One attribute per
  PATCH request.
- **Snapshot dryrun** is a separate endpoint; call it before `create` to
  avoid 4xx races. Then poll `/api/v1/tasks/{id}` until done.
- **Snapshot export is intentionally NOT implemented** — needs the server
  offline and a paid export slot. Don't add it.

## Critical R2 / restic facts

- Cloudflare R2 is S3-compatible. Configure restic with
  `RESTIC_REPOSITORY=s3:<accountid>.r2.cloudflarestorage.com/<bucket>` and
  the R2 access keys. `AWS_DEFAULT_REGION=auto` (R2 quirk — no real region).
- Restic deduplicates, encrypts (AES-256), and supports `forget --keep-last`.
  Pruning is a separate `--prune` step that can be expensive.
- Restic's repo password (`RESTIC_PASSWORD`) is required to read or prune.
  Generate once with `restic init`, store via env or `RESTIC_PASSWORD_FILE`.
- Don't run `restic backup` and `restic forget --prune` concurrently against
  the same repo; the scheduler offsets them by default.

## Style conventions

- Two-arg hard limit on every method. `Config.from_env(...)` etc. count as
  one arg.
- Don't extract classes/protocols until the third repetition (WET).
- One module per resource, mirror `pavelpikta/netcup-scp-cli` naming where
  possible so that upstream Python tool stays a reference.
- All env-driven config validated by `pydantic-settings` at startup — fail
  fast on missing/invalid values.
- **No comments in code** unless explicitly asked. Self-documenting names.

## Setup onboarding for a fresh RS 2000 G12

1. Buy + activate netcup RS 2000 G12. Note the server ID from the SCP URL.
2. CCP → API → enable REST API; whitelist the orchestrator host's IPv4.
3. One-time device-code flow on the orchestrator host (anywhere with a
   browser): run `scripts/reauth-netcup.sh`. It puts the refresh token in
   `.env` (do not commit).
4. Generate an SSH key (`ssh-keygen`), add the public key to
   `~/.ssh/authorized_keys` on the RS 2000. Store the private key in
   `SSH_PRIVATE_KEY` in `.env` (PEM, escaped newlines if needed).
5. Create an R2 bucket and an access key with `Object Read & Write` on it.
   Run `restic init -r s3:...` once locally and capture the password.
6. Deploy via Coolify: paste `docker-compose.yml` into a Docker Compose
   resource and fill the required env vars in the UI (no `.env` needed there).
   For local testing instead, run `docker compose up -d`.
7. Watch logs for `"agent deployed"` and `"snapshot created"` on first run.

## Where to look

- Netcup endpoint change → `src/netcup_backup/netcup/`.
- Schedule change → `src/netcup_backup/scheduler.py` and the three cron
  env vars in `.env.example`.
- What is backed up or pruned → `agent/backup.py` and `agent/prune.py`;
  persistent config on the RS 2000 lives under `/etc/netcup-backup/`.
- New notification sink → `http_server.py` is the place. Keep it tiny, no
  notifiers in the core path.

## Forbidden patterns

- Exporting a snapshot to R2 (offline-only at netcup).
- Hardcoding `state` values in upper case.
- PATCH with multiple attributes in one body.
- Mutating RS 2000 state from the orchestrator except via `agent/deploy.py`
  and the restic command wrappers — never `ssh root@… apt install` outside
  `agent/deploy.py`.
- Storing R2 credentials or SSH private keys in the image. Always env or
  mounted file.
- Adding new cron schedules outside the three env vars (`BACKUP_CRON`,
  `RESTIC_CRON`, `PRUNE_CRON`).
