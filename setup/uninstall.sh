#!/bin/bash
# Uninstall Lex launchd agents
set -euo pipefail

echo "Uninstalling Lex LaunchAgents..."

for label in com.erpaccess.lex-scrape com.erpaccess.lex-publish; do
    plist="$HOME/Library/LaunchAgents/$label.plist"
    if [ -f "$plist" ]; then
        launchctl unload "$plist" 2>/dev/null || true
        rm "$plist"
        echo "  Removed $label"
    fi
done

echo "Done."
