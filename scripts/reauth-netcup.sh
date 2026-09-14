#!/usr/bin/env bash
set -euo pipefail

REALM=scp
CLIENT=scp
BASE=https://www.servercontrolpanel.de

read -r -p "Enter netcup customer number (Keycloak username): " KUNDE
read -r -s -p "Enter SCP password: " PASS; echo

echo
echo "Requesting token via password grant..."

RAW=$(curl -sS -X POST \
    "${BASE}/realms/${REALM}/protocol/openid-connect/token" \
    -d "client_id=${CLIENT}" \
    -d "grant_type=password" \
    -d "username=${KUNDE}" \
    -d "password=${PASS}" \
    -d "scope=offline_access openid")

REFRESH=$(printf '%s' "$RAW" | python3 -c '
import json, sys
try:
    print(json.load(sys.stdin).get("refresh_token", ""))
except Exception:
    pass
')

if [[ -z "$REFRESH" ]]; then
    echo
    echo "Password grant did not return a refresh_token."
    echo "Server response (first 400 chars):"
    printf '%s' "$RAW" | head -c 400
    echo
    echo
    echo "Most likely: netcup disabled direct password grants on your realm."
    echo "Falling back to OAuth2 device-code flow (requires a browser once)."
    echo
    REFRESH=$(python3 <<'PY'
import json, sys, time, urllib.request, urllib.error, urllib.parse

BASE = "https://www.servercontrolpanel.de"
REALM = "scp"
CLIENT = "scp"


def post(path, form):
    data = urllib.parse.urlencode(form).encode()
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read().decode(), None
    except urllib.error.HTTPError as e:
        return e.read().decode(), e.code


print("requesting device code...")
body, status = post("/realms/scp/protocol/openid-connect/auth/device", {
    "client_id": CLIENT,
    "scope": "offline_access openid",
})
try:
    device = json.loads(body)
except Exception:
    raise SystemExit(f"device-code request failed (HTTP {status}): {body[:400]}")

if "error" in device:
    raise SystemExit(f"device-code request returned error: {device}")

verify_complete = device.get("verification_uri_complete")
verify_uri = device["verification_uri"]
user_code = device.get("user_code", "")

print()
if verify_complete:
    print(f"  1) open this URL in any browser, log in, and confirm:")
    print(f"     {verify_complete}")
else:
    print(f"  1) open {verify_uri} and enter code: {user_code}")
print(f"     (login will ask for your password and TOTP code if enabled)")
print()
print("  2) waiting for you to authorize (Ctrl-C to abort)...")

try:
    import webbrowser
    webbrowser.open(verify_complete or verify_uri)
except Exception:
    pass

poll = int(device.get("interval", 5))
expires_in = int(device.get("expires_in", 300))
deadline = time.time() + expires_in
last_heartbeat = 0.0

while time.time() < deadline:
    time.sleep(poll)
    body, status = post("/realms/scp/protocol/openid-connect/token", {
        "client_id": CLIENT,
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        "device_code": device["device_code"],
    })
    try:
        tok = json.loads(body)
    except Exception:
        raise SystemExit(f"token poll failed (HTTP {status}): {body[:400]}")
    if "refresh_token" in tok:
        print(tok["refresh_token"])
        sys.exit(0)
    err = tok.get("error", "")
    if err == "authorization_pending":
        if time.time() - last_heartbeat > 30:
            print("    still waiting...")
            last_heartbeat = time.time()
        continue
    if err == "slow_down":
        poll += 5
        continue
    raise SystemExit(f"device-code flow failed: {tok}")

raise SystemExit("device-code expired before authorization")
PY
)
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
