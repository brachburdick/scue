#!/usr/bin/env bash
# uninstall-route-fix.sh — Remove SCUE DJ Link route fix automation
#
# Removes:
# 1. /usr/local/bin/scue-route-fix
# 2. /etc/sudoers.d/scue-djlink
# 3. ~/Library/LaunchAgents/com.scue.route-fix.plist

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

if [[ $EUID -ne 0 ]]; then
    echo -e "${RED}This script must be run with sudo${NC}"
    echo "  sudo $0"
    exit 1
fi

REAL_USER="${SUDO_USER:-$(logname 2>/dev/null || echo $USER)}"
REAL_HOME=$(eval echo "~$REAL_USER")

echo -e "${YELLOW}Removing SCUE route fix automation${NC}"
echo ""

# 1. Unload and remove launchd agent
PLIST_FILE="$REAL_HOME/Library/LaunchAgents/com.scue.route-fix.plist"
if [[ -f "$PLIST_FILE" ]]; then
    sudo -u "$REAL_USER" launchctl unload "$PLIST_FILE" 2>/dev/null || true
    rm -f "$PLIST_FILE"
    echo -e "  ${GREEN}Removed launchd agent${NC}"
else
    echo -e "  ${YELLOW}LaunchAgent not found (already removed?)${NC}"
fi

# 2. Remove sudoers entry
SUDOERS_FILE="/etc/sudoers.d/scue-djlink"
if [[ -f "$SUDOERS_FILE" ]]; then
    rm -f "$SUDOERS_FILE"
    echo -e "  ${GREEN}Removed sudoers entry${NC}"
else
    echo -e "  ${YELLOW}Sudoers entry not found (already removed?)${NC}"
fi

# 3. Remove route fix script
if [[ -f "/usr/local/bin/scue-route-fix" ]]; then
    rm -f "/usr/local/bin/scue-route-fix"
    echo -e "  ${GREEN}Removed route fix script${NC}"
else
    echo -e "  ${YELLOW}Route fix script not found (already removed?)${NC}"
fi

echo ""
echo -e "${GREEN}Uninstallation complete.${NC}"
echo "Note: The broadcast route fix will no longer persist across reboots."
echo "You can manually fix it with: sudo ./tools/fix-djlink-route.sh <interface>"
