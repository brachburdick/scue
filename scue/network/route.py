"""Route inspection, repair, and interface enumeration for Pro DJ Link.

On macOS, the OS broadcast route for 169.254.255.255 must point to the correct
Ethernet interface for Pioneer device discovery to work. This module provides
programmatic route management so the bridge manager and API can fix the route
without manual sudo commands.

Interface enumeration replicates the Java bridge's scoring algorithm so results
are consistent. Works even when the bridge is not running.
"""

import ipaddress
import logging
import platform
import re
import subprocess

import psutil

from .models import (
    InterfaceAddress,
    NetworkInterfaceInfo,
    RouteCheckResult,
    RouteFixResult,
    RouteStatus,
)

logger = logging.getLogger(__name__)

# Path to the sudoers-whitelisted route fix script (installed by tools/install-route-fix.sh)
ROUTE_FIX_SCRIPT = "/usr/local/bin/scue-route-fix"

# Virtual/loopback interface name patterns to exclude
_VIRTUAL_PATTERNS = re.compile(
    r"^(lo\d*|veth|docker|br-|vmnet|utun|awdl|llw|bridge|ap\d)"
)

# Wired Ethernet name patterns
_WIRED_PATTERNS = re.compile(r"^(en\d+|eth\d+|enp\d+)")

# Wi-Fi name patterns
_WIFI_PATTERNS = re.compile(r"^(wl|wlan|Wi-Fi|airport)")

# VPN name patterns
_VPN_PATTERNS = re.compile(r"^(utun|tun|tap|ppp|ipsec|wireguard)")


def get_current_route() -> RouteStatus:
    """Parse the macOS broadcast route for 169.254.255.255.

    Uses two sources in order of reliability:

    1. ``netstat -rn -f inet`` — shows the actual kernel routing table.
       A host route added via ``route add -host`` appears here immediately
       and unambiguously.  We look for an exact ``169.254.255.255`` entry
       and read its Netif column.

    2. ``route get 169.254.255.255`` (fallback) — asks the kernel "how
       would you route to this address?"  For link-local broadcast addresses
       on macOS this sometimes returns the connected subnet route rather than
       an explicitly-added host route, and occasionally omits the
       ``interface:`` line entirely even when a valid route exists.

    Returns a RouteStatus with the current interface and raw output.
    On non-macOS, returns empty values.
    """
    if platform.system() != "Darwin":
        return RouteStatus(interface=None, gateway=None, raw_output="")

    # --- Primary: netstat -rn -f inet ---
    try:
        ns = subprocess.run(
            ["netstat", "-rn", "-f", "inet"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        for line in ns.stdout.splitlines():
            parts = line.split()
            # Columns: Destination  Gateway  Flags  Netif  [Expire]
            # Match exact host route "169.254.255.255" in Destination column
            if parts and parts[0] == "169.254.255.255" and len(parts) >= 4:
                netif = parts[3]
                logger.debug("netstat route for 169.254.255.255: %s", netif)
                return RouteStatus(
                    interface=netif,
                    gateway=parts[1] if len(parts) > 1 else None,
                    raw_output=ns.stdout,
                )
    except Exception as e:
        logger.debug("netstat route check failed: %s", e)

    # --- Fallback: route get ---
    try:
        result = subprocess.run(
            ["route", "get", "169.254.255.255"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        raw = result.stdout
        interface = None
        gateway = None

        for line in raw.splitlines():
            stripped = line.strip()
            if stripped.startswith("interface:"):
                interface = stripped.split(":", 1)[1].strip()
            elif stripped.startswith("gateway:"):
                gateway = stripped.split(":", 1)[1].strip()

        if interface:
            logger.debug("route get interface for 169.254.255.255: %s", interface)
        else:
            logger.debug(
                "route get returned no interface for 169.254.255.255 "
                "(no host route found in routing table)"
            )

        return RouteStatus(interface=interface, gateway=gateway, raw_output=raw)
    except Exception as e:
        logger.debug("Could not check macOS broadcast route: %s", e)
        return RouteStatus(interface=None, gateway=None, raw_output=str(e))


def check_route(expected_interface: str) -> RouteCheckResult:
    """Compare the current broadcast route against the expected interface.

    On Linux, link-local routing works differently so this always returns correct=True.
    """
    is_mac = platform.system() == "Darwin"

    if not is_mac:
        return RouteCheckResult(
            correct=True,
            current_interface=None,
            expected_interface=expected_interface,
            fix_available=False,
        )

    status = get_current_route()
    correct = status.interface == expected_interface

    return RouteCheckResult(
        correct=correct,
        current_interface=status.interface,
        expected_interface=expected_interface,
        fix_available=True,
    )


def fix_route(interface: str) -> RouteFixResult:
    """Fix the macOS broadcast route to point to the given interface.

    Uses the sudoers-whitelisted script at /usr/local/bin/scue-route-fix.
    On Linux, this is a no-op (link-local routing works automatically).
    """
    if platform.system() != "Darwin":
        return RouteFixResult(
            success=True,
            error=None,
            previous_interface=None,
            new_interface=interface,
        )

    # Validate interface name to prevent injection
    if not re.match(r"^en\d+$", interface):
        return RouteFixResult(
            success=False,
            error=f"Invalid interface name: {interface}. Must match en<number>.",
            previous_interface=None,
            new_interface=interface,
        )

    # Get current state before fixing
    current = get_current_route()
    previous = current.interface

    try:
        result = subprocess.run(
            ["sudo", ROUTE_FIX_SCRIPT, interface],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            error_msg = result.stderr.strip() or result.stdout.strip()
            # Check if it's a sudo/permission issue
            if "password" in error_msg.lower() or "not allowed" in error_msg.lower():
                error_msg = (
                    f"Route fix requires sudo access. Run: sudo ./tools/install-route-fix.sh"
                )
            return RouteFixResult(
                success=False,
                error=error_msg,
                previous_interface=previous,
                new_interface=interface,
            )

        # Trust the script's exit code — exit 0 means the route was set.
        #
        # We intentionally do NOT hard-fail on post-fix verification here.
        # `route get 169.254.255.255` on macOS doesn't reliably reflect a
        # freshly-added host route for link-local broadcast addresses; it
        # frequently falls back to the connected subnet route and omits the
        # "interface:" line entirely, even when the route was successfully
        # added to the kernel table. Treating that as a failure produces a
        # false error ("route still points to None") while the actual route
        # is correct — which we confirmed by running `route add` to success.
        #
        # We still call get_current_route() so we can log discrepancies for
        # future debugging, but the result does not affect the return value.
        after = get_current_route()
        if after.interface != interface:
            logger.debug(
                "Post-fix route get returned %r (expected %r) — "
                "this is a known macOS quirk for link-local broadcast routes; "
                "the route was set correctly (script exit 0)",
                after.interface,
                interface,
            )

        logger.info("Fixed broadcast route: %s -> %s", previous, interface)
        return RouteFixResult(
            success=True,
            error=None,
            previous_interface=previous,
            new_interface=interface,
        )
    except FileNotFoundError:
        return RouteFixResult(
            success=False,
            error=(
                f"Route fix script not found at {ROUTE_FIX_SCRIPT}. "
                f"Run: sudo ./tools/install-route-fix.sh"
            ),
            previous_interface=previous,
            new_interface=interface,
        )
    except Exception as e:
        return RouteFixResult(
            success=False,
            error=str(e),
            previous_interface=previous,
            new_interface=interface,
        )


def _is_link_local(addr: str) -> bool:
    """Check if an IP address is in the 169.254.0.0/16 range."""
    try:
        return ipaddress.ip_address(addr) in ipaddress.ip_network("169.254.0.0/16")
    except ValueError:
        return False


def _is_private(addr: str) -> bool:
    """Check if an IP address is in a private range (10.x, 172.16-31.x, 192.168.x)."""
    try:
        return ipaddress.ip_address(addr).is_private
    except ValueError:
        return False


def _classify_interface(name: str) -> str:
    """Classify an interface by name pattern.

    Returns: "ethernet" | "wifi" | "vpn" | "virtual" | "other"
    """
    lower = name.lower()
    if _VIRTUAL_PATTERNS.match(lower):
        return "virtual"
    if _VPN_PATTERNS.match(lower):
        return "vpn"
    if _WIFI_PATTERNS.match(lower):
        return "wifi"
    if _WIRED_PATTERNS.match(lower):
        return "ethernet"
    return "other"


def _score_interface(iface: NetworkInterfaceInfo) -> int:
    """Score an interface for Pro DJ Link suitability.

    Replicates the Java bridge's scoring algorithm:
    - Has link-local address (169.254.x.x): +10
    - Name suggests wired Ethernet: +5
    - Has private IP (10.x, 172.16.x, 192.168.x): +3
    - Name suggests Wi-Fi: -5
    - Name suggests VPN/virtual: -10
    """
    score = 0

    if iface.has_link_local:
        score += 10
    if iface.type == "ethernet":
        score += 5
    if iface.type == "wifi":
        score -= 5
    if iface.type in ("vpn", "virtual"):
        score -= 10

    # Check for private IP addresses
    for addr in iface.addresses:
        if addr.family == "ipv4" and not addr.is_link_local and _is_private(addr.address):
            score += 3
            break

    return score


def enumerate_interfaces() -> list[NetworkInterfaceInfo]:
    """List available network interfaces with Pro DJ Link suitability scoring.

    Uses psutil for cross-platform interface enumeration. Filters out loopback
    and virtual interfaces. Works even when the bridge is not running.
    """
    addrs = psutil.net_if_addrs()
    stats = psutil.net_if_stats()

    interfaces: list[NetworkInterfaceInfo] = []

    for name, addr_list in addrs.items():
        # Skip loopback and virtual
        iface_stats = stats.get(name)
        is_loopback = iface_stats.isup if iface_stats else False
        if name == "lo" or name == "lo0":
            continue
        if _VIRTUAL_PATTERNS.match(name.lower()):
            continue

        is_up = iface_stats.isup if iface_stats else False

        # Build address list
        addresses: list[InterfaceAddress] = []
        has_link_local = False

        for addr in addr_list:
            if addr.family.name == "AF_INET":
                ll = _is_link_local(addr.address)
                if ll:
                    has_link_local = True
                addresses.append(
                    InterfaceAddress(
                        address=addr.address,
                        netmask=addr.netmask or "",
                        family="ipv4",
                        is_link_local=ll,
                    )
                )
            elif addr.family.name == "AF_INET6":
                addresses.append(
                    InterfaceAddress(
                        address=addr.address,
                        netmask=addr.netmask or "",
                        family="ipv6",
                        is_link_local=addr.address.startswith("fe80"),
                    )
                )

        iface_type = _classify_interface(name)

        iface = NetworkInterfaceInfo(
            name=name,
            display_name=name,  # psutil doesn't provide friendly names
            addresses=addresses,
            is_up=is_up,
            is_loopback=False,
            has_link_local=has_link_local,
            type=iface_type,
            score=0,
        )
        iface.score = _score_interface(iface)
        interfaces.append(iface)

    # Sort by score descending
    interfaces.sort(key=lambda i: i.score, reverse=True)
    return interfaces


def check_sudoers_installed() -> bool:
    """Check if the sudoers entry and route-fix script are installed.

    Uses file presence rather than a subprocess call. Both the script at
    ROUTE_FIX_SCRIPT and the sudoers file at /etc/sudoers.d/scue-djlink
    must exist for passwordless route fixing to work.

    Note: the previous --check subprocess approach was unreliable because the
    installed script validated the interface regex *before* handling --check,
    causing a false-negative exit code even when sudoers was correctly set up.
    """
    import os

    script_ok = os.path.isfile(ROUTE_FIX_SCRIPT) and os.access(
        ROUTE_FIX_SCRIPT, os.X_OK
    )
    sudoers_ok = os.path.isfile("/etc/sudoers.d/scue-djlink")
    return script_ok and sudoers_ok


def check_launchd_installed() -> bool:
    """Check if the launchd agent plist is loaded."""
    if platform.system() != "Darwin":
        return False
    try:
        result = subprocess.run(
            ["launchctl", "list", "com.scue.route-fix"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False
