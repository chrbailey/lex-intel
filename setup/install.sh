#!/bin/bash
# Install Lex launchd agents
# Usage: bash setup/install.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST_DIR="$HOME/Library/LaunchAgents"

echo "Installing Lex LaunchAgents..."

# Create logs directory
mkdir -p "$SCRIPT_DIR/../logs"

# Copy plists (don't symlink — launchd needs real files)
for plist in "$SCRIPT_DIR"/com.erpaccess.lex-*.plist; do
    name=$(basename "$plist")
    cp "$plist" "$PLIST_DIR/$name"
    echo "  Installed $name"
done

# Load (but disabled by default — user enables when ready)
echo ""
echo "Agents installed but NOT loaded. To enable:"
echo "  launchctl load ~/Library/LaunchAgents/com.erpaccess.lex-scrape.plist"
echo "  launchctl load ~/Library/LaunchAgents/com.erpaccess.lex-publish.plist"
echo ""
echo "To test immediately:"
echo "  launchctl start com.erpaccess.lex-scrape"
echo "  launchctl start com.erpaccess.lex-publish"
echo ""
echo "To disable:"
echo "  launchctl unload ~/Library/LaunchAgents/com.erpaccess.lex-scrape.plist"
echo "  launchctl unload ~/Library/LaunchAgents/com.erpaccess.lex-publish.plist"
