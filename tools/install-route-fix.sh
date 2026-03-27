#!/usr/bin/env bash
# install-route-fix.sh — Install persistent DJ Link route fixing for SCUE
#
# This script installs:
# 1. /usr/local/bin/scue-route-fix — a minimal route fix script
# 2. /etc/sudoers.d/scue-djlink — passwordless sudo for that script
# 3. ~/Library/LaunchAgents/com.scue.route-fix.plist — launchd agent
#
# The launchd agent watches for network changes (cable plug/unplug) and
# automatically fixes the macOS broadcast route for Pro DJ Link.
#
# Usage:
#   sudo ./tools/install-route-fix.sh [interface]
#   sudo ./tools/install-route-fix.sh en16
#   sudo ./tools/install-route-fix.sh          # uses config/bridge.yaml

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

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Determine interface
INTERFACE="${1:-}"
if [[ -z "$INTERFACE" ]]; then
    # Try to read from config/bridge.yaml
    CONFIG="$PROJECT_DIR/config/bridge.yaml"
    if [[ -f "$CONFIG" ]]; then
        INTERFACE=$(grep "network_interface:" "$CONFIG" | awk '{print $2}' | tr -d "'\"")
    fi
fi
if [[ -z "$INTERFACE" ]]; then
    echo -e "${RED}No interface specified and none found in config/bridge.yaml${NC}"
    echo "Usage: sudo $0 <interface>"
    exit 1
fi

# Validate interface name
if ! [[ "$INTERFACE" =~ ^en[0-9]+$ ]]; then
    echo -e "${RED}Invalid interface name: $INTERFACE (must match en<number>)${NC}"
    exit 1
fi

REAL_USER="${SUDO_USER:-$(logname 2>/dev/null || echo $USER)}"
REAL_HOME=$(eval echo "~$REAL_USER")

echo -e "${YELLOW}Installing SCUE route fix for interface: $INTERFACE${NC}"
echo "  User: $REAL_USER"
echo "  Home: $REAL_HOME"
echo ""

# 1. Install the route fix script
echo -e "${YELLOW}[1/3] Installing /usr/local/bin/scue-route-fix${NC}"
cat > /usr/local/bin/scue-route-fix << 'SCRIPT'
#!/usr/bin/env bash
# scue-route-fix — Fix macOS broadcast route for Pro DJ Link
# Installed by SCUE. Do not edit manually.
set -euo pipefail

ARG="${1:-}"

if [[ -z "$ARG" ]]; then
    echo "Usage: scue-route-fix <interface>" >&2
    exit 1
fi

# --check flag: dry run, just verify passwordless sudo works (must come before regex)
if [[ "$ARG" == "--check" ]]; then
    echo "OK"
    exit 0
fi

# Validate interface name (prevent injection)
if ! [[ "$ARG" =~ ^en[0-9]+$ ]]; then
    echo "Invalid interface: $ARG (must match en<number>)" >&2
    exit 1
fi

INTERFACE="$ARG"

# 1. Delete competing 169.254 subnet routes from OTHER interfaces.
#    macOS adds 169.254.0.0/16 for every link-local-capable interface.
#    When en0 (Wi-Fi) and en16 (USB-Ethernet) both have one, beat-link's
#    non-broadcast link-local traffic goes out the wrong interface.
for competing in $(netstat -rn -f inet | awk '/^169\.254[[:space:]]/ && !/169\.254\.255\.255/ {print $NF}' | sort -u); do
    if [ "$competing" != "$INTERFACE" ]; then
        route delete -net 169.254.0.0/16 -interface "$competing" 2>/dev/null && \
            echo "Deleted competing subnet route: 169.254.0.0/16 via $competing" || true
    fi
done

# 2. Ensure subnet route exists for the target interface
route add -net 169.254.0.0/16 -interface "$INTERFACE" 2>/dev/null && \
    echo "Added subnet route: 169.254.0.0/16 -> $INTERFACE" || true

# 3. Fix the host broadcast route (existing logic)
route delete 169.254.255.255 2>/dev/null || true
route add -host 169.254.255.255 -interface "$INTERFACE"
echo "Route fixed: 169.254.255.255 -> $INTERFACE"
SCRIPT
chmod 755 /usr/local/bin/scue-route-fix
echo -e "  ${GREEN}Done${NC}"

# 2. Install sudoers entry
echo -e "${YELLOW}[2/3] Installing /etc/sudoers.d/scue-djlink${NC}"
SUDOERS_FILE="/etc/sudoers.d/scue-djlink"
cat > "$SUDOERS_FILE.tmp" << EOF
# Allow SCUE to fix the DJ Link broadcast route without a password.
# Installed by tools/install-route-fix.sh. Remove with tools/uninstall-route-fix.sh.
$REAL_USER ALL=(root) NOPASSWD: /usr/local/bin/scue-route-fix
EOF

# Validate before installing
if visudo -cf "$SUDOERS_FILE.tmp" > /dev/null 2>&1; then
    mv "$SUDOERS_FILE.tmp" "$SUDOERS_FILE"
    chmod 440 "$SUDOERS_FILE"
    echo -e "  ${GREEN}Done${NC}"
else
    rm -f "$SUDOERS_FILE.tmp"
    echo -e "  ${RED}Sudoers validation failed — skipping${NC}"
fi

# 3. Install launchd agent
echo -e "${YELLOW}[3/3] Installing launchd agent${NC}"
PLIST_DIR="$REAL_HOME/Library/LaunchAgents"
PLIST_FILE="$PLIST_DIR/com.scue.route-fix.plist"
LOG_FILE="$REAL_HOME/Library/Logs/scue-route-fix.log"

mkdir -p "$PLIST_DIR"

cat > "$PLIST_FILE" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.scue.route-fix</string>

    <key>ProgramArguments</key>
    <array>
        <string>sudo</string>
        <string>/usr/local/bin/scue-route-fix</string>
        <string>$INTERFACE</string>
    </array>

    <key>WatchPaths</key>
    <array>
        <string>/Library/Preferences/SystemConfiguration</string>
    </array>

    <key>RunAtLoad</key>
    <true/>

    <key>StandardOutPath</key>
    <string>$LOG_FILE</string>

    <key>StandardErrorPath</key>
    <string>$LOG_FILE</string>
</dict>
</plist>
EOF

chown "$REAL_USER" "$PLIST_FILE"
chmod 644 "$PLIST_FILE"

# Load the agent (as the real user, not root)
sudo -u "$REAL_USER" launchctl unload "$PLIST_FILE" 2>/dev/null || true
sudo -u "$REAL_USER" launchctl load "$PLIST_FILE"
echo -e "  ${GREEN}Done${NC}"

# Update bridge.yaml to record installation
BRIDGE_YAML="$PROJECT_DIR/config/bridge.yaml"
if [[ -f "$BRIDGE_YAML" ]]; then
    if ! grep -q "launchd_installed" "$BRIDGE_YAML"; then
        echo "" >> "$BRIDGE_YAML"
        echo "  route:" >> "$BRIDGE_YAML"
        echo "    auto_fix: true" >> "$BRIDGE_YAML"
        echo "    launchd_installed: true" >> "$BRIDGE_YAML"
    fi
fi

echo ""
echo -e "${GREEN}Installation complete!${NC}"
echo ""
echo "  Route fix script: /usr/local/bin/scue-route-fix"
echo "  Sudoers entry:    /etc/sudoers.d/scue-djlink"
echo "  LaunchAgent:      $PLIST_FILE"
echo "  Log file:         $LOG_FILE"
echo ""
echo "The route will be automatically fixed on:"
echo "  - Login/reboot"
echo "  - Network cable plug/unplug"
echo ""
echo "To remove: sudo ./tools/uninstall-route-fix.sh"
