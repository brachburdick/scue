import { useState } from "react";
import { useFolderStore } from "../../stores/folderStore";
import { createFolder } from "../../api/analyze";
import { useQueryClient } from "@tanstack/react-query";

interface TrackToolbarProps {
  search: string;
  onSearchChange: (value: string) => void;
  total: number;
}

export function TrackToolbar({ search, onSearchChange, total }: TrackToolbarProps) {
  const { viewMode, setViewMode, currentFolder, setCurrentFolder } = useFolderStore();
  const [newFolderInput, setNewFolderInput] = useState("");
  const [showNewFolder, setShowNewFolder] = useState(false);
  const queryClient = useQueryClient();

  const breadcrumbs = currentFolder
    ? currentFolder.split("/")
    : [];

  const handleCreateFolder = async () => {
    const name = newFolderInput.trim();
    if (!name) return;
    const fullPath = currentFolder ? `${currentFolder}/${name}` : name;
    await createFolder(fullPath);
    setNewFolderInput("");
    setShowNewFolder(false);
    queryClient.invalidateQueries({ queryKey: ["folder-contents"] });
  };

  return (
    <div className="mb-4 space-y-2">
      <div className="flex items-center gap-3">
        {/* View mode toggle */}
        <div className="flex rounded border border-gray-700 overflow-hidden text-xs">
          <button
            onClick={() => setViewMode("flat")}
            className={`px-2.5 py-1 ${
              viewMode === "flat"
                ? "bg-gray-600 text-white"
                : "bg-gray-800 text-gray-400 hover:text-gray-200"
            }`}
          >
            All
          </button>
          <button
            onClick={() => setViewMode("directory")}
            className={`px-2.5 py-1 border-l border-gray-700 ${
              viewMode === "directory"
                ? "bg-gray-600 text-white"
                : "bg-gray-800 text-gray-400 hover:text-gray-200"
            }`}
          >
            Folders
          </button>
        </div>

        {/* Search */}
        <input
          type="text"
          placeholder="Search by title or artist..."
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          className="bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:border-gray-500 w-72"
        />

        {/* New folder button (directory mode only) */}
        {viewMode === "directory" && (
          <button
            onClick={() => setShowNewFolder(!showNewFolder)}
            className="px-2.5 py-1.5 text-xs bg-gray-800 border border-gray-700 rounded hover:bg-gray-700 text-gray-300"
          >
            + Folder
          </button>
        )}

        <span className="text-gray-500 text-sm ml-auto">
          {total} track{total !== 1 ? "s" : ""}
        </span>
      </div>

      {/* Breadcrumb navigation (directory mode) */}
      {viewMode === "directory" && (
        <div className="flex items-center gap-1 text-xs text-gray-400">
          <button
            onClick={() => setCurrentFolder("")}
            className="hover:text-gray-200"
          >
            Root
          </button>
          {breadcrumbs.map((segment, i) => {
            const path = breadcrumbs.slice(0, i + 1).join("/");
            return (
              <span key={path} className="flex items-center gap-1">
                <span className="text-gray-600">/</span>
                <button
                  onClick={() => setCurrentFolder(path)}
                  className="hover:text-gray-200"
                >
                  {segment}
                </button>
              </span>
            );
          })}
        </div>
      )}

      {/* New folder inline input */}
      {showNewFolder && (
        <div className="flex items-center gap-2">
          <input
            type="text"
            placeholder="Folder name..."
            value={newFolderInput}
            onChange={(e) => setNewFolderInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleCreateFolder()}
            className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-100 placeholder-gray-500 focus:outline-none focus:border-gray-500 w-48"
            autoFocus
          />
          <button
            onClick={handleCreateFolder}
            disabled={!newFolderInput.trim()}
            className="px-2 py-1 text-xs bg-blue-600 hover:bg-blue-500 disabled:opacity-50 rounded text-white"
          >
            Create
          </button>
          <button
            onClick={() => {
              setShowNewFolder(false);
              setNewFolderInput("");
            }}
            className="text-xs text-gray-500 hover:text-gray-300"
          >
            Cancel
          </button>
        </div>
      )}
    </div>
  );
}
