"""Data models for network route and interface types."""

from dataclasses import dataclass, field


@dataclass
class InterfaceAddress:
    """A single IP address assigned to a network interface."""

    address: str
    netmask: str
    family: str  # "ipv4" | "ipv6"
    is_link_local: bool


@dataclass
class NetworkInterfaceInfo:
    """A network interface with metadata for Pro DJ Link suitability scoring."""

    name: str
    display_name: str
    addresses: list[InterfaceAddress] = field(default_factory=list)
    is_up: bool = False
    is_loopback: bool = False
    has_link_local: bool = False
    type: str = "other"  # "ethernet" | "wifi" | "vpn" | "virtual" | "other"
    score: int = 0  # Pro DJ Link suitability score (same algorithm as Java bridge)


@dataclass
class RouteStatus:
    """Raw result of checking the macOS broadcast route."""

    interface: str | None
    gateway: str | None
    raw_output: str


@dataclass
class RouteCheckResult:
    """Comparison of current route against the expected interface."""

    correct: bool
    current_interface: str | None
    expected_interface: str
    fix_available: bool  # True on macOS, False on Linux


@dataclass
class RouteFixResult:
    """Result of attempting to fix the broadcast route."""

    success: bool
    error: str | None
    previous_interface: str | None
    new_interface: str
