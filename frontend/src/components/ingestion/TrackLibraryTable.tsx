import { useRef, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  flexRender,
  createColumnHelper,
  type SortingState,
} from "@tanstack/react-table";
import { useVirtualizer } from "@tanstack/react-virtual";
import type { TrackSummary } from "../../types";
import { formatDuration, formatBpm } from "../../utils/formatters";

const col = createColumnHelper<TrackSummary>();

function SourceBadges({ track }: { track: TrackSummary }) {
  // Show source badges based on what data is available.
  // "LIB" = pioneer_enriched source (local ANLZ data)
  // "HW" = has rekordbox_id (from hardware scan)
  // "AUDIO" = analysis source (local audio analysis)
  const badges: { label: string; color: string }[] = [];

  if (track.source === "pioneer_enriched") {
    badges.push({ label: "LIB", color: "bg-green-900/50 text-green-400" });
  }
  if (track.source === "pioneer_enriched" || track.source === "analysis") {
    // If we have audio-based analysis
    if (track.source === "analysis") {
      badges.push({ label: "AUDIO", color: "bg-yellow-900/50 text-yellow-400" });
    }
  }

  if (badges.length === 0) {
    badges.push({ label: "AUDIO", color: "bg-yellow-900/50 text-yellow-400" });
  }

  return (
    <div className="flex items-center gap-1">
      {badges.map((b) => (
        <span key={b.label} className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${b.color}`}>
          {b.label}
        </span>
      ))}
    </div>
  );
}

const columns = [
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
  col.display({
    id: "sources",
    header: "Sources",
    cell: (info) => <SourceBadges track={info.row.original} />,
    size: 100,
  }),
];

const ROW_HEIGHT = 37;

interface TrackLibraryTableProps {
  data: TrackSummary[];
  globalFilter: string;
}

export function TrackLibraryTable({ data, globalFilter }: TrackLibraryTableProps) {
  const navigate = useNavigate();
  const [sorting, setSorting] = useState<SortingState>([
    { id: "title", desc: false },
  ]);

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
    state: { sorting, globalFilter },
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

  const handleRowClick = (fingerprint: string) => {
    navigate(`/strata?track=${fingerprint}`);
  };

  return (
    <div
      ref={parentRef}
      className="overflow-auto rounded border border-gray-800"
      style={{ maxHeight: "calc(100vh - 500px)" }}
    >
      <table className="w-full text-sm">
        <thead className="sticky top-0 z-10">
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id} className="border-b border-gray-800 bg-gray-900">
              {hg.headers.map((header) => (
                <th
                  key={header.id}
                  className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-gray-400 cursor-pointer select-none hover:text-gray-200"
                  style={{ width: header.getSize() }}
                  onClick={header.column.getToggleSortingHandler()}
                >
                  <div className="flex items-center gap-1">
                    {flexRender(header.column.columnDef.header, header.getContext())}
                    <SortIndicator dir={header.column.getIsSorted()} />
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
                No tracks in library
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
                return (
                  <tr
                    key={row.id}
                    className="border-b border-gray-800/50 hover:bg-gray-800/30 cursor-pointer transition-colors"
                    style={{ height: ROW_HEIGHT }}
                    onClick={() => handleRowClick(row.original.fingerprint)}
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
