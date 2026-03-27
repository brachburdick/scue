import { useRef, useMemo, useState } from "react";
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  flexRender,
  createColumnHelper,
  type SortingState,
  type ColumnFiltersState,
} from "@tanstack/react-table";
import { useVirtualizer } from "@tanstack/react-virtual";
import type { TrackSummary, FolderInfo } from "../../types";
import { formatDuration, formatBpm, formatDate, truncateFingerprint } from "../../utils/formatters";
import { useFolderStore } from "../../stores/folderStore";

const col = createColumnHelper<TrackSummary>();

function TierDot({ active, color }: { active?: boolean; color: string }) {
  return <span className={active ? color : "text-gray-700"}>●</span>;
}

const tierColumns = [
  col.accessor("has_quick", {
    header: "Q",
    cell: (info) => <TierDot active={info.getValue()} color="text-blue-400" />,
    size: 28,
    filterFn: "equals",
    enableColumnFilter: true,
  }),
  col.accessor("has_standard", {
    header: "S",
    cell: (info) => <TierDot active={info.getValue()} color="text-indigo-400" />,
    size: 28,
    filterFn: "equals",
    enableColumnFilter: true,
  }),
  col.accessor("has_deep", {
    header: "D",
    cell: (info) => <TierDot active={info.getValue()} color="text-purple-400" />,
    size: 28,
    filterFn: "equals",
    enableColumnFilter: true,
  }),
  col.accessor("has_live", {
    header: () => <span title="Live tier — real-time Pioneer hardware analysis">L</span>,
    cell: (info) => <TierDot active={info.getValue()} color="text-green-400" />,
    size: 28,
    filterFn: "equals",
    enableColumnFilter: true,
  }),
  col.accessor("has_live_offline", {
    header: () => <span title="Live Offline — analysis from saved Pioneer data (no hardware needed)">L-O</span>,
    cell: (info) => <TierDot active={info.getValue()} color="text-emerald-400" />,
    size: 32,
    filterFn: "equals",
    enableColumnFilter: true,
  }),
];

function makeFlatColumns(onFolderClick: (folder: string) => void) {
  return [
    col.accessor("title", {
      header: "Title",
      cell: (info) => info.getValue() || "Untitled",
      size: 220,
    }),
    col.accessor("artist", {
      header: "Artist",
      cell: (info) => info.getValue() || "Unknown",
      size: 160,
    }),
    col.accessor("folder", {
      header: "Folder",
      cell: (info) => {
        const folder = info.getValue();
        if (!folder) return <span className="text-gray-600">—</span>;
        return (
          <button
            onClick={(e) => {
              e.stopPropagation();
              onFolderClick(folder);
            }}
            className="text-blue-400 hover:text-blue-300 text-xs truncate max-w-[140px] block"
            title={folder}
          >
            {folder}
          </button>
        );
      },
      size: 150,
    }),
    col.accessor("bpm", {
      header: "BPM",
      cell: (info) => formatBpm(info.getValue()),
      size: 70,
    }),
    col.accessor("key_name", {
      header: "Key",
      cell: (info) => info.getValue() || "—",
      size: 60,
    }),
    col.accessor("duration", {
      header: "Duration",
      cell: (info) => formatDuration(info.getValue()),
      size: 80,
    }),
    col.accessor("section_count", {
      header: "Sections",
      cell: (info) => info.getValue(),
      size: 70,
    }),
    col.accessor("mood", {
      header: "Mood",
      cell: (info) => <MoodBadge mood={info.getValue()} />,
      size: 90,
    }),
    col.accessor("source", {
      header: "Source",
      cell: (info) => <SourceBadge source={info.getValue()} />,
      size: 80,
    }),
    col.accessor("created_at", {
      header: "Analyzed",
      cell: (info) => formatDate(info.getValue()),
      size: 100,
    }),
    col.accessor("fingerprint", {
      header: "ID",
      cell: (info) => (
        <span className="font-mono text-gray-500">{truncateFingerprint(info.getValue())}</span>
      ),
      size: 80,
    }),
    ...tierColumns,
  ];
}

const directoryColumns = [
  col.accessor("title", {
    header: "Title",
    cell: (info) => info.getValue() || "Untitled",
    size: 240,
  }),
  col.accessor("artist", {
    header: "Artist",
    cell: (info) => info.getValue() || "Unknown",
    size: 180,
  }),
  col.accessor("bpm", {
    header: "BPM",
    cell: (info) => formatBpm(info.getValue()),
    size: 70,
  }),
  col.accessor("key_name", {
    header: "Key",
    cell: (info) => info.getValue() || "—",
    size: 60,
  }),
  col.accessor("duration", {
    header: "Duration",
    cell: (info) => formatDuration(info.getValue()),
    size: 80,
  }),
  col.accessor("section_count", {
    header: "Sections",
    cell: (info) => info.getValue(),
    size: 70,
  }),
  col.accessor("mood", {
    header: "Mood",
    cell: (info) => <MoodBadge mood={info.getValue()} />,
    size: 100,
  }),
  col.accessor("source", {
    header: "Source",
    cell: (info) => <SourceBadge source={info.getValue()} />,
    size: 90,
  }),
  col.accessor("created_at", {
    header: "Analyzed",
    cell: (info) => formatDate(info.getValue()),
    size: 110,
  }),
  col.accessor("fingerprint", {
    header: "ID",
    cell: (info) => (
      <span className="font-mono text-gray-500">{truncateFingerprint(info.getValue())}</span>
    ),
    size: 80,
  }),
  ...tierColumns,
];

const ROW_HEIGHT = 37;

const MOOD_COLORS: Record<string, string> = {
  dark: "bg-purple-900/50 text-purple-300",
  euphoric: "bg-amber-900/50 text-amber-300",
  melancholic: "bg-blue-900/50 text-blue-300",
  aggressive: "bg-red-900/50 text-red-300",
  neutral: "bg-gray-800 text-gray-400",
};

function MoodBadge({ mood }: { mood: string }) {
  const cls = MOOD_COLORS[mood] ?? MOOD_COLORS.neutral;
  return <span className={`px-2 py-0.5 rounded text-xs ${cls}`}>{mood}</span>;
}

function SourceBadge({ source }: { source: string }) {
  const isEnriched = source === "pioneer_enriched";
  return (
    <span
      className={`px-2 py-0.5 rounded text-xs ${
        isEnriched
          ? "bg-green-900/50 text-green-300"
          : "bg-gray-800 text-gray-400"
      }`}
    >
      {isEnriched ? "enriched" : "analysis"}
    </span>
  );
}

interface TrackTableProps {
  data: TrackSummary[];
  globalFilter: string;
  folders?: FolderInfo[];
  onAnalyzeFolder?: (folderPath: string) => void;
}

export function TrackTable({ data, globalFilter, folders = [], onAnalyzeFolder }: TrackTableProps) {
  const { viewMode, navigateToFolder } = useFolderStore();

  const [sorting, setSorting] = useState<SortingState>([
    { id: "created_at", desc: true },
  ]);
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>([]);

  const columns = useMemo(
    () =>
      viewMode === "flat"
        ? makeFlatColumns(navigateToFolder)
        : directoryColumns,
    [viewMode, navigateToFolder],
  );

  const globalFilterFn = useMemo(
    () =>
      (row: { original: TrackSummary }) => {
        if (!globalFilter) return true;
        const q = globalFilter.toLowerCase();
        const t = row.original;
        return (
          t.title.toLowerCase().includes(q) ||
          t.artist.toLowerCase().includes(q)
        );
      },
    [globalFilter],
  );

  const table = useReactTable({
    data,
    columns,
    state: { sorting, globalFilter, columnFilters },
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    globalFilterFn,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  });

  const { rows } = table.getRowModel();

  const parentRef = useRef<HTMLDivElement>(null);

  // Account for folder rows in virtualizer count
  const folderRowCount = viewMode === "directory" ? folders.length : 0;
  const totalRows = folderRowCount + rows.length;

  const virtualizer = useVirtualizer({
    count: totalRows,
    getScrollElement: () => parentRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 10,
  });

  const virtualItems = virtualizer.getVirtualItems();

  return (
    <div
      ref={parentRef}
      className="overflow-auto rounded border border-gray-800"
      style={{ maxHeight: "calc(100vh - 260px)" }}
    >
      <table className="w-full text-sm">
        <thead className="sticky top-0 z-10">
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id} className="border-b border-gray-800 bg-gray-900">
              {hg.headers.map((header) => {
                const isTierCol = header.column.id.startsWith("has_");
                const tierFilterActive = isTierCol && header.column.getFilterValue() === true;
                return (
                  <th
                    key={header.id}
                    className={`px-3 py-2 text-left text-xs font-medium uppercase tracking-wider cursor-pointer select-none hover:text-gray-200 ${tierFilterActive ? "text-white bg-gray-800" : "text-gray-400"}`}
                    style={{ width: header.getSize() }}
                    onClick={
                      isTierCol
                        ? () => header.column.setFilterValue(tierFilterActive ? undefined : true)
                        : header.column.getToggleSortingHandler()
                    }
                    title={isTierCol ? `Filter: ${tierFilterActive ? "showing all" : "only with this tier"}` : undefined}
                  >
                    <div className="flex items-center gap-1">
                      {flexRender(header.column.columnDef.header, header.getContext())}
                      {!isTierCol && <SortIndicator dir={header.column.getIsSorted()} />}
                    </div>
                  </th>
                );
              })}
            </tr>
          ))}
        </thead>
        <tbody>
          {totalRows === 0 ? (
            <tr>
              <td colSpan={columns.length} className="px-3 py-8 text-center text-gray-500">
                {viewMode === "directory" ? "Empty folder" : "No tracks found"}
              </td>
            </tr>
          ) : (
            <>
              {virtualItems.length > 0 && (
                <tr>
                  <td
                    style={{ height: virtualItems[0].start }}
                    colSpan={columns.length}
                  />
                </tr>
              )}
              {virtualItems.map((virtualRow) => {
                const idx = virtualRow.index;

                // Folder rows come first in directory mode
                if (viewMode === "directory" && idx < folderRowCount) {
                  const folder = folders[idx];
                  return (
                    <tr
                      key={`folder-${folder.path}`}
                      className="border-b border-gray-800/50 hover:bg-gray-800/40 cursor-pointer transition-colors"
                      style={{ height: ROW_HEIGHT }}
                      onClick={() => navigateToFolder(folder.path)}
                    >
                      <td className="px-3 py-2 text-blue-400" colSpan={2}>
                        <span className="mr-2">📁</span>
                        {folder.name}
                      </td>
                      <td className="px-3 py-2 text-gray-500 text-xs" colSpan={columns.length - 3}>
                        {folder.track_count} track{folder.track_count !== 1 ? "s" : ""}
                      </td>
                      <td className="px-3 py-2 text-right">
                        {onAnalyzeFolder && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              onAnalyzeFolder(folder.path);
                            }}
                            className="text-xs text-gray-500 hover:text-blue-400"
                            title="Analyze all tracks in this folder"
                          >
                            Analyze
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                }

                // Track rows
                const trackIdx = idx - folderRowCount;
                const row = rows[trackIdx];
                if (!row) return null;

                return (
                  <tr
                    key={row.id}
                    className="border-b border-gray-800/50 hover:bg-gray-800/30 transition-colors"
                    style={{ height: ROW_HEIGHT }}
                  >
                    {row.getVisibleCells().map((cell) => (
                      <td key={cell.id} className="px-3 py-2 text-gray-300 whitespace-nowrap">
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </td>
                    ))}
                  </tr>
                );
              })}
              {virtualItems.length > 0 && (
                <tr>
                  <td
                    style={{
                      height:
                        virtualizer.getTotalSize() -
                        (virtualItems.at(-1)?.end ?? 0),
                    }}
                    colSpan={columns.length}
                  />
                </tr>
              )}
            </>
          )}
        </tbody>
      </table>
    </div>
  );
}

function SortIndicator({ dir }: { dir: false | "asc" | "desc" }) {
  if (!dir) return <span className="text-gray-700 text-xs">⇅</span>;
  return <span className="text-gray-300 text-xs">{dir === "asc" ? "▲" : "▼"}</span>;
}
