"""Per-tier, per-source Strata storage.

Each tier + analysis source combination gets its own JSON file:
  strata/{fingerprint}.{tier}.{source}.json

For backward compatibility, files without a source suffix are treated as
source="analysis":
  strata/{fingerprint}.quick.json  →  equivalent to .quick.analysis.json

Standard tier does NOT overwrite quick tier data. Different sources
(analysis, pioneer_enriched, pioneer_reanalyzed) coexist independently.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path

from .models import ArrangementFormula, formula_from_dict, formula_to_dict

logger = logging.getLogger(__name__)

VALID_TIERS = ("quick", "standard", "deep", "live", "live_offline", "hybrid")
VALID_SOURCES = ("analysis", "pioneer_enriched", "pioneer_reanalyzed", "pioneer_live")
DEFAULT_SOURCE = "analysis"
DEFAULT_VARIANT = "default"


class StrataStore:
    """File-based storage for per-tier, per-source arrangement formulas."""

    def __init__(self, strata_dir: Path) -> None:
        self._dir = strata_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    @property
    def base_dir(self) -> Path:
        return self._dir

    def _path(
        self, fingerprint: str, tier: str,
        source: str = DEFAULT_SOURCE, variant: str = DEFAULT_VARIANT,
    ) -> Path:
        """Get the file path for a tier + source + variant combination.

        Default variant: {fp}.{tier}.{source}.json  (backward compat)
        Named variant:   {fp}.{tier}.{source}.{variant}.json
        """
        if variant and variant != DEFAULT_VARIANT:
            return self._dir / f"{fingerprint}.{tier}.{source}.{variant}.json"
        return self._dir / f"{fingerprint}.{tier}.{source}.json"

    def _legacy_path(self, fingerprint: str, tier: str) -> Path:
        """Legacy path without source suffix: {fp}.{tier}.json"""
        return self._dir / f"{fingerprint}.{tier}.json"

    def save(
        self, formula: ArrangementFormula, tier: str,
        source: str = DEFAULT_SOURCE, variant: str = DEFAULT_VARIANT,
    ) -> Path:
        """Save an arrangement formula for a specific tier, source, and variant.

        Returns the path written to.
        """
        if tier not in VALID_TIERS:
            raise ValueError(f"Invalid tier: {tier!r} (expected one of {VALID_TIERS})")
        if source not in VALID_SOURCES:
            raise ValueError(f"Invalid source: {source!r} (expected one of {VALID_SOURCES})")
        path = self._path(formula.fingerprint, tier, source, variant)
        data = formula_to_dict(formula)
        fd, tmp_path = tempfile.mkstemp(dir=self._dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(json.dumps(data, indent=2) + "\n")
            os.replace(tmp_path, path)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        logger.info(
            "Saved strata %s/%s for %s (%.1fs compute)",
            tier, source, formula.fingerprint[:16], formula.compute_time_seconds,
        )
        return path

    def load(
        self, fingerprint: str, tier: str,
        source: str = DEFAULT_SOURCE, variant: str = DEFAULT_VARIANT,
    ) -> ArrangementFormula | None:
        """Load a specific tier + source + variant arrangement formula.

        Falls back to legacy path ({fp}.{tier}.json) when source is "analysis"
        and variant is "default" and the source-qualified file doesn't exist.
        """
        if tier not in VALID_TIERS:
            raise ValueError(f"Invalid tier: {tier!r} (expected one of {VALID_TIERS})")

        # Try full path (with variant) first
        path = self._path(fingerprint, tier, source, variant)
        if not path.exists() and source == DEFAULT_SOURCE and variant == DEFAULT_VARIANT:
            # Backward compat: try legacy path without source suffix
            path = self._legacy_path(fingerprint, tier)
        if not path.exists():
            return None

        try:
            data = json.loads(path.read_text())
            return formula_from_dict(data)
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Failed to load strata %s/%s for %s: %s", tier, source, fingerprint[:16], e)
            return None

    def load_all(
        self, fingerprint: str,
    ) -> dict[str, dict[str, dict[str, ArrangementFormula]]]:
        """Load all available tier + source + variant results for a track.

        Returns a nested dict: {tier: {source: {variant: formula}}}.
        For backward compat, the default variant is always keyed as "default".
        """
        results: dict[str, dict[str, dict[str, ArrangementFormula]]] = {}

        # Scan all matching files for this fingerprint
        for path in sorted(self._dir.glob(f"{fingerprint}.*.json")):
            parts = path.stem.split(".")
            if len(parts) < 2:
                continue

            fp = parts[0]
            if fp != fingerprint:
                continue

            if len(parts) == 2:
                # Legacy: {fp}.{tier}.json
                tier, source, variant = parts[1], DEFAULT_SOURCE, DEFAULT_VARIANT
            elif len(parts) == 3:
                # Source-qualified: {fp}.{tier}.{source}.json
                tier, source, variant = parts[1], parts[2], DEFAULT_VARIANT
            elif len(parts) == 4:
                # Variant-qualified: {fp}.{tier}.{source}.{variant}.json
                tier, source, variant = parts[1], parts[2], parts[3]
            else:
                continue

            if tier not in VALID_TIERS:
                continue
            if source not in VALID_SOURCES:
                continue

            formula = self._load_from_path(path)
            if formula is None:
                continue

            results.setdefault(tier, {}).setdefault(source, {})[variant] = formula

        return results

    def load_all_flat(self, fingerprint: str) -> dict[str, dict[str, ArrangementFormula]]:
        """Load all results, flattened to {tier: {source: formula}} (default variant only).

        Backward-compatible convenience method — ignores non-default variants.
        """
        all_results = self.load_all(fingerprint)
        flat: dict[str, dict[str, ArrangementFormula]] = {}
        for tier, sources in all_results.items():
            for source, variants in sources.items():
                if DEFAULT_VARIANT in variants:
                    flat.setdefault(tier, {})[source] = variants[DEFAULT_VARIANT]
        return flat

    def _load_from_path(self, path: Path) -> ArrangementFormula | None:
        """Load a formula from a specific file path."""
        try:
            data = json.loads(path.read_text())
            return formula_from_dict(data)
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Failed to load strata from %s: %s", path.name, e)
            return None

    def load_tier_flat(self, fingerprint: str, tier: str) -> dict[str, ArrangementFormula]:
        """Load all sources for a single tier (default variant only). Returns {source: formula}."""
        results: dict[str, ArrangementFormula] = {}
        for source in VALID_SOURCES:
            formula = self.load(fingerprint, tier, source, DEFAULT_VARIANT)
            if formula is not None:
                results[source] = formula
        return results

    def list_tracks(self) -> list[dict]:
        """List all fingerprints that have strata data, with tier, source, and variant info."""
        tracks: dict[str, dict] = {}
        for path in sorted(self._dir.glob("*.json")):
            parts = path.stem.split(".")
            if len(parts) == 2:
                # Legacy: {fp}.{tier}.json
                fp, tier = parts
                source = DEFAULT_SOURCE
                variant = DEFAULT_VARIANT
            elif len(parts) == 3:
                # Source-qualified: {fp}.{tier}.{source}.json
                fp, tier, source = parts
                variant = DEFAULT_VARIANT
            elif len(parts) == 4:
                # Variant-qualified: {fp}.{tier}.{source}.{variant}.json
                fp, tier, source, variant = parts
            else:
                continue

            if tier not in VALID_TIERS:
                continue
            if source not in VALID_SOURCES:
                continue

            if fp not in tracks:
                tracks[fp] = {"fingerprint": fp, "tiers": {}, "variants": set()}
            if tier not in tracks[fp]["tiers"]:
                tracks[fp]["tiers"][tier] = []
            if source not in tracks[fp]["tiers"][tier]:
                tracks[fp]["tiers"][tier].append(source)
            tracks[fp]["variants"].add(variant)

        # Convert sets to lists for JSON serialization
        for t in tracks.values():
            t["variants"] = sorted(t["variants"])

        return list(tracks.values())

    def delete(
        self, fingerprint: str, tier: str,
        source: str = DEFAULT_SOURCE, variant: str = DEFAULT_VARIANT,
    ) -> bool:
        """Delete a specific tier + source + variant's data. Returns True if file existed."""
        path = self._path(fingerprint, tier, source, variant)
        if path.exists():
            path.unlink()
            logger.info("Deleted strata %s/%s/%s for %s", tier, source, variant, fingerprint[:16])
            return True
        # Also check legacy path
        if source == DEFAULT_SOURCE and variant == DEFAULT_VARIANT:
            legacy = self._legacy_path(fingerprint, tier)
            if legacy.exists():
                legacy.unlink()
                logger.info("Deleted strata %s (legacy) for %s", tier, fingerprint[:16])
                return True
        return False
