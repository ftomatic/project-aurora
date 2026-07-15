#!/bin/zsh
set -eu

launchctl print "gui/$(id -u)/com.aurora.daily-factory" 2>/dev/null || {
  echo "Aurora daily factory schedule is not loaded."
  exit 1
}
