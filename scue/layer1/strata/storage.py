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
from pathlib import Path

from .models import ArrangementFormula, formula_from_dict, formula_to_dict

logger = logging.getLogger(__name__)

VALID_TIERS = ("quick", "standard", "deep")
VALID_SOURCES = ("analysis", "pioneer_enriched", "pioneer_reanalyzed")
DEFAULT_SOURCE = "analysis"


class StrataStore:
    """File-based storage for per-tier, per-source arrangement formulas."""

    def __init__(self, strata_dir: Path) -> None:
        self._dir = strata_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    @property
    def base_dir(self) -> Path:
        return self._dir

    def _path(self, fingerprint: str, tier: str, source: str = DEFAULT_SOURCE) -> Path:
        """Get the file path for a tier + source combination.

        Source-qualified: {fp}.{tier}.{source}.json
        """
        return self._dir / f"{fingerprint}.{tier}.{source}.json"

    def _legacy_path(self, fingerprint: str, tier: str) -> Path:
        """Legacy path without source suffix: {fp}.{tier}.json"""
        return self._dir / f"{fingerprint}.{tier}.json"

    def save(self, formula: ArrangementFormula, tier: str, source: str = DEFAULT_SOURCE) -> Path:
        """Save an arrangement formula for a specific tier and source.

        Returns the path written to.
        """
        if tier not in VALID_TIERS:
            raise ValueError(f"Invalid tier: {tier!r} (expected one of {VALID_TIERS})")
        if source not in VALID_SOURCES:
            raise ValueError(f"Invalid source: {source!r} (expected one of {VALID_SOURCES})")
        path = self._path(formula.fingerprint, tier, source)
        data = formula_to_dict(formula)
        path.write_text(json.dumps(data, indent=2) + "\n")
        logger.info(
            "Saved strata %s/%s for %s (%.1fs compute)",
            tier, source, formula.fingerprint[:16], formula.compute_time_seconds,
        )
        return path

    def load(
        self, fingerprint: str, tier: str, source: str = DEFAULT_SOURCE,
    ) -> ArrangementFormula | None:
        """Load a specific tier + source arrangement formula.

        Falls back to legacy path ({fp}.{tier}.json) when source is "analysis"
        and the source-qualified file doesn't exist.
        """
        if tier not in VALID_TIERS:
            raise ValueError(f"Invalid tier: {tier!r} (expected one of {VALID_TIERS})")

        # Try source-qualified path first
        path = self._path(fingerprint, tier, source)
        if not path.exists() and source == DEFAULT_SOURCE:
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

    def load_all(self, fingerprint: str) -> dict[str, dict[str, ArrangementFormula]]:
        """Load all available tier + source results for a track.

        Returns a nested dict: {tier: {source: formula}}.
        """
        results: dict[str, dict[str, ArrangementFormula]] = {}
        for tier in VALID_TIERS:
            tier_results: dict[str, ArrangementFormula] = {}
            for source in VALID_SOURCES:
                formula = self.load(fingerprint, tier, source)
                if formula is not None:
                    tier_results[source] = formula
            if tier_results:
                results[tier] = tier_results
        return results

    def load_tier_flat(self, fingerprint: str, tier: str) -> dict[str, ArrangementFormula]:
        """Load all sources for a single tier. Returns {source: formula}."""
        results: dict[str, ArrangementFormula] = {}
        for source in VALID_SOURCES:
            formula = self.load(fingerprint, tier, source)
            if formula is not None:
                results[source] = formula
        return results

    def list_tracks(self) -> list[dict]:
        """List all fingerprints that have strata data, with tier and source info."""
        tracks: dict[str, dict] = {}
        for path in sorted(self._dir.glob("*.json")):
            parts = path.stem.split(".")
            if len(parts) == 2:
                # Legacy: {fp}.{tier}.json
                fp, tier = parts
                source = DEFAULT_SOURCE
            elif len(parts) == 3:
                # Source-qualified: {fp}.{tier}.{source}.json
                fp, tier, source = parts
            else:
                continue

            if tier not in VALID_TIERS:
                continue
            if source not in VALID_SOURCES:
                continue

            if fp not in tracks:
                tracks[fp] = {"fingerprint": fp, "tiers": {}}
            if tier not in tracks[fp]["tiers"]:
                tracks[fp]["tiers"][tier] = []
            if source not in tracks[fp]["tiers"][tier]:
                tracks[fp]["tiers"][tier].append(source)

        return list(tracks.values())

    def delete(self, fingerprint: str, tier: str, source: str = DEFAULT_SOURCE) -> bool:
        """Delete a specific tier + source's data. Returns True if file existed."""
        path = self._path(fingerprint, tier, source)
        if path.exists():
            path.unlink()
            logger.info("Deleted strata %s/%s for %s", tier, source, fingerprint[:16])
            return True
        # Also check legacy path
        if source == DEFAULT_SOURCE:
            legacy = self._legacy_path(fingerprint, tier)
            if legacy.exists():
                legacy.unlink()
                logger.info("Deleted strata %s (legacy) for %s", tier, fingerprint[:16])
                return True
        return False
