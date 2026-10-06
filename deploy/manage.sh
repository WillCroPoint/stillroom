#!/usr/bin/env bash
# Source builds for generic Docker and Unraid; no registry or scheduled updater needed.
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
ENV_FILE="$ROOT/deploy/docker/.env"
ACTION=${1:-start}
case "$ACTION" in start|update|apply|stop|logs|status) ;; *) echo 'Usage: deploy/manage.sh [start|update|apply|stop|logs|status]' >&2; exit 2;; esac
if [[ ! -f "$ENV_FILE" ]]; then
    echo 'First copy deploy/docker/env.example (or deploy/unraid/env.example) to deploy/docker/.env and edit it.' >&2
    exit 1
fi
# This is trusted, locally maintained configuration, using shell assignment syntax.
set -a
source "$ENV_FILE"
set +a
docker compose version >/dev/null
COMPOSE=(docker compose --env-file "$ENV_FILE" -f "$ROOT/deploy/docker/compose.yaml")
if [[ "$ACTION" == update ]]; then
    : "${GIT_REMOTE:?Set GIT_REMOTE in deploy/docker/.env to your deployment remote}"
    : "${GIT_BRANCH:?Set GIT_BRANCH in deploy/docker/.env to your deployment branch}"
    [[ "$GIT_REMOTE" != -* && "$GIT_BRANCH" != -* ]] || { echo 'Invalid Git remote/branch' >&2; exit 1; }
    [[ -z "$(git status --porcelain)" ]] || { echo 'Working tree is not clean. Save your changes before updating.' >&2; exit 1; }
    [[ "$(git symbolic-ref --short HEAD)" == "$GIT_BRANCH" ]] || { echo 'Checkout must already be on GIT_BRANCH; no automatic branch switching.' >&2; exit 1; }
    git pull --ff-only "$GIT_REMOTE" "$GIT_BRANCH"
    # Re-read the script/config from the updated revision.
    exec bash "$ROOT/deploy/manage.sh" start
fi
case "$ACTION" in
    start)
        DATA_PATH=${DATA_DIR:-./data}
        [[ "$DATA_PATH" == /* ]] || DATA_PATH="$ROOT/deploy/docker/$DATA_PATH"
        if [[ ! -d "$DATA_PATH" ]]; then
            mkdir -p -- "$DATA_PATH"
            if [[ $(id -u) == 0 ]]; then
                chown "${PUID:-1000}:${PGID:-1000}" "$DATA_PATH"
            fi
        fi
        # Build failure leaves the running container intact. Never call 'down -v'.
        "${COMPOSE[@]}" build --pull
        "${COMPOSE[@]}" up -d --no-build --wait --wait-timeout 120
        echo "Studio available at: ${FRAIMIC_PUBLIC_ORIGIN:-http://localhost:8080}"
        ;;
    apply)
        "${COMPOSE[@]}" up -d --no-build --force-recreate --wait --wait-timeout 120
        "${COMPOSE[@]}" ps
        ;;
    stop) "${COMPOSE[@]}" stop ;;
    logs) "${COMPOSE[@]}" logs -f --tail=100 ;;
    status) "${COMPOSE[@]}" ps ;;
esac
