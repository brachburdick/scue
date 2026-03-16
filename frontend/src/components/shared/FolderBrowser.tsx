import { useEffect, useState, useCallback } from "react";
import { browseFilesystem } from "../../api/analyze";
import type { BrowseEntry } from "../../types";

interface FolderBrowserProps {
  open: boolean;
  onSelect: (path: string) => void;
  onClose: () => void;
}

export function FolderBrowser({ open, onSelect, onClose }: FolderBrowserProps) {
  const [currentPath, setCurrentPath] = useState("");
  const [parent, setParent] = useState<string | null>(null);
  const [entries, setEntries] = useState<BrowseEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const navigate = useCallback(async (path?: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await browseFilesystem(path);
      setCurrentPath(res.path);
      setParent(res.parent);
      setEntries(res.entries);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) navigate();
  }, [open, navigate]);

  if (!open) return null;

  const pathSegments = currentPath.split("/").filter(Boolean);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-gray-900 border border-gray-700 rounded-lg w-[560px] max-h-[480px] flex flex-col shadow-xl">
        {/* Header */}
        <div className="px-4 py-3 border-b border-gray-800 flex items-center justify-between">
          <span className="text-sm font-medium">Browse Filesystem</span>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-200 text-lg leading-none">&times;</button>
        </div>

        {/* Breadcrumb */}
        <div className="px-4 py-2 border-b border-gray-800 text-xs text-gray-400 flex items-center gap-1 overflow-x-auto whitespace-nowrap">
          <button
            onClick={() => navigate("/")}
            className="hover:text-gray-200"
          >
            /
          </button>
          {pathSegments.map((seg, i) => {
            const segPath = "/" + pathSegments.slice(0, i + 1).join("/");
            return (
              <span key={segPath} className="flex items-center gap-1">
                <span className="text-gray-600">/</span>
                <button
                  onClick={() => navigate(segPath)}
                  className="hover:text-gray-200"
                >
                  {seg}
                </button>
              </span>
            );
          })}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto min-h-0">
          {loading ? (
            <p className="text-gray-500 text-sm p-4">Loading...</p>
          ) : error ? (
            <p className="text-red-400 text-sm p-4">{error}</p>
          ) : (
            <div className="divide-y divide-gray-800/50">
              {parent && (
                <button
                  onClick={() => navigate(parent)}
                  className="w-full text-left px-4 py-2 text-sm text-gray-400 hover:bg-gray-800/50 flex items-center gap-2"
                >
                  <span className="text-gray-500">..</span>
                  <span>Parent directory</span>
                </button>
              )}
              {entries.length === 0 && (
                <p className="text-gray-500 text-sm p-4">Empty directory</p>
              )}
              {entries.map((entry) => (
                <button
                  key={entry.path}
                  onClick={() => entry.is_dir ? navigate(entry.path) : onSelect(entry.path)}
                  className="w-full text-left px-4 py-2 text-sm hover:bg-gray-800/50 flex items-center gap-2"
                >
                  <span className={entry.is_dir ? "text-blue-400" : "text-gray-500"}>
                    {entry.is_dir ? "\u{1F4C1}" : "\u{1F3B5}"}
                  </span>
                  <span className={entry.is_dir ? "text-gray-200" : "text-gray-400"}>
                    {entry.name}
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-4 py-3 border-t border-gray-800 flex items-center justify-between">
          <span className="text-xs text-gray-500 truncate max-w-[320px]">{currentPath}</span>
          <div className="flex gap-2">
            <button
              onClick={onClose}
              className="px-3 py-1.5 text-sm text-gray-400 hover:text-gray-200"
            >
              Cancel
            </button>
            <button
              onClick={() => onSelect(currentPath)}
              className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white text-sm rounded"
            >
              Select Folder
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
