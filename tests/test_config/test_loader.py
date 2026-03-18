"""Tests for the SCUE config loader."""

from pathlib import Path

import yaml

from scue.config.loader import (
    BridgeConfig,
    ScueConfig,
    ServerConfig,
    UsbConfig,
    load_config,
)


class TestLoadDefaultsWhenNoYaml:
    """Config loader returns all defaults when YAML files don't exist."""

    def test_returns_scue_config(self, tmp_path: Path):
        config = load_config(config_dir=tmp_path)
        assert isinstance(config, ScueConfig)

    def test_server_defaults(self, tmp_path: Path):
        config = load_config(config_dir=tmp_path)
        assert config.server.cors_origins == ["http://localhost:5173"]
        assert config.server.audio_extensions == [".mp3", ".wav", ".flac", ".aiff", ".m4a", ".ogg"]
        assert config.server.tracks_dir == "tracks"
        assert config.server.cache_path == "cache/scue.db"

    def test_bridge_defaults(self, tmp_path: Path):
        config = load_config(config_dir=tmp_path)
        assert config.bridge.port == 17400
        assert config.bridge.player_number == 5
        assert config.bridge.network_interface is None
        assert config.bridge.route.auto_fix is True
        assert config.bridge.watchdog.is_receiving_threshold_ms == 5000
        assert config.bridge.watchdog.poll_interval_s == 2.0
        assert config.bridge.health.check_interval_s == 10.0
        assert config.bridge.restart.base_delay_s == 2.0
        assert config.bridge.restart.max_delay_s == 30.0
        assert config.bridge.restart.max_crash_before_fallback == 3

    def test_usb_defaults(self, tmp_path: Path):
        config = load_config(config_dir=tmp_path)
        assert config.usb.db_relative_path == "PIONEER/rekordbox/exportLibrary.db"
        assert config.usb.anlz_relative_path == "PIONEER/USBANLZ"


class TestLoadPartialYaml:
    """Config loader merges partial YAML with defaults."""

    def test_bridge_partial_no_watchdog(self, tmp_path: Path):
        """bridge.yaml with port but no watchdog section -> watchdog gets defaults."""
        bridge_yaml = tmp_path / "bridge.yaml"
        bridge_yaml.write_text(yaml.dump({"bridge": {"port": 18000}}))

        config = load_config(config_dir=tmp_path)
        assert config.bridge.port == 18000
        assert config.bridge.watchdog.is_receiving_threshold_ms == 5000
        assert config.bridge.watchdog.poll_interval_s == 2.0

    def test_server_partial_only_cors(self, tmp_path: Path):
        """server.yaml with only cors_origins -> other fields get defaults."""
        server_yaml = tmp_path / "server.yaml"
        server_yaml.write_text(yaml.dump({
            "server": {"cors_origins": ["http://localhost:3000"]}
        }))

        config = load_config(config_dir=tmp_path)
        assert config.server.cors_origins == ["http://localhost:3000"]
        assert config.server.tracks_dir == "tracks"
        assert config.server.audio_extensions == [".mp3", ".wav", ".flac", ".aiff", ".m4a", ".ogg"]

    def test_bridge_partial_restart_only(self, tmp_path: Path):
        """bridge.yaml with only restart section -> other sections get defaults."""
        bridge_yaml = tmp_path / "bridge.yaml"
        bridge_yaml.write_text(yaml.dump({
            "bridge": {"restart": {"base_delay_s": 5.0}}
        }))

        config = load_config(config_dir=tmp_path)
        assert config.bridge.restart.base_delay_s == 5.0
        assert config.bridge.restart.max_delay_s == 30.0  # default
        assert config.bridge.health.check_interval_s == 10.0  # default


class TestLoadFullYaml:
    """All values from YAML override defaults."""

    def test_all_values_overridden(self, tmp_path: Path):
        (tmp_path / "server.yaml").write_text(yaml.dump({
            "server": {
                "cors_origins": ["http://example.com"],
                "audio_extensions": [".wav", ".opus"],
                "tracks_dir": "/data/tracks",
                "cache_path": "/data/cache.db",
            }
        }))
        (tmp_path / "bridge.yaml").write_text(yaml.dump({
            "bridge": {
                "network_interface": "en0",
                "player_number": 3,
                "port": 19000,
                "route": {"auto_fix": False, "launchd_installed": True},
                "watchdog": {"is_receiving_threshold_ms": 3000, "poll_interval_s": 1.0},
                "health": {"check_interval_s": 5.0},
                "restart": {"base_delay_s": 1.0, "max_delay_s": 60.0, "max_crash_before_fallback": 5},
            }
        }))
        (tmp_path / "usb.yaml").write_text(yaml.dump({
            "usb": {
                "db_relative_path": "CUSTOM/db.db",
                "anlz_relative_path": "CUSTOM/ANLZ",
            }
        }))

        config = load_config(config_dir=tmp_path)

        assert config.server.cors_origins == ["http://example.com"]
        assert config.server.audio_extensions == [".wav", ".opus"]
        assert config.server.tracks_dir == "/data/tracks"
        assert config.server.cache_path == "/data/cache.db"

        assert config.bridge.network_interface == "en0"
        assert config.bridge.player_number == 3
        assert config.bridge.port == 19000
        assert config.bridge.route.auto_fix is False
        assert config.bridge.route.launchd_installed is True
        assert config.bridge.watchdog.is_receiving_threshold_ms == 3000
        assert config.bridge.watchdog.poll_interval_s == 1.0
        assert config.bridge.health.check_interval_s == 5.0
        assert config.bridge.restart.base_delay_s == 1.0
        assert config.bridge.restart.max_delay_s == 60.0
        assert config.bridge.restart.max_crash_before_fallback == 5

        assert config.usb.db_relative_path == "CUSTOM/db.db"
        assert config.usb.anlz_relative_path == "CUSTOM/ANLZ"


class TestPortValidation:
    """Port outside 1024-65535 falls back to default."""

    def test_port_too_low(self, tmp_path: Path):
        (tmp_path / "bridge.yaml").write_text(yaml.dump({"bridge": {"port": 80}}))
        config = load_config(config_dir=tmp_path)
        assert config.bridge.port == 17400

    def test_port_too_high(self, tmp_path: Path):
        (tmp_path / "bridge.yaml").write_text(yaml.dump({"bridge": {"port": 70000}}))
        config = load_config(config_dir=tmp_path)
        assert config.bridge.port == 17400

    def test_port_not_int(self, tmp_path: Path):
        (tmp_path / "bridge.yaml").write_text(yaml.dump({"bridge": {"port": "bad"}}))
        config = load_config(config_dir=tmp_path)
        assert config.bridge.port == 17400

    def test_valid_port(self, tmp_path: Path):
        (tmp_path / "bridge.yaml").write_text(yaml.dump({"bridge": {"port": 8080}}))
        config = load_config(config_dir=tmp_path)
        assert config.bridge.port == 8080


class TestAudioExtensionsLoaded:
    """Audio extensions from server.yaml are loaded correctly."""

    def test_custom_extensions(self, tmp_path: Path):
        (tmp_path / "server.yaml").write_text(yaml.dump({
            "server": {"audio_extensions": [".wav", ".opus", ".aac"]}
        }))
        config = load_config(config_dir=tmp_path)
        assert config.server.audio_extensions == [".wav", ".opus", ".aac"]

    def test_empty_extensions(self, tmp_path: Path):
        (tmp_path / "server.yaml").write_text(yaml.dump({
            "server": {"audio_extensions": []}
        }))
        config = load_config(config_dir=tmp_path)
        assert config.server.audio_extensions == []


class TestUsbConfigLoaded:
    """USB paths from usb.yaml are loaded correctly."""

    def test_custom_usb_paths(self, tmp_path: Path):
        (tmp_path / "usb.yaml").write_text(yaml.dump({
            "usb": {
                "db_relative_path": "CUSTOM/library.db",
                "anlz_relative_path": "CUSTOM/ANLZ_DIR",
            }
        }))
        config = load_config(config_dir=tmp_path)
        assert config.usb.db_relative_path == "CUSTOM/library.db"
        assert config.usb.anlz_relative_path == "CUSTOM/ANLZ_DIR"


class TestConfigDirMissing:
    """Missing config directory returns all defaults (no crash)."""

    def test_nonexistent_dir(self):
        config = load_config(config_dir=Path("/nonexistent/config/dir"))
        assert isinstance(config, ScueConfig)
        assert config.server.cors_origins == ["http://localhost:5173"]
        assert config.bridge.port == 17400


class TestMalformedYaml:
    """Malformed YAML files don't crash the loader."""

    def test_invalid_yaml(self, tmp_path: Path):
        (tmp_path / "bridge.yaml").write_text("{{invalid yaml content")
        config = load_config(config_dir=tmp_path)
        # Should fall back to defaults
        assert config.bridge.port == 17400

    def test_yaml_with_non_dict_root(self, tmp_path: Path):
        (tmp_path / "server.yaml").write_text("just a string")
        config = load_config(config_dir=tmp_path)
        assert config.server.cors_origins == ["http://localhost:5173"]
