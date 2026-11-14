#!/usr/bin/env bash
# Dev helper: render secrets into a temp copy of the app config, upload it to a
# Home Assistant host and reload the app store. Not needed for normal installs.
set -euo pipefail
cd "$(dirname "$0")"

APP_DIR=cam_snapshot
DEPLOY_HOST=${DEPLOY_HOST:-pi}
REMOTE_DIR=${REMOTE_DIR:-/addons/cam_snapshot}

if [[ ! -f secrets.env ]]; then
    echo "secrets.env is missing; copy secrets.env.example and fill it in" >&2
    exit 1
fi

# shellcheck disable=SC1091
. ./secrets.env

: "${MOTIONEYE_USER:?set MOTIONEYE_USER in secrets.env}"
: "${MOTIONEYE_PASSWORD:?set MOTIONEYE_PASSWORD in secrets.env}"
: "${SNAPSHOT_TOKEN:?set SNAPSHOT_TOKEN in secrets.env}"

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

cp "$APP_DIR/config.yaml" "$APP_DIR/Dockerfile" "$APP_DIR/build.yaml" \
    "$APP_DIR/README.md" "$APP_DIR/CHANGELOG.md" "$APP_DIR/server.py" "$tmp/"

python3 - "$tmp/config.yaml" "$MOTIONEYE_USER" "$MOTIONEYE_PASSWORD" "$SNAPSHOT_TOKEN" <<'PY'
import json
import re
import sys

path, user, password, token = sys.argv[1:5]
text = open(path, encoding="utf-8").read()

# Drop the prebuilt-image key so the Supervisor builds the uploaded Dockerfile.
text = re.sub(r"(?m)^image: .*\n", "", text)

# Only the `options:` block carries values; `schema:` repeats the same keys.
head, sep, tail = text.partition("\nschema:")
if not sep:
    raise SystemExit("config.yaml has no schema: section")

for key, value in (("username", user), ("password", password), ("token", token)):
    head, count = re.subn(
        rf"(?m)^  {key}: .*$", f"  {key}: {json.dumps(value)}", head
    )
    if count != 1:
        raise SystemExit(f"expected exactly one '{key}:' line in options")

open(path, "w", encoding="utf-8").write(head + sep + tail)
PY

tar czf - -C "$tmp" . | ssh "$DEPLOY_HOST" "
    set -e
    rm -rf '$REMOTE_DIR'
    mkdir -p '$REMOTE_DIR'
    tar xzf - -C '$REMOTE_DIR'
    chmod -R go-rwx '$REMOTE_DIR'
"

ssh "$DEPLOY_HOST" 'ha store reload >/dev/null 2>&1 || true'
echo "uploaded to $DEPLOY_HOST:$REMOTE_DIR"
echo "first install: ssh $DEPLOY_HOST 'ha apps install local_cam_snapshot && ha apps start local_cam_snapshot'"
echo "after edits:   ssh $DEPLOY_HOST 'ha apps rebuild local_cam_snapshot'"
