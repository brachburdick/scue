#!/usr/bin/env bash
# fix-djlink-route.sh — Fix macOS broadcast route for Pro DJ Link
#
# Pioneer DJ hardware uses link-local addresses (169.254.x.x) and broadcasts
# to 169.254.255.255. On macOS, the broadcast route often points to the wrong
# interface (Wi-Fi, VPN, etc.), preventing beat-link from discovering devices.
#
# This script fixes the route to point to the correct Ethernet interface.
#
# Usage:
#   sudo ./tools/fix-djlink-route.sh [interface]
#   sudo ./tools/fix-djlink-route.sh en16
#   sudo ./tools/fix-djlink-route.sh          # auto-detect
#
# The fix persists until reboot. Run again after restarting your Mac.

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

if [[ $EUID -ne 0 ]]; then
    echo -e "${RED}This script must be run with sudo${NC}"
    echo "  sudo $0 $*"
    exit 1
fi

INTERFACE="${1:-}"

# Auto-detect: find the interface with a 169.254.x.x address
if [[ -z "$INTERFACE" ]]; then
    INTERFACE=$(ifconfig | grep -B 5 "inet 169.254" | grep "^[a-z]" | head -1 | cut -d: -f1)
    if [[ -z "$INTERFACE" ]]; then
        echo -e "${RED}No interface found with a 169.254.x.x address${NC}"
        echo "Specify the interface manually: sudo $0 en16"
        exit 1
    fi
    echo -e "${YELLOW}Auto-detected interface: ${INTERFACE}${NC}"
fi

# Verify the interface exists and is up
if ! ifconfig "$INTERFACE" > /dev/null 2>&1; then
    echo -e "${RED}Interface $INTERFACE not found${NC}"
    exit 1
fi

# Show current route
echo -e "\n${YELLOW}Current route for 169.254.255.255:${NC}"
route get 169.254.255.255 2>/dev/null | grep -E "(interface|gateway)" || true

# Fix the route
echo -e "\n${YELLOW}Fixing route...${NC}"
route delete 169.254.255.255 2>/dev/null || true
route add -host 169.254.255.255 -interface "$INTERFACE"

# Verify
echo -e "\n${GREEN}Updated route for 169.254.255.255:${NC}"
route get 169.254.255.255 2>/dev/null | grep -E "(interface|gateway)" || true

echo -e "\n${GREEN}Done.${NC} Pro DJ Link broadcast now routes via ${INTERFACE}."
echo "Restart the SCUE bridge to pick up the change."
echo -e "${YELLOW}Note: This fix does not persist across reboots.${NC}"
