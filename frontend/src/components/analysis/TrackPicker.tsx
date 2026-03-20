import { useState, useMemo } from "react";
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  flexRender,
  createColumnHelper,
  type SortingState,
} from "@tanstack/react-table";
import { useTracks } from "../../api/tracks";
import type { TrackSummary } from "../../types";
import { formatDuration, formatBpm } from "../../utils/formatters";

const col = createColumnHelper<TrackSummary>();

const columns = [
  col.accessor("title", {
    header: "Title",
    cell: (info) => info.getValue() || "Untitled",
    size: 200,
  }),
  col.accessor("artist", {
    header: "Artist",
    cell: (info) => info.getValue() || "Unknown",
    size: 160,
  }),
  col.accessor("bpm", {
    header: "BPM",
    cell: (info) => formatBpm(info.getValue()),
    size: 60,
  }),
  col.accessor("key_name", {
    header: "Key",
    cell: (info) => info.getValue() || "—",
    size: 50,
  }),
  col.accessor("duration", {
    header: "Duration",
    cell: (info) => formatDuration(info.getValue()),
    size: 70,
  }),
  col.accessor("section_count", {
    header: "Sections",
    cell: (info) => info.getValue(),
    size: 60,
  }),
];

const ROW_HEIGHT = 33;

interface TrackPickerProps {
  selectedFingerprint: string | null;
  onSelect: (fingerprint: string) => void;
}

export function TrackPicker({ selectedFingerprint, onSelect }: TrackPickerProps) {
  const { data, isLoading, error } = useTracks({ limit: 1000 });
  const [sorting, setSorting] = useState<SortingState>([{ id: "title", desc: false }]);
  const [search, setSearch] = useState("");

  const globalFilterFn = useMemo(
    () => (row: { original: TrackSummary }) => {
      if (!search) return true;
      const q = search.toLowerCase();
      const t = row.original;
      return t.title.toLowerCase().includes(q) || t.artist.toLowerCase().includes(q);
    },
    [search],
  );

  const table = useReactTable({
    data: data?.tracks ?? [],
    columns,
    state: { sorting, globalFilter: search },
    onSortingChange: setSorting,
    globalFilterFn,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  });

  if (error) {
    return <p className="text-red-400 text-sm">Failed to load tracks: {(error as Error).message}</p>;
  }

  if (isLoading) {
    return <p className="text-gray-500 text-sm">Loading tracks...</p>;
  }

  return (
    <div>
      <input
        type="text"
        placeholder="Search by title or artist..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className="w-full mb-2 px-3 py-1.5 text-sm bg-gray-900 border border-gray-700 rounded text-gray-300 placeholder-gray-600 focus:outline-none focus:border-gray-500"
      />
      <div className="max-h-48 overflow-auto rounded border border-gray-800">
        <table className="w-full text-sm">
          <thead className="sticky top-0 z-10">
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id} className="border-b border-gray-800 bg-gray-900">
                {hg.headers.map((header) => (
                  <th
                    key={header.id}
                    className="px-2 py-1.5 text-left text-xs font-medium text-gray-400 uppercase tracking-wider cursor-pointer select-none hover:text-gray-200"
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
            {table.getRowModel().rows.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="px-2 py-4 text-center text-gray-500">
                  No tracks found
                </td>
              </tr>
            ) : (
              table.getRowModel().rows.map((row) => {
                const isSelected = row.original.fingerprint === selectedFingerprint;
                return (
                  <tr
                    key={row.id}
                    className={`border-b border-gray-800/50 cursor-pointer transition-colors ${
                      isSelected
                        ? "bg-blue-900/30 text-white"
                        : "hover:bg-gray-800/30 text-gray-300"
                    }`}
                    style={{ height: ROW_HEIGHT }}
                    onClick={() => onSelect(row.original.fingerprint)}
                  >
                    {row.getVisibleCells().map((cell) => (
                      <td key={cell.id} className="px-2 py-1.5 whitespace-nowrap">
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </td>
                    ))}
                  </tr>
                );
              })
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
