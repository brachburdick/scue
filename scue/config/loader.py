"""Typed configuration loader for SCUE.

Loads YAML files from config/ and maps them to typed dataclasses.
Missing files or keys fall back to sensible defaults — never crashes.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


@dataclass
class ServerConfig:
    cors_origins: list[str] = field(default_factory=lambda: ["http://localhost:5173"])
    audio_extensions: list[str] = field(
        default_factory=lambda: [".mp3", ".wav", ".flac", ".aiff", ".m4a", ".ogg"]
    )
    tracks_dir: str = "tracks"
    cache_path: str = "cache/scue.db"


@dataclass
class WatchdogConfig:
    is_receiving_threshold_ms: int = 5000
    poll_interval_s: float = 2.0


@dataclass
class HealthConfig:
    check_interval_s: float = 10.0


@dataclass
class RestartConfig:
    base_delay_s: float = 2.0
    max_delay_s: float = 30.0
    max_crash_before_fallback: int = 3


@dataclass
class RouteConfig:
    auto_fix: bool = True
    launchd_installed: bool = False


@dataclass
class BridgeConfig:
    network_interface: str | None = None
    player_number: int = 5
    port: int = 17400
    route: RouteConfig = field(default_factory=RouteConfig)
    watchdog: WatchdogConfig = field(default_factory=WatchdogConfig)
    health: HealthConfig = field(default_factory=HealthConfig)
    restart: RestartConfig = field(default_factory=RestartConfig)


@dataclass
class UsbConfig:
    db_relative_path: str = "PIONEER/rekordbox/exportLibrary.db"
    pdb_relative_path: str = "PIONEER/rekordbox/export.pdb"
    anlz_relative_path: str = "PIONEER/USBANLZ"


@dataclass
class ScueConfig:
    server: ServerConfig = field(default_factory=ServerConfig)
    bridge: BridgeConfig = field(default_factory=BridgeConfig)
    usb: UsbConfig = field(default_factory=UsbConfig)


def _load_yaml(path: Path) -> dict:
    """Load a YAML file, returning empty dict on any failure."""
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning("Failed to load %s: %s", path, e)
        return {}


def _build_server_config(data: dict) -> ServerConfig:
    """Build ServerConfig from the 'server' section of server.yaml."""
    section = data.get("server", {})
    if not isinstance(section, dict):
        return ServerConfig()
    kwargs = {}
    if "cors_origins" in section:
        kwargs["cors_origins"] = section["cors_origins"]
    if "audio_extensions" in section:
        kwargs["audio_extensions"] = section["audio_extensions"]
    if "tracks_dir" in section:
        kwargs["tracks_dir"] = section["tracks_dir"]
    if "cache_path" in section:
        kwargs["cache_path"] = section["cache_path"]
    return ServerConfig(**kwargs)


def _build_bridge_config(data: dict) -> BridgeConfig:
    """Build BridgeConfig from the 'bridge' section of bridge.yaml."""
    section = data.get("bridge", {})
    if not isinstance(section, dict):
        return BridgeConfig()

    # Route sub-config
    route_data = section.get("route", {})
    route = RouteConfig(
        auto_fix=route_data.get("auto_fix", True),
        launchd_installed=route_data.get("launchd_installed", False),
    ) if isinstance(route_data, dict) else RouteConfig()

    # Watchdog sub-config
    wd_data = section.get("watchdog", {})
    watchdog = WatchdogConfig(
        is_receiving_threshold_ms=wd_data.get("is_receiving_threshold_ms", 5000),
        poll_interval_s=wd_data.get("poll_interval_s", 2.0),
    ) if isinstance(wd_data, dict) else WatchdogConfig()

    # Health sub-config
    health_data = section.get("health", {})
    health = HealthConfig(
        check_interval_s=health_data.get("check_interval_s", 10.0),
    ) if isinstance(health_data, dict) else HealthConfig()

    # Restart sub-config
    restart_data = section.get("restart", {})
    restart = RestartConfig(
        base_delay_s=restart_data.get("base_delay_s", 2.0),
        max_delay_s=restart_data.get("max_delay_s", 30.0),
        max_crash_before_fallback=restart_data.get("max_crash_before_fallback", 3),
    ) if isinstance(restart_data, dict) else RestartConfig()

    # Port validation
    port = section.get("port", 17400)
    if not isinstance(port, int) or port < 1024 or port > 65535:
        logger.warning("Invalid bridge port %r, using default 17400", port)
        port = 17400

    return BridgeConfig(
        network_interface=section.get("network_interface"),
        player_number=section.get("player_number", 5),
        port=port,
        route=route,
        watchdog=watchdog,
        health=health,
        restart=restart,
    )


def _build_usb_config(data: dict) -> UsbConfig:
    """Build UsbConfig from the 'usb' section of usb.yaml."""
    section = data.get("usb", {})
    if not isinstance(section, dict):
        return UsbConfig()
    return UsbConfig(
        db_relative_path=section.get("db_relative_path", "PIONEER/rekordbox/exportLibrary.db"),
        anlz_relative_path=section.get("anlz_relative_path", "PIONEER/USBANLZ"),
    )


def load_config(config_dir: Path = Path("config")) -> ScueConfig:
    """Load all configuration from YAML files in config_dir.

    Missing files or keys fall back to defaults. Never raises on bad config.
    """
    server_data = _load_yaml(config_dir / "server.yaml")
    bridge_data = _load_yaml(config_dir / "bridge.yaml")
    usb_data = _load_yaml(config_dir / "usb.yaml")

    config = ScueConfig(
        server=_build_server_config(server_data),
        bridge=_build_bridge_config(bridge_data),
        usb=_build_usb_config(usb_data),
    )

    _log_config(config)
    return config


def _log_config(config: ScueConfig) -> None:
    """Log all config values at INFO level for startup diagnostics."""
    logger.info("--- SCUE Configuration ---")
    logger.info("Server: cors_origins=%s", config.server.cors_origins)
    logger.info("Server: audio_extensions=%s", config.server.audio_extensions)
    logger.info("Server: tracks_dir=%s", config.server.tracks_dir)
    logger.info("Server: cache_path=%s", config.server.cache_path)
    logger.info(
        "Bridge: interface=%s, player=%d, port=%d",
        config.bridge.network_interface,
        config.bridge.player_number,
        config.bridge.port,
    )
    logger.info(
        "Bridge route: auto_fix=%s, launchd_installed=%s",
        config.bridge.route.auto_fix,
        config.bridge.route.launchd_installed,
    )
    logger.info(
        "Bridge watchdog: threshold_ms=%d, poll_s=%.1f",
        config.bridge.watchdog.is_receiving_threshold_ms,
        config.bridge.watchdog.poll_interval_s,
    )
    logger.info("Bridge health: check_interval_s=%.1f", config.bridge.health.check_interval_s)
    logger.info(
        "Bridge restart: base_delay=%.1f, max_delay=%.1f, max_crash=%d",
        config.bridge.restart.base_delay_s,
        config.bridge.restart.max_delay_s,
        config.bridge.restart.max_crash_before_fallback,
    )
    logger.info(
        "USB: db_path=%s, anlz_path=%s",
        config.usb.db_relative_path,
        config.usb.anlz_relative_path,
    )
    logger.info("--- End Configuration ---")
