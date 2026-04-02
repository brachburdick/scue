import { useState, useMemo, useCallback, useRef, Fragment } from "react";
import { useNavigate } from "react-router-dom";
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  flexRender,
  createColumnHelper,
  type SortingState,
  type ColumnDef,
} from "@tanstack/react-table";
import { useVirtualizer } from "@tanstack/react-virtual";
import { useQueryClient } from "@tanstack/react-query";
import { useTracks } from "../../api/tracks";
import { useAnalyzeStrataBatch, useCancelStrataBatch } from "../../api/strata";
import { startBatchAnalysis, useJobStatus, useCancelJob } from "../../api/analyze";
import { useLibraryStore } from "../../stores/libraryStore";
import { TrackPreviewRow } from "./TrackPreviewRow";
import { StrataBatchProgress } from "../strata/TierAnalysisStatus";
import { formatDuration, formatBpm, formatDate } from "../../utils/formatters";
import type { TrackSummary } from "../../types";

const col = createColumnHelper<TrackSummary>();

function TierDot({ active, color, tooltip }: { active?: boolean; color: string; tooltip: string }) {
  return (
    <span title={tooltip} className={active ? color : "text-gray-700"}>
      ●
    </span>
  );
}

function SourceBadge({ source }: { source: string }) {
  const config: Record<string, { label: string; color: string }> = {
    pioneer_enriched: { label: "RB", color: "bg-green-900/50 text-green-400" },
    analysis: { label: "Audio", color: "bg-yellow-900/50 text-yellow-400" },
  };
  const badge = config[source] ?? { label: "Audio", color: "bg-yellow-900/50 text-yellow-400" };
  return (
    <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${badge.color}`}>
      {badge.label}
    </span>
  );
}

const ROW_HEIGHT = 37;

type SourceFilter = "all" | "rekordbox" | "hardware" | "audio";

export function ScueLibraryTab() {
  const navigate = useNavigate();
  const { data: trackData, isLoading, error } = useTracks({ limit: 5000 });
  const tracks = trackData?.tracks ?? [];

  const selectedTracks = useLibraryStore((s) => s.selectedTracks.scue_library);
  const setSelectedTracks = useLibraryStore((s) => s.setSelectedTracks);
  const toggleTrackSelection = useLibraryStore((s) => s.toggleTrackSelection);
  const expandedPreview = useLibraryStore((s) => s.expandedPreview);
  const setExpandedPreview = useLibraryStore((s) => s.setExpandedPreview);
  const searchText = useLibraryStore((s) => s.searchText.scue_library);
  const setSearchText = useLibraryStore((s) => s.setSearchText);

  const [sorting, setSorting] = useState<SortingState>([{ id: "title", desc: false }]);
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>("all");

  const queryClient = useQueryClient();
  const batchMutation = useAnalyzeStrataBatch();
  const cancelBatch = useCancelStrataBatch();
  const [batchId, setBatchId] = useState<string | null>(null);
  const [selectedTier, setSelectedTier] = useState<"quick" | "standard" | "deep">("quick");
  const [skipAnalyzed, setSkipAnalyzed] = useState(true);

  // Base audio analysis state
  const [audioJobId, setAudioJobId] = useState<string | null>(null);
  const { data: audioJob } = useJobStatus(audioJobId);
  const cancelAudioJob = useCancelJob();

  // Columns
  const columns = useMemo<ColumnDef<TrackSummary, unknown>[]>(() => [
    {
      id: "select",
      size: 32,
      header: () => null,
      cell: ({ row }) => {
        const fp = row.original.fingerprint;
        return (
          <input
            type="checkbox"
            checked={selectedTracks.has(fp)}
            onChange={() => toggleTrackSelection("scue_library", fp)}
            onClick={(e) => e.stopPropagation()}
            className="accent-blue-500"
          />
        );
      },
    },
    col.accessor("title", {
      header: "Title",
      cell: (info) => info.getValue() || "Untitled",
      size: 200,
    }) as ColumnDef<TrackSummary, unknown>,
    col.accessor("artist", {
      header: "Artist",
      cell: (info) => info.getValue() || "Unknown",
      size: 160,
    }) as ColumnDef<TrackSummary, unknown>,
    col.accessor("bpm", {
      header: "BPM",
      cell: (info) => formatBpm(info.getValue()),
      size: 60,
    }) as ColumnDef<TrackSummary, unknown>,
    col.accessor("key_name", {
      header: "Key",
      cell: (info) => info.getValue() || "\u2014",
      size: 50,
    }) as ColumnDef<TrackSummary, unknown>,
    col.accessor("duration", {
      header: "Duration",
      cell: (info) => formatDuration(info.getValue()),
      size: 70,
    }) as ColumnDef<TrackSummary, unknown>,
    col.display({
      id: "source",
      header: "Source",
      cell: (info) => <SourceBadge source={info.row.original.source} />,
      size: 70,
    }),
    col.accessor("created_at", {
      header: "Imported",
      cell: (info) => formatDate(info.getValue()),
      size: 100,
    }) as ColumnDef<TrackSummary, unknown>,
    col.accessor("has_quick", {
      header: "Q",
      cell: (info) => <TierDot active={info.getValue()} color="text-blue-400" tooltip="Quick: fast heuristic analysis (~3-7s)" />,
      size: 24,
    }) as ColumnDef<TrackSummary, unknown>,
    col.accessor("has_standard", {
      header: "S",
      cell: (info) => <TierDot active={info.getValue()} color="text-indigo-400" tooltip="Standard: stem separation + per-stem analysis (~1-2 min)" />,
      size: 24,
    }) as ColumnDef<TrackSummary, unknown>,
    col.accessor("has_deep", {
      header: "D",
      cell: (info) => <TierDot active={info.getValue()} color="text-purple-400" tooltip="Deep: stem separation + ML models (~2-5 min)" />,
      size: 24,
    }) as ColumnDef<TrackSummary, unknown>,
    col.accessor("has_live", {
      header: "L",
      cell: (info) => <TierDot active={info.getValue()} color="text-green-400" tooltip="Live: Pioneer hardware real-time data" />,
      size: 24,
    }) as ColumnDef<TrackSummary, unknown>,
    col.accessor("has_live_offline", {
      header: "L-O",
      cell: (info) => <TierDot active={info.getValue()} color="text-emerald-400" tooltip="Live Offline: saved Pioneer data, no hardware needed" />,
      size: 28,
    }) as ColumnDef<TrackSummary, unknown>,
  ], [selectedTracks, toggleTrackSelection]);

  // Filtering
  const globalFilterFn = useMemo(
    () => (row: { original: TrackSummary }) => {
      const t = row.original;
      // Source filter
      if (sourceFilter !== "all") {
        if (sourceFilter === "rekordbox" && t.source !== "pioneer_enriched") return false;
        if (sourceFilter === "audio" && t.source !== "analysis") return false;
        // "hardware" filter — no distinct source flag yet, treat same as rekordbox for now
        if (sourceFilter === "hardware" && t.source !== "pioneer_enriched") return false;
      }
      // Text search
      if (!searchText) return true;
      const q = searchText.toLowerCase();
      return t.title.toLowerCase().includes(q) || t.artist.toLowerCase().includes(q);
    },
    [searchText, sourceFilter],
  );

  const table = useReactTable({
    data: tracks,
    columns,
    state: { sorting, globalFilter: searchText },
    onSortingChange: setSorting,
    globalFilterFn,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  });

  const { rows } = table.getRowModel();
  const parentRef = useRef<HTMLDivElement>(null);

  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 10,
  });

  const virtualItems = virtualizer.getVirtualItems();
  const visibleTracks = table.getFilteredRowModel().rows.map((r) => r.original);
  const allVisibleSelected = visibleTracks.length > 0 && visibleTracks.every((t) => selectedTracks.has(t.fingerprint));

  const toggleAll = useCallback(() => {
    if (allVisibleSelected) {
      setSelectedTracks("scue_library", new Set());
    } else {
      setSelectedTracks("scue_library", new Set(visibleTracks.map((t) => t.fingerprint)));
    }
  }, [allVisibleSelected, visibleTracks, setSelectedTracks]);

  // Batch analysis: tier-aware stats
  const tierHasField = { quick: "has_quick", standard: "has_standard", deep: "has_deep" } as const;
  const selectedTrackData = useMemo(
    () => tracks.filter((t) => selectedTracks.has(t.fingerprint)),
    [tracks, selectedTracks],
  );
  const alreadyAnalyzedCount = useMemo(
    () => selectedTrackData.filter((t) => t[tierHasField[selectedTier]]).length,
    [selectedTrackData, selectedTier],
  );
  const fingerprintsToAnalyze = useMemo(
    () =>
      skipAnalyzed
        ? selectedTrackData.filter((t) => !t[tierHasField[selectedTier]]).map((t) => t.fingerprint)
        : [...selectedTracks],
    [selectedTrackData, selectedTier, skipAnalyzed, selectedTracks],
  );

  // Base audio analysis: tracks that have no analysis yet (section_count === 0)
  const needsAudioAnalysis = useMemo(
    () => selectedTrackData.filter((t) => t.section_count === 0),
    [selectedTrackData],
  );
  const audioAnalysisPaths = useMemo(
    () => needsAudioAnalysis.filter((t) => t.audio_path).map((t) => t.audio_path),
    [needsAudioAnalysis],
  );
  const isAudioJobRunning = audioJobId != null && audioJob?.status !== "complete" && audioJob?.status !== "complete_with_errors" && audioJob?.status !== "cancelled";

  const handleRunAudioAnalysis = useCallback(async () => {
    if (audioAnalysisPaths.length === 0) return;
    try {
      const result = await startBatchAnalysis(audioAnalysisPaths);
      setAudioJobId(result.job_id);
    } catch {
      // mutation error handled by TanStack
    }
  }, [audioAnalysisPaths]);

  const handleAudioJobDone = useCallback(() => {
    setAudioJobId(null);
    queryClient.invalidateQueries({ queryKey: ["tracks"] });
  }, [queryClient]);

  const handleRunAnalysis = useCallback(() => {
    if (fingerprintsToAnalyze.length === 0) return;
    batchMutation.mutate(
      { fingerprints: fingerprintsToAnalyze, tiers: [selectedTier] },
      { onSuccess: (result) => setBatchId(result.batch_id) },
    );
  }, [fingerprintsToAnalyze, selectedTier, batchMutation]);

  const handleOpenInAnalysis = useCallback(() => {
    if (selectedTracks.size !== 1) return;
    const fp = [...selectedTracks][0];
    navigate(`/analysis?track=${fp}`);
  }, [selectedTracks, navigate]);

  const handleBatchComplete = useCallback(() => {
    setBatchId(null);
    queryClient.invalidateQueries({ queryKey: ["tracks"] });
  }, [queryClient]);

  const handleBatchCancel = useCallback(() => {
    if (batchId) cancelBatch.mutate(batchId);
  }, [batchId, cancelBatch]);

  const handleRowClick = useCallback((fp: string) => {
    setExpandedPreview(expandedPreview === fp ? null : fp);
  }, [expandedPreview, setExpandedPreview]);

  if (error) {
    return (
      <div className="rounded border border-red-800 bg-red-900/20 p-4 text-sm text-red-400">
        <p className="font-medium">Failed to load tracks</p>
        <pre className="mt-2 text-xs text-red-300 whitespace-pre-wrap">{(error as Error).message}</pre>
      </div>
    );
  }

  if (isLoading) {
    return <div className="h-64 bg-gray-900 rounded border border-gray-800 animate-pulse" />;
  }

  return (
    <div className="space-y-3">
      {/* Toolbar */}
      <div className="flex items-center gap-3 flex-wrap">
        <input
          type="text"
          placeholder="Search by title or artist..."
          value={searchText}
          onChange={(e) => setSearchText("scue_library", e.target.value)}
          className="flex-1 min-w-48 px-3 py-1.5 text-sm bg-gray-900 border border-gray-700 rounded text-gray-300 placeholder-gray-600 focus:outline-none focus:border-gray-500"
        />

        <select
          value={sourceFilter}
          onChange={(e) => setSourceFilter(e.target.value as SourceFilter)}
          className="px-3 py-1.5 text-sm bg-gray-900 border border-gray-700 rounded text-gray-300 focus:outline-none focus:border-gray-500"
        >
          <option value="all">All Sources</option>
          <option value="rekordbox">Rekordbox</option>
          <option value="hardware">Hardware</option>
          <option value="audio">Audio</option>
        </select>

        <label className="flex items-center gap-1.5 text-xs text-gray-400 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={allVisibleSelected}
            onChange={toggleAll}
            className="accent-blue-500"
          />
          All ({visibleTracks.length})
        </label>

        <span className="text-xs text-gray-500">
          {tracks.length} total
        </span>
      </div>

      {/* Bulk actions */}
      {selectedTracks.size > 0 && (
        <div className="px-4 py-2 bg-gray-950 rounded border border-gray-800 space-y-2">
          <div className="flex items-center gap-3 flex-wrap">
            <span className="text-sm text-gray-400">
              {selectedTracks.size} selected
            </span>

            {/* Audio analysis button — for tracks that lack base analysis */}
            {needsAudioAnalysis.length > 0 && (
              <>
                <button
                  onClick={handleRunAudioAnalysis}
                  disabled={isAudioJobRunning || audioAnalysisPaths.length === 0}
                  className={`px-3 py-1.5 text-sm rounded transition-colors ${
                    isAudioJobRunning || audioAnalysisPaths.length === 0
                      ? "bg-emerald-800 text-emerald-300 cursor-not-allowed"
                      : "bg-emerald-600 text-white hover:bg-emerald-500"
                  }`}
                >
                  {isAudioJobRunning
                    ? "Analyzing audio..."
                    : `Analyze audio (${audioAnalysisPaths.length})`}
                </button>
                <span className="text-xs text-gray-500">
                  {needsAudioAnalysis.length} need audio analysis
                </span>
              </>
            )}

            {/* Strata tier section — only when some tracks have base analysis */}
            {selectedTrackData.length - needsAudioAnalysis.length > 0 && (
              <>
                <span className="text-gray-700">|</span>
                <select
                  value={selectedTier}
                  onChange={(e) => setSelectedTier(e.target.value as "quick" | "standard" | "deep")}
                  disabled={!!batchId || isAudioJobRunning}
                  className="px-2 py-1 text-sm rounded bg-gray-800 text-gray-200 border border-gray-700 focus:border-blue-500 focus:outline-none disabled:opacity-50"
                >
                  <option value="quick">Quick</option>
                  <option value="standard">Standard</option>
                  <option value="deep">Deep</option>
                </select>

                <span className="text-xs text-gray-500">
                  {alreadyAnalyzedCount}/{selectedTracks.size} have {selectedTier}
                </span>

                <label className="flex items-center gap-1.5 text-xs text-gray-400 cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={skipAnalyzed}
                    onChange={(e) => setSkipAnalyzed(e.target.checked)}
                    disabled={!!batchId || isAudioJobRunning}
                    className="accent-blue-500"
                  />
                  Skip done
                </label>

                <button
                  onClick={handleRunAnalysis}
                  disabled={batchMutation.isPending || !!batchId || isAudioJobRunning || fingerprintsToAnalyze.length === 0}
                  className={`px-3 py-1.5 text-sm rounded transition-colors ${
                    batchMutation.isPending || batchId || isAudioJobRunning || fingerprintsToAnalyze.length === 0
                      ? "bg-blue-800 text-blue-300 cursor-not-allowed"
                      : "bg-blue-600 text-white hover:bg-blue-500"
                  }`}
                >
                  {batchMutation.isPending
                    ? "Starting..."
                    : batchId
                      ? "Running..."
                      : fingerprintsToAnalyze.length === 0
                        ? "All done"
                        : `Run ${selectedTier} (${fingerprintsToAnalyze.length})`}
                </button>
              </>
            )}

            {/* Open in Analysis */}
            <button
              onClick={handleOpenInAnalysis}
              disabled={selectedTracks.size !== 1}
              title={selectedTracks.size !== 1 ? "Select exactly 1 track to open in Analysis" : ""}
              className={`px-3 py-1.5 text-sm rounded transition-colors ${
                selectedTracks.size === 1
                  ? "bg-gray-700 text-gray-200 hover:bg-gray-600"
                  : "bg-gray-800 text-gray-600 cursor-not-allowed"
              }`}
            >
              Open in Analysis
            </button>
          </div>
        </div>
      )}

      {/* Audio analysis progress */}
      {audioJobId && audioJob && (() => {
        const pct = audioJob.total > 0 ? Math.round((audioJob.completed / audioJob.total) * 100) : 0;
        const isDone = audioJob.status === "complete" || audioJob.status === "complete_with_errors";
        const isCancelled = audioJob.status === "cancelled";
        const isRunning = audioJob.status === "running" || audioJob.status === "pending";

        return (
          <div className="px-4 py-3 bg-gray-950 rounded border border-gray-800 space-y-2">
            <div className="flex justify-between items-center text-xs text-gray-400">
              <span>
                {isCancelled
                  ? <span className="text-yellow-400">Cancelled — {audioJob.completed}/{audioJob.total} completed</span>
                  : isDone
                    ? <span className="text-green-400">Audio analysis complete — {audioJob.completed} succeeded{audioJob.failed > 0 ? `, ${audioJob.failed} failed` : ""}</span>
                    : `Analyzing: ${audioJob.current_file ?? "..."}`}
              </span>
              <div className="flex items-center gap-3">
                <span>{audioJob.completed}/{audioJob.total} ({pct}%)</span>
                {isRunning && (
                  <button
                    onClick={() => cancelAudioJob.mutate(audioJobId)}
                    disabled={cancelAudioJob.isPending}
                    className="px-2 py-0.5 text-xs font-medium rounded bg-red-900/50 hover:bg-red-800 text-red-300 border border-red-800 transition-colors"
                  >
                    Stop
                  </button>
                )}
                {(isDone || isCancelled) && (
                  <button
                    onClick={handleAudioJobDone}
                    className="px-2 py-0.5 text-xs font-medium rounded bg-gray-700 hover:bg-gray-600 text-gray-300 border border-gray-600 transition-colors"
                  >
                    Dismiss
                  </button>
                )}
              </div>
            </div>
            <div className="w-full bg-gray-800 rounded-full h-2">
              <div
                className={`h-2 rounded-full transition-all ${isCancelled ? "bg-yellow-500" : isDone ? "bg-green-500" : "bg-emerald-500"}`}
                style={{ width: `${pct}%` }}
              />
            </div>
            {isRunning && audioJob.current_step_name && (
              <div>
                <div className="flex justify-between text-xs text-gray-500 mb-1">
                  <span>{audioJob.current_step_name}</span>
                  <span>{audioJob.current_step}/{audioJob.total_steps}</span>
                </div>
                <div className="w-full bg-gray-800 rounded-full h-1">
                  <div
                    className="h-1 rounded-full bg-cyan-500 transition-all"
                    style={{ width: `${audioJob.total_steps > 0 ? (audioJob.current_step / audioJob.total_steps) * 100 : 0}%` }}
                  />
                </div>
              </div>
            )}
          </div>
        );
      })()}

      {/* Strata batch progress */}
      {batchId && (
        <StrataBatchProgress
          batchId={batchId}
          onComplete={handleBatchComplete}
          onCancel={handleBatchCancel}
        />
      )}

      {/* Table */}
      <div
        ref={parentRef}
        className="overflow-auto rounded border border-gray-800"
        style={{ maxHeight: "calc(100vh - 380px)" }}
      >
        <table className="w-full text-sm">
          <thead className="sticky top-0 z-10">
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id} className="border-b border-gray-800 bg-gray-900">
                {hg.headers.map((header) => (
                  <th
                    key={header.id}
                    className="px-2 py-1.5 text-left text-xs font-medium uppercase tracking-wider text-gray-400 cursor-pointer select-none hover:text-gray-200"
                    style={{ width: header.getSize() }}
                    onClick={header.column.id !== "select" ? header.column.getToggleSortingHandler() : undefined}
                  >
                    <div className="flex items-center gap-1">
                      {flexRender(header.column.columnDef.header, header.getContext())}
                      {header.column.id !== "select" && (
                        <SortIndicator dir={header.column.getIsSorted()} />
                      )}
                    </div>
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="px-3 py-8 text-center text-gray-500">
                  {tracks.length === 0 ? "No tracks in SCUE yet. Import tracks from the Rekordbox, Hardware, or Audio tabs." : "No tracks match the current filters."}
                </td>
              </tr>
            ) : (
              <>
                {virtualItems.length > 0 && (
                  <tr>
                    <td style={{ height: virtualItems[0].start }} colSpan={columns.length} />
                  </tr>
                )}
                {virtualItems.map((virtualRow) => {
                  const row = rows[virtualRow.index];
                  if (!row) return null;
                  const fp = row.original.fingerprint;
                  const isSelected = selectedTracks.has(fp);
                  const isExpanded = expandedPreview === fp;
                  return (
                    <Fragment key={row.id}>
                      <tr
                        className={`border-b border-gray-800/50 cursor-pointer transition-colors ${
                          isExpanded
                            ? "bg-gray-800/50 text-white"
                            : isSelected
                              ? "bg-blue-900/20 text-gray-200"
                              : "hover:bg-gray-800/30 text-gray-300"
                        }`}
                        style={{ height: ROW_HEIGHT }}
                        onClick={() => handleRowClick(fp)}
                      >
                        {row.getVisibleCells().map((cell) => (
                          <td key={cell.id} className="px-2 py-1.5 whitespace-nowrap">
                            {flexRender(cell.column.columnDef.cell, cell.getContext())}
                          </td>
                        ))}
                      </tr>
                      {isExpanded && (
                        <TrackPreviewRow track={row.original} colSpan={columns.length} />
                      )}
                    </Fragment>
                  );
                })}
                {virtualItems.length > 0 && (
                  <tr>
                    <td
                      style={{ height: virtualizer.getTotalSize() - (virtualItems.at(-1)?.end ?? 0) }}
                      colSpan={columns.length}
                    />
                  </tr>
                )}
              </>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function SortIndicator({ dir }: { dir: false | "asc" | "desc" }) {
  if (!dir) return <span className="text-gray-700 text-xs">{"\u21C5"}</span>;
  return <span className="text-gray-300 text-xs">{dir === "asc" ? "\u25B2" : "\u25BC"}</span>;
}

