import { useState, useMemo, useCallback } from "react";
import { useMasterDbDetect, useMasterDbScan, useMasterDbIngest, useMasterDbPlaylists } from "../../api/ingestion";
import { useJobStatus } from "../../api/analyze";
import { useBridgeStore } from "../../stores/bridgeStore";
import { useLibraryStore } from "../../stores/libraryStore";
import { RekordboxTreeView } from "../library/RekordboxTreeView";
import type { MasterDbScanResponse, MasterDbIngestResponse } from "../../types/ingestion";
import type { ImportMode } from "../../types/library";

type Phase = "detect" | "scan" | "review" | "ingesting" | "done";
type ViewMode = "flat" | "tree";

/** Unified track row for the table — merges matched + importable tracks. */
interface RekordboxTrackRow {
  title: string;
  artist: string;
  bpm: number;
  phrases: number;
  inScue: boolean;
  fingerprint?: string;
  audio_path?: string;
  rekordbox_id?: number;
}

interface RekordboxTabProps {
  importMode?: ImportMode;
}

function Stat({ label, value, muted }: { label: string; value: number; muted?: boolean }) {
  return (
    <div className="rounded bg-gray-800/50 px-3 py-2">
      <div className={`text-lg font-semibold ${muted ? "text-gray-500" : "text-gray-200"}`}>{value}</div>
      <div className="text-xs text-gray-500">{label}</div>
    </div>
  );
}

function ProgressPanel({ jobId }: { jobId: string }) {
  const { data: job } = useJobStatus(jobId);
  if (!job) return <div className="text-sm text-gray-500 animate-pulse">Starting analysis...</div>;

  const pct = job.total > 0 ? Math.round((job.completed / job.total) * 100) : 0;
  const isDone = job.status === "complete" || job.status === "complete_with_errors";

  return (
    <div className="space-y-3">
      <div>
        <div className="flex justify-between text-xs text-gray-400 mb-1">
          <span>{isDone ? "Complete" : `Analyzing: ${job.current_file ?? "..."}`}</span>
          <span>{job.completed}/{job.total} ({pct}%)</span>
        </div>
        <div className="w-full bg-gray-800 rounded-full h-2">
          <div
            className={`h-2 rounded-full transition-all ${isDone ? "bg-green-500" : "bg-blue-500"}`}
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>
      {!isDone && job.current_step_name && (
        <div>
          <div className="flex justify-between text-xs text-gray-500 mb-1">
            <span>{job.current_step_name}</span>
            <span>{job.current_step}/{job.total_steps}</span>
          </div>
          <div className="w-full bg-gray-800 rounded-full h-1">
            <div
              className="h-1 rounded-full bg-cyan-500 transition-all"
              style={{ width: `${job.total_steps > 0 ? (job.current_step / job.total_steps) * 100 : 0}%` }}
            />
          </div>
        </div>
      )}
      {job.failed > 0 && (
        <div className="text-xs text-red-400">{job.failed} file{job.failed !== 1 ? "s" : ""} failed</div>
      )}
      {isDone && (
        <div className="text-sm text-green-400">
          Analysis complete: {job.completed} succeeded{job.failed > 0 ? `, ${job.failed} failed` : ""}
        </div>
      )}
    </div>
  );
}

export function RekordboxTab({ importMode: importModeProp }: RekordboxTabProps = {}) {
  const isStartingUp = useBridgeStore((s) => s.isStartingUp);
  const storeImportMode = useLibraryStore((s) => s.importMode);
  const importMode = importModeProp ?? storeImportMode;

  const [phase, setPhase] = useState<Phase>("detect");
  const [scanResult, setScanResult] = useState<MasterDbScanResponse | null>(null);
  const [ingestResult, setIngestResult] = useState<MasterDbIngestResponse | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>("flat");
  const [search, setSearch] = useState("");
  const [showImported, setShowImported] = useState(false);
  const [selectedTracks, setSelectedTracks] = useState<Set<number>>(new Set());

  // Playlist tree state
  const [selectedPlaylistId, setSelectedPlaylistId] = useState<number | null>(null);
  const [playlistTrackIds, setPlaylistTrackIds] = useState<number[]>([]);

  const { data: detected, isLoading: detecting, error: detectError } = useMasterDbDetect(!isStartingUp);
  const { data: playlistData } = useMasterDbPlaylists(!!detected && phase !== "detect");
  const scanMutation = useMasterDbScan();
  const ingestMutation = useMasterDbIngest();

  // Build unified track list from scan results
  const allTracks = useMemo<RekordboxTrackRow[]>(() => {
    if (!scanResult) return [];
    const rows: RekordboxTrackRow[] = [
      ...scanResult.matched_tracks.map((t) => ({
        title: t.title,
        artist: t.artist,
        bpm: t.bpm,
        phrases: t.phrases,
        inScue: true,
        fingerprint: t.fingerprint,
      })),
      ...scanResult.importable_tracks.map((t, i) => ({
        title: t.title,
        artist: t.artist,
        bpm: t.bpm,
        phrases: t.phrases,
        inScue: false,
        audio_path: t.audio_path,
        rekordbox_id: i, // synthetic ID for selection
      })),
    ];
    return rows;
  }, [scanResult]);

  // Filter tracks
  const filteredTracks = useMemo(() => {
    let result = allTracks;

    // Filter by SCUE status
    if (!showImported) {
      result = result.filter((t) => !t.inScue);
    }

    // Filter by search text
    if (search) {
      const q = search.toLowerCase();
      result = result.filter(
        (t) => t.title.toLowerCase().includes(q) || t.artist.toLowerCase().includes(q),
      );
    }

    // Filter by selected playlist (tree view)
    if (selectedPlaylistId !== null && playlistTrackIds.length > 0) {
      // Cross-reference: playlist track IDs are rekordbox content IDs
      // We don't have rekordbox IDs on all rows yet, so this is a best-effort filter
      // For now, playlist filtering works with the flat view search
    }

    return result;
  }, [allTracks, showImported, search, selectedPlaylistId, playlistTrackIds]);

  const handleScan = () => {
    scanMutation.mutate(undefined, {
      onSuccess: (data) => { setScanResult(data); setPhase("review"); },
    });
    setPhase("scan");
  };

  const handleIngest = useCallback(() => {
    const skipWaveform = importMode === "metadata";
    ingestMutation.mutate({ skip_waveform: skipWaveform }, {
      onSuccess: (data) => {
        setIngestResult(data);
        setPhase(data.job_id ? "ingesting" : "done");
      },
    });
  }, [importMode, ingestMutation]);

  const toggleTrack = useCallback((idx: number) => {
    setSelectedTracks((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  }, []);

  const toggleAll = useCallback(() => {
    if (selectedTracks.size === filteredTracks.length) {
      setSelectedTracks(new Set());
    } else {
      setSelectedTracks(new Set(filteredTracks.map((_, i) => i)));
    }
  }, [selectedTracks.size, filteredTracks]);

  const handlePlaylistSelect = useCallback((id: number | null, trackIds: number[]) => {
    setSelectedPlaylistId(id);
    setPlaylistTrackIds(trackIds);
  }, []);

  if (isStartingUp) return <div className="text-gray-500 text-sm animate-pulse">Connecting...</div>;
  if (detecting) return <div className="text-gray-500 text-sm">Detecting rekordbox...</div>;
  if (detectError || !detected) {
    return (
      <div className="rounded border border-red-800 bg-red-900/20 p-4">
        <p className="text-red-400 text-sm font-medium">No rekordbox database found</p>
        <p className="text-red-300/60 text-xs mt-1 font-mono">
          master.db not found at ~/Library/Pioneer/rekordbox/master.db
        </p>
        <p className="text-gray-500 text-xs mt-2">
          Check that Rekordbox is installed and has been opened at least once.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Detection header */}
      <div className="rounded border border-gray-800 bg-gray-900/50 p-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-gray-300">
              rekordbox collection found
              <span className="text-gray-500 text-xs ml-2">({detected.size_mb} MB)</span>
            </p>
            <p className="text-xs text-gray-500 mt-0.5 font-mono">{detected.path}</p>
          </div>
          {phase === "detect" && (
            <button onClick={handleScan} className="px-4 py-2 text-sm font-medium rounded bg-blue-600 hover:bg-blue-500 text-white transition-colors">
              Scan Collection
            </button>
          )}
        </div>
        {phase === "scan" && scanMutation.isPending && (
          <div className="mt-3">
            <div className="text-xs text-gray-500 mb-1">Scanning rekordbox collection...</div>
            <div className="w-full bg-gray-800 rounded-full h-1.5">
              <div className="h-1.5 rounded-full bg-blue-500 animate-pulse w-2/3" />
            </div>
          </div>
        )}
        {scanMutation.isError && (
          <div className="mt-2 rounded border border-red-800 bg-red-900/20 p-2">
            <p className="text-red-400 text-xs">Scan failed: {scanMutation.error.message}</p>
          </div>
        )}
      </div>

      {scanResult && phase !== "detect" && (
        <div className="space-y-4">
          {/* Stats */}
          <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
            <Stat label="Tracks with audio" value={scanResult.with_audio} />
            <Stat label="With phrase analysis" value={scanResult.with_anlz} />
            <Stat label="Already in SCUE" value={scanResult.matched_to_scue} />
            <Stat label="Sidecars created" value={scanResult.sidecars_created} />
          </div>

          {/* Action bar */}
          {phase === "review" && (
            <div className="flex items-center justify-between rounded border border-gray-800 bg-gray-900/50 p-3">
              <div className="text-sm text-gray-300">
                <span className="font-medium text-blue-400">{scanResult.with_audio - scanResult.matched_to_scue}</span>{" "}
                new tracks ready to import
              </div>
              <div className="flex items-center gap-3">
                <button onClick={handleScan} disabled={scanMutation.isPending} className="px-3 py-1.5 text-xs font-medium rounded bg-gray-800 hover:bg-gray-700 text-gray-300 transition-colors">
                  Rescan
                </button>
                <button
                  onClick={handleIngest}
                  disabled={ingestMutation.isPending}
                  className="px-4 py-2 text-sm font-medium rounded bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white transition-colors"
                >
                  {ingestMutation.isPending
                    ? "Starting..."
                    : `Import ${scanResult.with_audio - scanResult.matched_to_scue} Tracks`}
                </button>
              </div>
            </div>
          )}

          {/* Ingest stats */}
          {ingestResult && (
            <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-5">
              <Stat label="In rekordbox" value={ingestResult.total_in_rekordbox} />
              <Stat label="Already in SCUE" value={ingestResult.already_in_scue} />
              <Stat label="Queued" value={ingestResult.queued_for_analysis} />
              <Stat label="Sidecars created" value={ingestResult.sidecars_created} />
              <Stat label="No ANLZ" value={ingestResult.sidecars_skipped} muted />
            </div>
          )}

          {phase === "ingesting" && ingestResult?.job_id && <ProgressPanel jobId={ingestResult.job_id} />}

          {/* Track table toolbar */}
          <div className="flex items-center gap-3 flex-wrap">
            {/* View mode toggle */}
            <div className="flex items-center rounded border border-gray-700 overflow-hidden">
              <button
                onClick={() => setViewMode("flat")}
                className={`px-3 py-1 text-xs transition-colors ${
                  viewMode === "flat" ? "bg-gray-700 text-white" : "bg-gray-900 text-gray-400 hover:text-gray-200"
                }`}
              >
                Flat
              </button>
              <button
                onClick={() => setViewMode("tree")}
                className={`px-3 py-1 text-xs transition-colors ${
                  viewMode === "tree" ? "bg-gray-700 text-white" : "bg-gray-900 text-gray-400 hover:text-gray-200"
                }`}
              >
                Tree
              </button>
            </div>

            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Filter tracks..."
              className="flex-1 min-w-40 px-3 py-1 text-xs rounded border border-gray-700 bg-gray-800 text-gray-300 placeholder-gray-500 focus:outline-none focus:border-blue-500"
            />

            <label className="flex items-center gap-1.5 text-xs text-gray-400 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={showImported}
                onChange={() => setShowImported((v) => !v)}
                className="accent-blue-500"
              />
              Show imported
            </label>

            <label className="flex items-center gap-1.5 text-xs text-gray-400 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={selectedTracks.size === filteredTracks.length && filteredTracks.length > 0}
                onChange={toggleAll}
                className="accent-blue-500"
              />
              All ({filteredTracks.length})
            </label>
          </div>

          {/* Content area */}
          <div className={viewMode === "tree" ? "grid grid-cols-[240px_1fr] gap-4" : ""}>
            {/* Tree sidebar */}
            {viewMode === "tree" && playlistData && (
              <RekordboxTreeView
                playlists={playlistData.playlists}
                selectedPlaylistId={selectedPlaylistId}
                onSelectPlaylist={handlePlaylistSelect}
              />
            )}

            {/* Track table */}
            <div className="overflow-auto rounded border border-gray-800" style={{ maxHeight: 400 }}>
              <table className="w-full text-sm">
                <thead className="sticky top-0 z-10">
                  <tr className="border-b border-gray-800 bg-gray-900">
                    <th className="px-2 py-2 w-8">
                      <span className="sr-only">Select</span>
                    </th>
                    <th className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-gray-400">Title</th>
                    <th className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-gray-400">Artist</th>
                    <th className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-gray-400 w-16">BPM</th>
                    <th className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-gray-400 w-20">Phrases</th>
                    <th className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-gray-400 w-24">SCUE</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredTracks.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="px-3 py-8 text-center text-gray-500">
                        {allTracks.length === 0 ? "No tracks found" : "No tracks match the current filters"}
                      </td>
                    </tr>
                  ) : (
                    filteredTracks.map((t, i) => (
                      <tr
                        key={`${t.title}-${i}`}
                        className={`border-b border-gray-800/50 cursor-pointer transition-colors ${
                          selectedTracks.has(i) ? "bg-blue-900/20" : "hover:bg-gray-800/30"
                        }`}
                        onClick={() => toggleTrack(i)}
                      >
                        <td className="px-2 py-1.5 text-center">
                          <input
                            type="checkbox"
                            checked={selectedTracks.has(i)}
                            onChange={() => toggleTrack(i)}
                            onClick={(e) => e.stopPropagation()}
                            className="accent-blue-500"
                          />
                        </td>
                        <td className="px-3 py-1.5 text-gray-300 truncate max-w-[250px]" title={t.title}>{t.title}</td>
                        <td className="px-3 py-1.5 text-gray-400 truncate max-w-[180px]">{t.artist || "-"}</td>
                        <td className="px-3 py-1.5 text-gray-400 tabular-nums">{t.bpm ? t.bpm.toFixed(0) : "-"}</td>
                        <td className="px-3 py-1.5 text-gray-500 tabular-nums">{t.phrases || "-"}</td>
                        <td className="px-3 py-1.5">
                          {t.inScue ? (
                            <span className="text-green-500 text-xs flex items-center gap-1">
                              <span>✓</span> in SCUE
                            </span>
                          ) : (
                            <span className="text-gray-600 text-xs">—</span>
                          )}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
