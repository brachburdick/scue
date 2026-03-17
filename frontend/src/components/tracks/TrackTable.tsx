import { useRef, useMemo, useState } from "react";
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
import { formatDuration, formatBpm, formatDate, truncateFingerprint } from "../../utils/formatters";

const col = createColumnHelper<TrackSummary>();

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
}

export function TrackTable({ data, globalFilter }: TrackTableProps) {
  const [sorting, setSorting] = useState<SortingState>([
    { id: "created_at", desc: true },
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

  return (
    <div
      ref={parentRef}
      className="overflow-auto rounded border border-gray-800"
      style={{ maxHeight: "calc(100vh - 220px)" }}
    >
      <table className="w-full text-sm">
        <thead className="sticky top-0 z-10">
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id} className="border-b border-gray-800 bg-gray-900">
              {hg.headers.map((header) => (
                <th
                  key={header.id}
                  className="px-3 py-2 text-left text-xs font-medium text-gray-400 uppercase tracking-wider cursor-pointer select-none hover:text-gray-200"
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
                No tracks found
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
                const row = rows[virtualRow.index];
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
