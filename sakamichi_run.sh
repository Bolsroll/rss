#!/bin/bash

set -euo pipefail

# =======================
# 設定
# =======================
BASE_DIR="/Users/dig/rss"
NOGI_DIR="$BASE_DIR/nogi"
SAKURA_DIR="$BASE_DIR/sakura"

LOG_FILE="/tmp/sakamichi.log"
LOCK_FILE="/tmp/sakamichi.lock"

PYTHON="/usr/local/bin/python3"

export PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export LANG="ja_JP.UTF-8"
export LC_ALL="ja_JP.UTF-8"

# =======================
# ログ初期化
# =======================
: > "$LOG_FILE"

log() {
    echo "$1" | tee -a "$LOG_FILE"
}

log "=============================="
log "START: $(date)"

# =======================
# 共通ロック
# =======================
if [ -f "$LOCK_FILE" ]; then
    log "⛔ 他プロセス実行中（共通ロック）"
    exit 0
fi

touch "$LOCK_FILE"

# =======================
# 乃木
# =======================
cd "$NOGI_DIR"

log "[NOGI] main"
$PYTHON main.py >> "$LOG_FILE" 2>&1 || {
    log "❌ NOGI main失敗"
    rm -f "$LOCK_FILE"
    exit 1
}

log "[NOGI] xml"
$PYTHON make_member_xml.py >> "$LOG_FILE" 2>&1 || {
    log "❌ NOGI xml失敗"
    rm -f "$LOCK_FILE"
    exit 1
}

# =======================
# 櫻
# =======================
cd "$SAKURA_DIR"

log "[SAKURA] main"
$PYTHON main.py >> "$LOG_FILE" 2>&1 || {
    log "❌ SAKURA main失敗"
    rm -f "$LOCK_FILE"
    exit 1
}

log "[SAKURA] xml"
$PYTHON make_member_xml.py >> "$LOG_FILE" 2>&1 || {
    log "❌ SAKURA xml失敗"
    rm -f "$LOCK_FILE"
    exit 1
}

# =======================
# Git（1回だけ）
# =======================
cd "$BASE_DIR"

log "[GIT] cleanup"
rm -f .git/index.lock 2>/dev/null || true
rm -rf .git/rebase-merge 2>/dev/null || true

export GIT_TERMINAL_PROMPT=0

log "[GIT] add"
git add -A >> "$LOG_FILE" 2>&1

log "[GIT] commit"
git commit -m "auto update $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG_FILE" 2>&1 || {
    log "[GIT] nothing to commit (skip commit)"
}

log "[GIT] push"
git push -f origin main >> "$LOG_FILE" 2>&1 || {
    log "❌ git push失敗"
    rm -f "$LOCK_FILE"
    exit 1
}

# =======================
# 終了
# =======================
rm -f "$LOCK_FILE"

log "END: $(date)"
log "=============================="