#!/bin/zsh
# Cron wrapper for X post bot.
# Loads credentials from ~/.x_bot_env (not sourced by cron automatically).
# Usage: post_cron.sh <vertical>
#   vertical: finance | crypto | oilgas | brokerage | compliance |
#             betting | gaming | ecommerce | media | solar | weather

source "$HOME/.x_bot_env"

PYTHON=/opt/homebrew/bin/python3
BOT="$HOME/Claude_Projects/REVENUE/X/bot/post.py"
LOG_DIR=/tmp

VERTICAL="${1:-finance}"
LOG="$LOG_DIR/x_post_${VERTICAL}.log"

echo "=== $(date) === posting $VERTICAL" >> "$LOG"
"$PYTHON" "$BOT" "$VERTICAL" >> "$LOG" 2>&1
EXIT=$?

if [ $EXIT -ne 0 ]; then
  echo "FAILED (exit $EXIT)" >> "$LOG"
else
  echo "OK" >> "$LOG"
fi

exit $EXIT
