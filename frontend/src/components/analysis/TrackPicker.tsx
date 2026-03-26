import { useState, useMemo, useCallback } from "react";
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
import { useTracks } from "../../api/tracks";
import type { TrackSummary } from "../../types";
import { formatDuration, formatBpm } from "../../utils/formatters";

const col = createColumnHelper<TrackSummary>();

function TierDot({ active, color }: { active?: boolean; color: string }) {
  return <span className={active ? color : "text-gray-700"}>●</span>;
}

const baseColumns: ColumnDef<TrackSummary, unknown>[] = [
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
  col.accessor("section_count", {
    header: "Sections",
    cell: (info) => info.getValue(),
    size: 60,
  }) as ColumnDef<TrackSummary, unknown>,
  col.accessor("has_quick", {
    header: "Q",
    cell: (info) => <TierDot active={info.getValue()} color="text-blue-400" />,
    size: 24,
  }) as ColumnDef<TrackSummary, unknown>,
  col.accessor("has_standard", {
    header: "S",
    cell: (info) => <TierDot active={info.getValue()} color="text-indigo-400" />,
    size: 24,
  }) as ColumnDef<TrackSummary, unknown>,
  col.accessor("has_deep", {
    header: "D",
    cell: (info) => <TierDot active={info.getValue()} color="text-purple-400" />,
    size: 24,
  }) as ColumnDef<TrackSummary, unknown>,
  col.accessor("has_live", {
    header: "L",
    cell: (info) => <TierDot active={info.getValue()} color="text-green-400" />,
    size: 24,
  }) as ColumnDef<TrackSummary, unknown>,
  col.accessor("has_live_offline", {
    header: "L-O",
    cell: (info) => <TierDot active={info.getValue()} color="text-emerald-400" />,
    size: 28,
  }) as ColumnDef<TrackSummary, unknown>,
];

const ROW_HEIGHT = 33;

interface TrackPickerSingleProps {
  mode?: "single";
  selectedFingerprint: string | null;
  onSelect: (fingerprint: string) => void;
  selectedFingerprints?: never;
  onSelectionChange?: never;
}

interface TrackPickerMultiProps {
  mode: "multi";
  selectedFingerprints: Set<string>;
  onSelectionChange: (fps: Set<string>) => void;
  selectedFingerprint?: never;
  onSelect?: never;
}

type TrackPickerProps = TrackPickerSingleProps | TrackPickerMultiProps;

export function TrackPicker(props: TrackPickerProps) {
  const isMulti = props.mode === "multi";
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

  const toggleSelection = useCallback(
    (fp: string) => {
      if (!isMulti) return;
      const next = new Set(props.selectedFingerprints);
      if (next.has(fp)) next.delete(fp);
      else next.add(fp);
      props.onSelectionChange(next);
    },
    [isMulti, props],
  );

  const toggleAll = useCallback(
    (tracks: TrackSummary[]) => {
      if (!isMulti) return;
      const allSelected = tracks.every((t) => props.selectedFingerprints.has(t.fingerprint));
      if (allSelected) {
        props.onSelectionChange(new Set());
      } else {
        props.onSelectionChange(new Set(tracks.map((t) => t.fingerprint)));
      }
    },
    [isMulti, props],
  );

  // Build columns with optional checkbox
  const columns = useMemo(() => {
    if (!isMulti) return baseColumns;
    const checkboxCol: ColumnDef<TrackSummary, unknown> = {
      id: "select",
      size: 32,
      header: () => null, // Header checkbox rendered separately via toggleAll
      cell: ({ row }) => {
        const fp = row.original.fingerprint;
        const checked = props.selectedFingerprints.has(fp);
        return (
          <input
            type="checkbox"
            checked={checked}
            onChange={() => toggleSelection(fp)}
            onClick={(e) => e.stopPropagation()}
            className="accent-blue-500"
          />
        );
      },
    };
    return [checkboxCol, ...baseColumns];
  }, [isMulti, props, toggleSelection]);

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

  const visibleTracks = table.getFilteredRowModel().rows.map((r) => r.original);
  const allVisibleSelected = isMulti && visibleTracks.length > 0 && visibleTracks.every((t) => props.selectedFingerprints.has(t.fingerprint));

  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <input
          type="text"
          placeholder="Search by title or artist..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1 px-3 py-1.5 text-sm bg-gray-900 border border-gray-700 rounded text-gray-300 placeholder-gray-600 focus:outline-none focus:border-gray-500"
        />
        {isMulti && (
          <label className="flex items-center gap-1.5 text-xs text-gray-400 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={allVisibleSelected}
              onChange={() => toggleAll(visibleTracks)}
              className="accent-blue-500"
            />
            All ({visibleTracks.length})
          </label>
        )}
      </div>
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
            {table.getRowModel().rows.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="px-2 py-4 text-center text-gray-500">
                  No tracks found
                </td>
              </tr>
            ) : (
              table.getRowModel().rows.map((row) => {
                const fp = row.original.fingerprint;
                const isSelected = isMulti
                  ? props.selectedFingerprints.has(fp)
                  : fp === props.selectedFingerprint;
                return (
                  <tr
                    key={row.id}
                    className={`border-b border-gray-800/50 cursor-pointer transition-colors ${
                      isSelected
                        ? "bg-blue-900/30 text-white"
                        : "hover:bg-gray-800/30 text-gray-300"
                    }`}
                    style={{ height: ROW_HEIGHT }}
                    onClick={() => {
                      if (isMulti) {
                        toggleSelection(fp);
                      } else {
                        props.onSelect(fp);
                      }
                    }}
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
      {isMulti && props.selectedFingerprints.size > 0 && (
        <p className="text-xs text-gray-500 mt-1">
          {props.selectedFingerprints.size} track{props.selectedFingerprints.size !== 1 ? "s" : ""} selected
        </p>
      )}
    </div>
  );
}

function SortIndicator({ dir }: { dir: false | "asc" | "desc" }) {
  if (!dir) return <span className="text-gray-700 text-xs">{"\u21C5"}</span>;
  return <span className="text-gray-300 text-xs">{dir === "asc" ? "\u25B2" : "\u25BC"}</span>;
}
