"""Network subsystem — route management and interface enumeration."""

from .models import (
    InterfaceAddress,
    NetworkInterfaceInfo,
    RouteCheckResult,
    RouteFixResult,
    RouteStatus,
)
from .route import (
    check_route,
    check_subnet_routes,
    enumerate_interfaces,
    fix_route,
    get_current_route,
)

__all__ = [
    "InterfaceAddress",
    "NetworkInterfaceInfo",
    "RouteCheckResult",
    "RouteFixResult",
    "RouteStatus",
    "check_route",
    "check_subnet_routes",
    "enumerate_interfaces",
    "fix_route",
    "get_current_route",
]
