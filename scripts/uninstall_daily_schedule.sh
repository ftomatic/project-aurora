#!/bin/zsh
set -eu

TARGET="$HOME/Library/LaunchAgents/com.aurora.daily-factory.plist"
launchctl bootout "gui/$(id -u)" "$TARGET" 2>/dev/null || true
rm -f "$TARGET"
echo "Aurora daily factory schedule uninstalled."
