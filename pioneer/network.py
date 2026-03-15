"""Network interface discovery for Pro DJ Link.

Pro DJ Link devices use link-local addresses (169.254.x.x) when no DHCP
server is present. On macOS with multiple interfaces (WiFi + USB-Ethernet),
binding to 0.0.0.0 often doesn't receive broadcasts from non-primary
interfaces. We enumerate all interfaces and bind to each IP explicitly.
"""

import socket

try:
    import netifaces
    _HAS_NETIFACES = True
except ImportError:
    _HAS_NETIFACES = False


def get_local_interfaces() -> list[dict]:
    """Return all local IPv4 interfaces (excluding loopback).

    Returns a list of dicts with keys:
        interface   str   OS name (e.g. "en16")
        ip          str   IPv4 address (e.g. "169.254.20.47")
        netmask     str   Subnet mask (e.g. "255.255.0.0")
        broadcast   str   Broadcast address or "" if not available
    """
    results = []

    if _HAS_NETIFACES:
        for iface in netifaces.interfaces():
            addrs = netifaces.ifaddresses(iface)
            for addr in addrs.get(netifaces.AF_INET, []):
                ip = addr.get("addr", "")
                if not ip or ip.startswith("127."):
                    continue
                results.append({
                    "interface": iface,
                    "ip": ip,
                    "netmask": addr.get("netmask", ""),
                    "broadcast": addr.get("broadcast", ""),
                })
    else:
        # Minimal fallback — only catches the default-route interface
        try:
            hostname = socket.gethostname()
            for res in socket.getaddrinfo(hostname, None, socket.AF_INET):
                ip = res[4][0]
                if not ip.startswith("127."):
                    results.append({
                        "interface": "unknown",
                        "ip": ip,
                        "netmask": "",
                        "broadcast": "",
                    })
        except Exception:
            pass

    return results


def is_link_local(ip: str) -> bool:
    """Return True if an IP is in the 169.254.x.x range (APIPA / link-local)."""
    return ip.startswith("169.254.")


def pioneer_interfaces(all_ifaces: list[dict]) -> list[dict]:
    """Return the subset of interfaces most likely to carry Pro DJ Link traffic.

    Prioritises link-local (169.254.x.x) interfaces since Pioneer gear defaults
    to APIPA when no DHCP server is present. Falls back to all non-loopback
    interfaces if none are link-local.
    """
    link_local = [i for i in all_ifaces if is_link_local(i["ip"])]
    return link_local if link_local else all_ifaces
