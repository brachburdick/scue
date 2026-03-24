"""REST API for waveform rendering presets.

Presets are stored in config/waveform-presets.yaml and served via these endpoints.
All rendering params are applied at frontend render time — the stored RGBWaveform
data is not modified.
"""

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/waveform-presets", tags=["waveform-presets"])

_presets_path: Path | None = None


# --- Pydantic models ---

class WaveformRenderParams(BaseModel):
    normalization: str = "global"
    lowGain: float = 1.0
    midGain: float = 1.0
    highGain: float = 1.0
    frequencyWeighting: str = "none"
    lowCrossover: int = 200
    highCrossover: int = 2500
    amplitudeScale: str = "linear"
    gamma: float = 1.0
    logStrength: int = 10
    noiseFloor: float = 0.001
    peakNormalize: bool = True
    colorMode: str = "rgb_blend"
    lowColor: str = "#ff0000"
    midColor: str = "#00ff00"
    highColor: str = "#0000ff"
    saturation: float = 1.0
    brightness: float = 1.0
    minBrightness: float = 0.0


class PresetCreate(BaseModel):
    name: str
    params: WaveformRenderParams


class PresetUpdate(BaseModel):
    name: str | None = None
    params: WaveformRenderParams | None = None


# --- YAML helpers ---

def _load_presets_file() -> dict[str, Any]:
    """Load the presets YAML file."""
    if _presets_path is None or not _presets_path.exists():
        return {"active_preset": "default", "presets": []}
    with open(_presets_path) as f:
        data = yaml.safe_load(f) or {}
    return data


def _save_presets_file(data: dict[str, Any]) -> None:
    """Save the presets YAML file."""
    if _presets_path is None:
        raise HTTPException(status_code=500, detail="Presets path not configured")
    _presets_path.parent.mkdir(parents=True, exist_ok=True)
    with open(_presets_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


def _preset_to_response(preset: dict[str, Any], active_id: str) -> dict[str, Any]:
    """Convert a YAML preset dict to an API response dict."""
    return {
        "id": preset["id"],
        "name": preset["name"],
        "isActive": preset["id"] == active_id,
        "createdAt": preset.get("created_at", ""),
        "updatedAt": preset.get("updated_at", ""),
        "params": preset["params"],
    }


# --- Init ---

def init_waveform_presets_api(presets_path: Path) -> None:
    """Initialize the waveform presets API with the config file path."""
    global _presets_path
    _presets_path = presets_path
    logger.info("Waveform presets API initialized: %s", presets_path)


# --- Endpoints ---

@router.get("")
async def list_presets() -> dict[str, Any]:
    """List all presets with active flag."""
    data = _load_presets_file()
    active_id = data.get("active_preset", "default")
    presets = data.get("presets", [])
    return {
        "activePresetId": active_id,
        "presets": [_preset_to_response(p, active_id) for p in presets],
    }


@router.get("/active")
async def get_active_preset() -> dict[str, Any]:
    """Get the currently active preset."""
    data = _load_presets_file()
    active_id = data.get("active_preset", "default")
    for p in data.get("presets", []):
        if p["id"] == active_id:
            return _preset_to_response(p, active_id)
    raise HTTPException(status_code=404, detail="Active preset not found")


@router.post("")
async def create_preset(body: PresetCreate) -> dict[str, Any]:
    """Create a new preset."""
    data = _load_presets_file()
    now = datetime.now(timezone.utc).isoformat()
    new_preset = {
        "id": str(uuid.uuid4())[:8],
        "name": body.name,
        "created_at": now,
        "updated_at": now,
        "params": body.params.model_dump(),
    }
    data.setdefault("presets", []).append(new_preset)
    _save_presets_file(data)
    active_id = data.get("active_preset", "default")
    return _preset_to_response(new_preset, active_id)


@router.put("/{preset_id}")
async def update_preset(preset_id: str, body: PresetUpdate) -> dict[str, Any]:
    """Update a preset's params or name."""
    data = _load_presets_file()
    for p in data.get("presets", []):
        if p["id"] == preset_id:
            if body.name is not None:
                p["name"] = body.name
            if body.params is not None:
                p["params"] = body.params.model_dump()
            p["updated_at"] = datetime.now(timezone.utc).isoformat()
            _save_presets_file(data)
            active_id = data.get("active_preset", "default")
            return _preset_to_response(p, active_id)
    raise HTTPException(status_code=404, detail="Preset not found")


@router.delete("/{preset_id}")
async def delete_preset(preset_id: str) -> dict[str, str]:
    """Delete a preset. Cannot delete the active preset."""
    data = _load_presets_file()
    active_id = data.get("active_preset", "default")
    if preset_id == active_id:
        raise HTTPException(status_code=400, detail="Cannot delete the active preset")
    presets = data.get("presets", [])
    original_count = len(presets)
    data["presets"] = [p for p in presets if p["id"] != preset_id]
    if len(data["presets"]) == original_count:
        raise HTTPException(status_code=404, detail="Preset not found")
    _save_presets_file(data)
    return {"status": "deleted"}


@router.post("/{preset_id}/activate")
async def activate_preset(preset_id: str) -> dict[str, Any]:
    """Set a preset as the active one."""
    data = _load_presets_file()
    found = any(p["id"] == preset_id for p in data.get("presets", []))
    if not found:
        raise HTTPException(status_code=404, detail="Preset not found")
    data["active_preset"] = preset_id
    _save_presets_file(data)
    for p in data["presets"]:
        if p["id"] == preset_id:
            return _preset_to_response(p, preset_id)
    raise HTTPException(status_code=404, detail="Preset not found")
