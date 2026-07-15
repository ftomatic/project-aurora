#!/bin/zsh
set -eu

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TEMPLATE="$PROJECT_ROOT/config/com.aurora.daily-factory.plist.template"
TARGET="$HOME/Library/LaunchAgents/com.aurora.daily-factory.plist"

mkdir -p "$HOME/Library/LaunchAgents" "$PROJECT_ROOT/data/aurora/logs"
sed "s#__PROJECT_ROOT__#$PROJECT_ROOT#g" "$TEMPLATE" > "$TARGET"
chmod +x "$PROJECT_ROOT/scripts/run_daily_factory_scheduled.sh"
launchctl bootout "gui/$(id -u)" "$TARGET" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$TARGET"

echo "Aurora daily factory schedule installed."
echo "The Mac must be awake, logged in, and connected to the internet."
