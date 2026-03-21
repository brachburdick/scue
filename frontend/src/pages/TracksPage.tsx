import { useState, useCallback } from "react";
import { useTracks } from "../api/tracks";
import { useFolderContents } from "../api/analyze";
import { useFolderStore } from "../stores/folderStore";
import { useAnalyzeStore } from "../stores/analyzeStore";
import { AnalyzePanel } from "../components/tracks/AnalyzePanel";
import { TrackTable } from "../components/tracks/TrackTable";
import { TrackToolbar } from "../components/tracks/TrackToolbar";

export function TracksPage() {
  const [search, setSearch] = useState("");
  const { viewMode, currentFolder } = useFolderStore();
  const analyzeStore = useAnalyzeStore();

  const handleAnalyzeFolder = useCallback(
    (folderPath: string) => {
      // Pre-fill the analyze panel with this folder as destination
      analyzeStore.setDestinationFolder(folderPath);
      // Scroll to top so user sees the analyze panel
      window.scrollTo({ top: 0, behavior: "smooth" });
    },
    [analyzeStore],
  );

  // Flat view: load all tracks
  const flatQuery = useTracks({ limit: 1000 });

  // Directory view: load folder contents
  const dirQuery = useFolderContents(currentFolder, viewMode === "directory");

  const isLoading = viewMode === "flat" ? flatQuery.isLoading : dirQuery.isLoading;
  const error = viewMode === "flat" ? flatQuery.error : dirQuery.error;

  const tracks =
    viewMode === "flat"
      ? flatQuery.data?.tracks ?? []
      : dirQuery.data?.tracks ?? [];

  const folders = viewMode === "directory" ? dirQuery.data?.folders ?? [] : [];

  const total =
    viewMode === "flat"
      ? flatQuery.data?.total ?? 0
      : (dirQuery.data?.track_count ?? 0) + (dirQuery.data?.folders?.length ?? 0);

  return (
    <div>
      <h1 className="text-xl font-semibold mb-4">Tracks</h1>
      <AnalyzePanel />

      {error ? (
        <p className="text-red-400 text-sm">
          Failed to load tracks: {(error as Error).message}
        </p>
      ) : isLoading ? (
        <p className="text-gray-500 text-sm">Loading tracks...</p>
      ) : (
        <>
          <TrackToolbar
            search={search}
            onSearchChange={setSearch}
            total={total}
          />
          <TrackTable
            data={tracks}
            globalFilter={search}
            folders={folders}
            onAnalyzeFolder={handleAnalyzeFolder}
          />
        </>
      )}
    </div>
  );
}
