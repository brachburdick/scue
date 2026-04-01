import { useLibraryStore } from "../../stores/libraryStore";

export function ImportSettingsBar() {
  const importMode = useLibraryStore((s) => s.importMode);
  const setImportMode = useLibraryStore((s) => s.setImportMode);

  return (
    <div className="flex items-center gap-3 px-4 py-2 bg-gray-950 rounded border border-gray-800 text-sm">
      <span className="text-gray-400">Import mode:</span>
      <button
        onClick={() => setImportMode("metadata")}
        className={`px-3 py-1 rounded transition-colors ${
          importMode === "metadata"
            ? "bg-blue-600 text-white"
            : "bg-gray-800 text-gray-400 hover:bg-gray-700"
        }`}
      >
        Metadata only
      </button>
      <button
        onClick={() => setImportMode("metadata_analysis")}
        className={`px-3 py-1 rounded transition-colors ${
          importMode === "metadata_analysis"
            ? "bg-blue-600 text-white"
            : "bg-gray-800 text-gray-400 hover:bg-gray-700"
        }`}
      >
        Metadata + Base Analysis
      </button>
      <span className="text-gray-600 text-xs ml-2">
        {importMode === "metadata"
          ? "Fast import — pull metadata from source, skip audio analysis"
          : "Full import — metadata + waveform/BPM/key generation"}
      </span>
    </div>
  );
}
