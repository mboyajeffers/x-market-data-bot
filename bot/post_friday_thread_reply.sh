#!/bin/zsh
# Friday rotation thread reply — mirrors post_friday.sh's rotation formula so
# the reply targets the same vertical the main post actually used, 90 min
# earlier. Added 2026-08-26 — post_friday.sh never had a thread-reply
# companion before.
# Rotation: oilgas → betting → solar → gaming → media → ecommerce → weather
# Full cycle repeats every 7 weeks.

source "$HOME/.x_bot_env"

PYTHON=/opt/homebrew/bin/python3
BOT="$HOME/Claude_Projects/REVENUE/X/bot/post_thread_reply.py"
LOG_DIR=/tmp

VERTICALS=(oilgas betting solar gaming media ecommerce weather)
WEEK=$(date +%V)          # ISO week number (01-53)
IDX=$(( WEEK % 7 ))       # 0-6
VERTICAL=${VERTICALS[$IDX + 1]}   # zsh arrays are 1-indexed

LOG="$LOG_DIR/x_thread_reply_friday_${VERTICAL}.log"

echo "=== $(date) === Friday rotation thread reply: week $WEEK → $VERTICAL" >> "$LOG"
"$PYTHON" "$BOT" "$VERTICAL" >> "$LOG" 2>&1
EXIT=$?

if [ $EXIT -ne 0 ]; then
  echo "FAILED (exit $EXIT)" >> "$LOG"
else
  echo "OK" >> "$LOG"
fi

exit $EXIT
