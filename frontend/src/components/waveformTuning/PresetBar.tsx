/**
 * PresetBar — preset management controls for the waveform tuning page.
 *
 * Shows active preset name, save/save-as buttons, preset dropdown, delete.
 */

import { useState } from "react";
import type { WaveformPreset, WaveformRenderParams } from "../../types/waveformPreset";

interface Props {
  presets: WaveformPreset[];
  activePreset: WaveformPreset | null;
  currentPresetId: string | null;
  isDirty: boolean;
  onSave: (id: string, params: WaveformRenderParams) => void;
  onSaveAs: (name: string, params: WaveformRenderParams) => void;
  onLoadPreset: (preset: WaveformPreset) => void;
  onActivate: (id: string) => void;
  onDelete: (id: string) => void;
  currentParams: WaveformRenderParams;
}

export function PresetBar({
  presets,
  activePreset,
  currentPresetId,
  isDirty,
  onSave,
  onSaveAs,
  onLoadPreset,
  onActivate,
  onDelete,
  currentParams,
}: Props) {
  const [showSaveAs, setShowSaveAs] = useState(false);
  const [newName, setNewName] = useState("");
  const [showDropdown, setShowDropdown] = useState(false);

  const currentPreset = presets.find((p) => p.id === currentPresetId);
  const displayName = currentPreset?.name ?? activePreset?.name ?? "No preset";

  const handleSave = () => {
    if (currentPresetId) {
      onSave(currentPresetId, currentParams);
    }
  };

  const handleSaveAs = () => {
    if (newName.trim()) {
      onSaveAs(newName.trim(), currentParams);
      setNewName("");
      setShowSaveAs(false);
    }
  };

  return (
    <div className="flex items-center gap-3 bg-slate-800/50 rounded-lg px-4 py-2 flex-wrap">
      {/* Active indicator */}
      <div className="flex items-center gap-2 text-sm">
        <span className="text-slate-400">Preset:</span>
        <span className="text-white font-medium">{displayName}</span>
        {isDirty && (
          <span className="text-amber-400 text-xs">(unsaved)</span>
        )}
        {currentPreset && !currentPreset.isActive && (
          <button
            onClick={() => onActivate(currentPreset.id)}
            className="text-xs px-2 py-0.5 bg-cyan-600/30 text-cyan-400 rounded hover:bg-cyan-600/50"
          >
            Activate
          </button>
        )}
        {currentPreset?.isActive && (
          <span className="text-xs text-emerald-400">(active)</span>
        )}
      </div>

      <div className="flex-1" />

      {/* Save */}
      <button
        onClick={handleSave}
        disabled={!isDirty || !currentPresetId}
        className="text-xs px-3 py-1 bg-slate-700 text-white rounded hover:bg-slate-600 disabled:opacity-40 disabled:cursor-not-allowed"
      >
        Save
      </button>

      {/* Save As */}
      {showSaveAs ? (
        <div className="flex items-center gap-1">
          <input
            type="text"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="Preset name..."
            className="text-xs px-2 py-1 bg-slate-900 border border-slate-700 rounded text-white w-40"
            autoFocus
            onKeyDown={(e) => {
              if (e.key === "Enter") handleSaveAs();
              if (e.key === "Escape") setShowSaveAs(false);
            }}
          />
          <button
            onClick={handleSaveAs}
            disabled={!newName.trim()}
            className="text-xs px-2 py-1 bg-cyan-600 text-white rounded hover:bg-cyan-500 disabled:opacity-40"
          >
            Create
          </button>
          <button
            onClick={() => setShowSaveAs(false)}
            className="text-xs px-2 py-1 text-slate-400 hover:text-white"
          >
            Cancel
          </button>
        </div>
      ) : (
        <button
          onClick={() => setShowSaveAs(true)}
          className="text-xs px-3 py-1 bg-slate-700 text-white rounded hover:bg-slate-600"
        >
          Save As
        </button>
      )}

      {/* Preset Dropdown */}
      <div className="relative">
        <button
          onClick={() => setShowDropdown(!showDropdown)}
          className="text-xs px-3 py-1 bg-slate-700 text-white rounded hover:bg-slate-600"
        >
          Presets
        </button>
        {showDropdown && (
          <div className="absolute right-0 top-full mt-1 bg-slate-800 border border-slate-700 rounded shadow-lg z-20 min-w-48">
            {presets.map((p) => (
              <div
                key={p.id}
                className="flex items-center gap-2 px-3 py-1.5 hover:bg-slate-700 cursor-pointer text-sm"
                onClick={() => {
                  onLoadPreset(p);
                  setShowDropdown(false);
                }}
              >
                <span className={`flex-1 ${p.id === currentPresetId ? "text-cyan-400" : "text-white"}`}>
                  {p.name}
                </span>
                {p.isActive && (
                  <span className="text-xs text-emerald-400">active</span>
                )}
                {!p.isActive && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onDelete(p.id);
                    }}
                    className="text-xs text-red-400 hover:text-red-300 px-1"
                    title="Delete preset"
                  >
                    x
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
