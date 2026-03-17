interface TrackToolbarProps {
  search: string;
  onSearchChange: (value: string) => void;
  total: number;
}

export function TrackToolbar({ search, onSearchChange, total }: TrackToolbarProps) {
  return (
    <div className="flex items-center gap-4 mb-4">
      <input
        type="text"
        placeholder="Search by title or artist..."
        value={search}
        onChange={(e) => onSearchChange(e.target.value)}
        className="bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:border-gray-500 w-72"
      />
      <span className="text-gray-500 text-sm ml-auto">
        {total} track{total !== 1 ? "s" : ""}
      </span>
    </div>
  );
}
