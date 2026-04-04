"""Variant configuration loader for the Strata substep strategy system.

Loads config/strata_variants.yaml and provides typed access to variant
presets and per-strategy parameters.

Follows the same pattern as load_detector_config() in detectors/events.py.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Canonical substep IDs — must match keys in the YAML strategies section
SUBSTEP_IDS = ("transition_detection", "energy_trend", "fill_detection")


@dataclass
class VariantConfig:
    """Loaded variant configuration."""

    # Named presets: variant_name -> {substep_id: strategy_name}
    variants: dict[str, dict[str, str]] = field(default_factory=dict)

    # Available strategies per substep: substep_id -> {strategy_name: params_dict}
    strategies: dict[str, dict[str, dict]] = field(default_factory=dict)

    def resolve(
        self,
        variant: str = "default",
        overrides: dict[str, str] | None = None,
    ) -> dict[str, str]:
        """Resolve a full substep->strategy mapping for a variant.

        Starts from the named preset, then applies any per-substep overrides.

        Returns:
            Dict mapping substep_id to strategy_name.
        """
        base = dict(self.variants.get(variant, self.variants.get("default", {})))
        if overrides:
            for substep_id, strategy_name in overrides.items():
                if substep_id in SUBSTEP_IDS:
                    base[substep_id] = strategy_name
        return base

    def get_strategy_name(self, substep_id: str, variant: str = "default") -> str:
        """Get the strategy name for a substep in a given variant."""
        preset = self.variants.get(variant, self.variants.get("default", {}))
        return preset.get(substep_id, "")

    def get_params(self, substep_id: str, strategy_name: str) -> dict:
        """Get parameters for a specific strategy."""
        substep_strategies = self.strategies.get(substep_id, {})
        return dict(substep_strategies.get(strategy_name, {}))

    def available_strategies(self, substep_id: str) -> list[str]:
        """List available strategy names for a substep."""
        return list(self.strategies.get(substep_id, {}).keys())

    def variant_names(self) -> list[str]:
        """List all named variant presets."""
        return list(self.variants.keys())


_cached_config: VariantConfig | None = None
_cached_path: Path | None = None


def load_variant_config(config_path: str | Path | None = None) -> VariantConfig:
    """Load variant configuration from a YAML file.

    Args:
        config_path: Path to strata_variants.yaml. If None, uses the default
            config at config/strata_variants.yaml relative to the scue package.

    Returns:
        VariantConfig with all settings populated. Cached after first load.
    """
    global _cached_config, _cached_path

    import yaml

    if config_path is None:
        # __file__ = scue/layer1/strata/variant_config.py → .parent×4 = project root
        config_path = Path(__file__).parent.parent.parent.parent / "config" / "strata_variants.yaml"
    else:
        config_path = Path(config_path)

    # Return cached if same path
    if _cached_config is not None and _cached_path == config_path:
        return _cached_config

    if not config_path.exists():
        logger.warning("Variant config not found at %s, using defaults", config_path)
        _cached_config = _default_config()
        _cached_path = config_path
        return _cached_config

    try:
        raw = yaml.safe_load(config_path.read_text())
    except Exception as e:
        logger.warning("Failed to load variant config from %s: %s", config_path, e)
        _cached_config = _default_config()
        _cached_path = config_path
        return _cached_config

    config = VariantConfig(
        variants=raw.get("variants", {}),
        strategies=raw.get("strategies", {}),
    )
    _cached_config = config
    _cached_path = config_path
    logger.info(
        "Loaded variant config: %d presets, %d substeps",
        len(config.variants), len(config.strategies),
    )
    return config


def reload_variant_config() -> VariantConfig:
    """Force-reload the variant config (clears cache)."""
    global _cached_config, _cached_path
    path = _cached_path
    _cached_config = None
    _cached_path = None
    return load_variant_config(path)


def _default_config() -> VariantConfig:
    """Return hardcoded default config matching original behavior."""
    return VariantConfig(
        variants={
            "default": {
                "transition_detection": "energy_delta",
                "energy_trend": "slope_heuristic",
                "fill_detection": "onset_spike",
            },
        },
        strategies={
            "transition_detection": {
                "energy_delta": {"energy_threshold": 0.15},
            },
            "energy_trend": {
                "slope_heuristic": {
                    "window": 4,
                    "slope_threshold": 0.05,
                    "peak_ratio": 1.3,
                    "valley_ratio": 0.7,
                },
            },
            "fill_detection": {
                "onset_spike": {
                    "spike_ratio": 1.8,
                    "boundary_window_s": 5.0,
                },
            },
        },
    )
