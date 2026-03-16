import { useState } from "react";
import { useTracks } from "../api/tracks";
import { AnalyzePanel } from "../components/tracks/AnalyzePanel";
import { TrackTable } from "../components/tracks/TrackTable";
import { TrackToolbar } from "../components/tracks/TrackToolbar";

export function TracksPage() {
  const [search, setSearch] = useState("");
  const { data, isLoading, error } = useTracks({ limit: 1000 });

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
            total={data?.total ?? 0}
          />
          <TrackTable data={data?.tracks ?? []} globalFilter={search} />
        </>
      )}
    </div>
  );
}
