#!/usr/bin/env bash
# Auto-Pull & Auto-Deploy Watcher for Stephan Van Vuuren's Network Tester
# Polls https://github.com/stephanv48v/stephan-network-tester (main branch) every 15 seconds
# and automatically deploys updates + restarts services when a new commit arrives.

set -u

REPO_DIR="/opt/stephan-network-tester"
BRANCH="main"
LOG_FILE="/var/log/stephan-auto-deploy.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

deploy_once() {
    cd "$REPO_DIR" || return 1
    git fetch origin "$BRANCH" --quiet 2>/dev/null || return 1

    LOCAL_SHA=$(git rev-parse HEAD 2>/dev/null || echo "none")
    REMOTE_SHA=$(git rev-parse "origin/$BRANCH" 2>/dev/null || echo "none")

    if [ "$LOCAL_SHA" != "$REMOTE_SHA" ] && [ "$REMOTE_SHA" != "none" ]; then
        log "New commit detected on origin/$BRANCH ($LOCAL_SHA -> $REMOTE_SHA). Deploying..."
        git reset --hard "origin/$BRANCH"
        sed -i 's/\r$//' "$REPO_DIR"/scripts/*.sh "$REPO_DIR"/scripts/*.py "$REPO_DIR"/systemd/*.service 2>/dev/null || true
        chmod +x "$REPO_DIR"/scripts/*.sh "$REPO_DIR"/scripts/*.py 2>/dev/null || true

        if [ -f "$REPO_DIR/backend/requirements.txt" ] && [ -x "$REPO_DIR/venv/bin/pip" ]; then
            "$REPO_DIR/venv/bin/pip" install -q -r "$REPO_DIR/backend/requirements.txt" || true
        fi

        cp "$REPO_DIR/systemd/trex-server.service" /etc/systemd/system/trex-server.service 2>/dev/null || true
        cp "$REPO_DIR/systemd/stephan-tester-web.service" /etc/systemd/system/stephan-tester-web.service 2>/dev/null || true
        cp "$REPO_DIR/systemd/stephan-auto-deploy.service" /etc/systemd/system/stephan-auto-deploy.service 2>/dev/null || true
        systemctl daemon-reload || true

        systemctl restart stephan-tester-web.service || true
        log "Deployment of $REMOTE_SHA complete. stephan-tester-web.service restarted."
    fi
}

if [ "${1:-}" = "--once" ]; then
    deploy_once
    exit 0
fi

log "Starting Stephan's Network Tester Git Auto-Pull & Auto-Deploy daemon (polling origin/$BRANCH every 15s)..."
while true; do
    deploy_once
    sleep 15
done
