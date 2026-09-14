# netcup-backup

A zero-downtime backup orchestrator for a Netcup RS 2000 G12. Creates online
SC snapshots via the netcup SCP REST API and pushes file-level encrypted
backups to Cloudflare R2 via [restic][restic] running on the source server.
Runs as a Docker container on a separate host — typically one managed by
[Coolify][coolify].

[restic]: https://restic.net/
[coolify]: https://coolify.io/

## Why

Netcup's snapshot export endpoint produces a downloadable disk image, but
only for **offline** snapshots — the server has to be off, and only the
first export per server is free. This service avoids both: it keeps a
single online (copy-on-write) snapshot inside the SCP for fast local
rollback, and uses `restic` to push incremental, encrypted, deduplicated
chunks to Cloudflare R2 for true offsite backup. The source server never
goes down.

## How it works

```
┌────────────────────────────┐                   ┌──────────────────────────┐
│  Orchestrator host         │   REST + OAuth2   │  netcup SCP API          │
│  netcup-backup container   │ ────────────────▶ │  online snapshots        │
│  (Python)                  │                   │  tasks / servers         │
│                            │                   └──────────────────────────┘
│   • scheduler              │
│   • /health endpoint       │   SSH + restic    ┌──────────────────────────┐
│   • retention control      │ ────────────────▶ │  RS 2000 G12             │
│                            │                   │  restic agent (systemd)  │
└────────────────────────────┘                   └────────────┬─────────────┘
            │                                                │ restic push
            │                                                ▼
            │                                  ┌──────────────────────────┐
            └─────────────── logs ───────────▶│  Cloudflare R2           │
                                               │  encrypted chunks        │
                                               └──────────────────────────┘
```

Two tiers:

| Tier | What | Where | Lifetime |
|---|---|---|---|
| Local rollback | Online (copy-on-write) snapshot in the SCP | Netcup host | `NETCUP_KEEP` (default 1) |
| Offsite backup | `restic` incremental backups | Cloudflare R2 | `R2_KEEP` (default 4) |

## Deployment

### Via Coolify

1. In Coolify, create a new **Docker Compose** resource.
2. Paste the contents of `docker-compose.yml`.
3. Fill in the required environment variables in the UI (see [Configuration](#configuration)).
4. Deploy. The service self-bootstraps the `restic` agent on the RS 2000 over SSH on first run.

### Manually

```bash
cp .env.example .env
# fill in required vars (see Configuration below)
docker compose up -d
```

## Prerequisites

- A Netcup RS 2000 G12 (or any KVM-based root server with REST API access).
- The orchestrator host must be reachable from the RS 2000 over SSH.
- A [Cloudflare R2][r2] bucket and an access key with **Object Read & Write**.
- An SSH keypair; the public half is added to `~/.ssh/authorized_keys` on the RS 2000.

[r2]: https://developers.cloudflare.com/r2/

## Onboarding a fresh RS 2000 G12

1. Activate the server. Find the **server ID** at the end of any SCP URL for it.
2. **CCP → API**: enable the REST API and whitelist the orchestrator host's IPv4.
3. **One-time device-code flow** on any machine with a browser:
   ```bash
   bash scripts/reauth-netcup.sh
   ```
   Copy the printed refresh token into `NETCUP_REFRESH_TOKEN`.
4. `ssh-keygen -t ed25519`, then add the public key to the RS 2000's `~/.ssh/authorized_keys`. Paste the private key (PEM) into `SSH_PRIVATE_KEY`.
5. Create an R2 bucket and an access key. Run `restic init -r s3:<account>.r2.cloudflarestorage.com/<bucket>` once and capture the password into `RESTIC_PASSWORD`.
6. Deploy (above). Watch logs for `agent deployed` followed by `snapshot created` on the first run.

## Configuration

### Required

| Var | Purpose |
|---|---|
| `NETCUP_REFRESH_TOKEN` | Long-lived OAuth2 refresh token (offline_access). Must be used at least once every 30 days or it expires. |
| `NETCUP_SERVER_ID` | The RS 2000's ID, from the SCP URL. |
| `SSH_HOST` | Hostname or IP of the RS 2000. |
| `SSH_PRIVATE_KEY` | PEM-encoded private key for the user above. |
| `RESTIC_REPOSITORY` | e.g. `s3:<account>.r2.cloudflarestorage.com/<bucket>`. |
| `RESTIC_PASSWORD` | Restic repo password (from `restic init`). |
| `R2_ACCESS_KEY_ID` | R2 access key with Object Read & Write. |
| `R2_SECRET_ACCESS_KEY` | R2 secret. |

### Optional

| Var | Default | Effect |
|---|---|---|
| `NETCUP_KEEP` | `1` | Number of online snapshots kept in the SCP (free tier). |
| `R2_KEEP` | `4` | Number of restic snapshots kept in R2 (`forget --keep-last`). |
| `BACKUP_CRON` | `0 3 * * *` | When to take an online SCP snapshot (UTC). |
| `RESTIC_CRON` | `30 3 * * *` | When restic pushes to R2 (UTC). |
| `PRUNE_CRON` | `0 4 * * 0` | When to run `restic forget --prune`. |
| `RESTIC_PATHS` | `/` | Comma-separated paths to back up on the RS 2000. |
| `RESTIC_EXCLUDE` | `/tmp,/proc,/sys,/run,/var/cache` | Comma-separated paths to exclude. |
| `SSH_USER` | `root` | SSH user on the RS 2000. |
| `SSH_PORT` | `22` | SSH port. |
| `AWS_DEFAULT_REGION` | `auto` | R2 quirk — leave as `auto`. |
| `HEALTH_PORT` | `8080` | Internal `/health` endpoint. |
| `LOG_LEVEL` | `INFO` | Standard Python log levels. |
| `TZ` | `UTC` | Container timezone (affects cron). |

The full list with comments is in `.env.example`.

## Local development

```bash
uv sync --all-extras
uv run ruff check src tests
uv run ruff format src tests
uv run pytest
uv run python -m netcup_backup
```

See `AGENTS.md` for the conventions used by AI assistants working on this
codebase.

## Acknowledgements

The netcup REST client follows the same shape as
[`pavelpikta/netcup-scp-cli`](https://github.com/pavelpikta/netcup-scp-cli)
and the snapshot lifecycle mirrors
[`k-it-ai/netcup-snapshot`](https://github.com/k-it-ai/netcup-snapshot),
extended for Cloudflare R2 offsite push instead of SCP-local retention.

## License

MIT
