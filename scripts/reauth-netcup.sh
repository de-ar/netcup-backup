#!/usr/bin/env bash
set -euo pipefail

REALM=scp
CLIENT=scp
BASE=https://www.servercontrolpanel.de

read -r -p "Enter netcup customer number (Keycloak username): " KUNDE
read -r -s -p "Enter SCP password: " PASS; echo

echo
echo "Requesting token via password grant..."

RAW=$(curl -fsS -X POST \
    "${BASE}/realms/${REALM}/protocol/openid-connect/token" \
    -d "client_id=${CLIENT}" \
    -d "grant_type=password" \
    -d "username=${KUNDE}" \
    -d "password=${PASS}" \
    -d "scope=offline_access openid")

ACCESS=$(echo "$RAW" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("access_token",""))')
REFRESH=$(echo "$RAW" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("refresh_token",""))')

if [[ -z "$REFRESH" ]]; then
    echo "no refresh_token in response — password grant may be disabled" >&2
    echo "$RAW" >&2
    echo >&2
    echo "use the device-code flow instead:" >&2
    echo "  curl -X POST '${BASE}/realms/${REALM}/protocol/openid-connect/auth/device' \\" >&2
    echo "    -d 'client_id=${CLIENT}' -d 'scope=offline_access openid'" >&2
    exit 1
fi

echo
echo "token received, keeping refresh_token only"
echo "store this as NETCUP_REFRESH_TOKEN in your .env:"
echo
echo "$REFRESH"
echo

read -r -p "write to .env now? [y/N] " WRITE
if [[ "$WRITE" =~ ^[Yy]$ ]]; then
    ENV_FILE="${ENV_FILE:-.env}"
    if [[ -f "$ENV_FILE" ]]; then
        if grep -q '^NETCUP_REFRESH_TOKEN=' "$ENV_FILE"; then
            python3 - "$ENV_FILE" "$REFRESH" <<'PY'
import sys, pathlib
path, token = sys.argv[1], sys.argv[2]
lines = pathlib.Path(path).read_text().splitlines()
out, replaced = [], False
for line in lines:
    if line.startswith("NETCUP_REFRESH_TOKEN="):
        out.append(f"NETCUP_REFRESH_TOKEN={token}")
        replaced = True
    else:
        out.append(line)
if not replaced:
    if out and out[-1].strip():
        out.append("")
    out.append(f"NETCUP_REFRESH_TOKEN={token}")
pathlib.Path(path).write_text("\n".join(out) + "\n")
PY
        fi
    else
        printf "NETCUP_REFRESH_TOKEN=%s\n" "$REFRESH" > "$ENV_FILE"
    fi
    chmod 600 "$ENV_FILE"
    echo "wrote $ENV_FILE"
fi
