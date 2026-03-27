import { useState, useEffect, useRef } from "react";
import { useUsbMenu, useUsbFolder, useUsbBrowse } from "../../api/ingestion";
import type { UsbTrack, UsbMenuItem } from "../../types/ingestion";

interface UsbBrowserProps {
  player: number;
  slot: string;
  scannedIds: Set<number>;
  selectedIds: Set<number>;
  onSelectionChange: (ids: Set<number>) => void;
}

export function UsbBrowser({
  player,
  slot,
  scannedIds,
  selectedIds,
  onSelectionChange,
}: UsbBrowserProps) {
  const [folderId, setFolderId] = useState<number | null>(null);
  const [folderPath, setFolderPath] = useState<{ id: number; name: string }[]>([]);
  // "flat" mode shows all tracks via browse_all_tracks (for TRACK root menu)
  const [flatMode, setFlatMode] = useState(false);
  // Whether the current folderId points to a folder (true) or leaf playlist (false)
  const [isFolder, setIsFolder] = useState(true);

  // Root menu items that need special navigation
  const PLAYLIST_NAMES = new Set(["PLAYLIST", "playlist"]);
  const TRACK_NAMES = new Set(["TRACK", "track"]);
  // Menu items that require unimplemented DLP commands
  const UNSUPPORTED_MENUS = new Set(["ARTIST", "ALBUM", "KEY", "HISTORY", "SEARCH", "FOLDER", "BITRATE", "BPM", "GENRE", "RATING", "TIME", "COLOR", "LABEL", "ORIGINAL ARTIST", "REMIXER", "DJ NAME", "YEAR"]);

  // Reset navigation when player or slot changes
  useEffect(() => {
    setFolderId(null);
    setFolderPath([]);
    setFlatMode(false);
    setIsFolder(true);
  }, [player, slot]);

  const { data: menu, isLoading: menuLoading } = useUsbMenu(player, slot, folderId === null && !flatMode);
  const { data: folder, isLoading: folderLoading } = useUsbFolder(player, slot, folderId, folderId !== null, isFolder);
  const { data: rootTracks } = useUsbBrowse(player, slot, folderId === null || flatMode);

  const navigateToFolder = (item: UsbMenuItem) => {
    const upperName = item.name.toUpperCase();

    // From root menu: handle special menu types
    if (folderId === null && !flatMode) {
      if (TRACK_NAMES.has(upperName)) {
        // TRACK: show flat track listing
        setFolderPath([{ id: item.id, name: item.name }]);
        setFlatMode(true);
        return;
      }
      if (PLAYLIST_NAMES.has(upperName)) {
        // PLAYLIST: navigate to playlist root (folder_id=0)
        setFolderPath([{ id: 0, name: item.name }]);
        setFolderId(0);
        return;
      }
      if (UNSUPPORTED_MENUS.has(upperName)) {
        // Not yet supported — stay at root
        return;
      }
    }

    setFolderPath((prev) => [...prev, { id: item.id, name: item.name }]);
    setFolderId(item.id);
    setIsFolder(item.is_folder);
  };

  const navigateUp = () => {
    if (flatMode || folderPath.length <= 1) {
      setFolderId(null);
      setFolderPath([]);
      setFlatMode(false);
      setIsFolder(true);
    } else {
      const newPath = folderPath.slice(0, -1);
      setFolderPath(newPath);
      setFolderId(newPath[newPath.length - 1].id);
      setIsFolder(true); // Parent is always a folder
    }
  };

  const navigateToRoot = () => {
    setFolderId(null);
    setFolderPath([]);
    setFlatMode(false);
    setIsFolder(true);
  };

  const items: UsbMenuItem[] = flatMode ? [] : folderId === null ? (menu?.items ?? []) : (folder?.items ?? []);
  const tracks: UsbTrack[] = flatMode ? (rootTracks?.tracks ?? []) : folderId === null ? [] : (folder?.tracks ?? []);
  const isLoading = flatMode ? !rootTracks : folderId === null ? menuLoading : folderLoading;

  const lastClickedIndex = useRef<number | null>(null);

  const toggleTrack = (id: number, index: number, shiftKey: boolean) => {
    const next = new Set(selectedIds);

    if (shiftKey && lastClickedIndex.current !== null) {
      // Range select: select all tracks between last click and current
      const start = Math.min(lastClickedIndex.current, index);
      const end = Math.max(lastClickedIndex.current, index);
      for (let i = start; i <= end; i++) {
        next.add(tracks[i].rekordbox_id);
      }
    } else {
      if (next.has(id)) next.delete(id);
      else next.add(id);
    }

    lastClickedIndex.current = index;
    onSelectionChange(next);
  };

  const selectAll = () => {
    const next = new Set(selectedIds);
    for (const t of tracks) next.add(t.rekordbox_id);
    onSelectionChange(next);
  };

  const deselectAll = () => {
    const next = new Set(selectedIds);
    for (const t of tracks) next.delete(t.rekordbox_id);
    onSelectionChange(next);
  };

  return (
    <div className="space-y-2">
      {/* Breadcrumb */}
      <div className="flex items-center gap-1 text-xs text-gray-400">
        <button onClick={navigateToRoot} className="hover:text-gray-200 transition-colors">
          Root
        </button>
        {folderPath.map((crumb, i) => (
          <span key={crumb.id} className="flex items-center gap-1">
            <span className="text-gray-600">/</span>
            <button
              onClick={() => {
                setFolderPath((p) => p.slice(0, i + 1));
                setFolderId(crumb.id);
                setIsFolder(true); // Breadcrumb targets are always folders
              }}
              className="hover:text-gray-200 transition-colors"
            >
              {crumb.name}
            </button>
          </span>
        ))}
      </div>

      {(folderId !== null || flatMode) && (
        <button
          onClick={navigateUp}
          className="text-xs text-gray-500 hover:text-gray-300 transition-colors"
        >
          .. (up)
        </button>
      )}

      {isLoading ? (
        <div className="text-gray-500 text-sm animate-pulse">Loading...</div>
      ) : (
        <div className="overflow-auto rounded border border-gray-800" style={{ maxHeight: 350 }}>
          {/* Folders */}
          {items.filter((i) => i.is_folder).map((item) => {
            const isUnsupported = folderId === null && UNSUPPORTED_MENUS.has(item.name.toUpperCase());
            return (
              <div
                key={`folder-${item.id}`}
                onClick={() => navigateToFolder(item)}
                className={`px-3 py-2 flex items-center gap-2 text-sm border-b border-gray-800/50 transition-colors ${
                  isUnsupported
                    ? "text-gray-600 cursor-not-allowed"
                    : "text-blue-400 hover:bg-gray-800/40 cursor-pointer"
                }`}
                title={isUnsupported ? "Browse by this category is not yet supported" : undefined}
              >
                <span className="text-gray-500">📁</span>
                {item.name}
                {isUnsupported && <span className="text-gray-700 text-xs ml-auto">coming soon</span>}
              </div>
            );
          })}

          {/* Tracks */}
          {tracks.length > 0 && (
            <>
              <div className="px-3 py-1.5 flex items-center justify-between border-b border-gray-800 bg-gray-900/50">
                <span className="text-xs text-gray-500">
                  {tracks.length} track{tracks.length !== 1 ? "s" : ""}
                </span>
                <div className="flex items-center gap-2">
                  <button onClick={selectAll} className="text-xs text-blue-400 hover:text-blue-300">
                    Select All
                  </button>
                  <button onClick={deselectAll} className="text-xs text-gray-500 hover:text-gray-300">
                    Deselect All
                  </button>
                </div>
              </div>
              {tracks.map((track, index) => {
                const isScanned = scannedIds.has(track.rekordbox_id);
                const isSelected = selectedIds.has(track.rekordbox_id);
                return (
                  <div
                    key={`${track.rekordbox_id}-${index}`}
                    onClick={(e) => toggleTrack(track.rekordbox_id, index, e.shiftKey)}
                    className={`px-3 py-2 flex items-center gap-3 text-sm border-b border-gray-800/50 cursor-pointer transition-colors ${
                      isSelected ? "bg-blue-900/20" : "hover:bg-gray-800/30"
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={(e) => toggleTrack(track.rekordbox_id, index, e.nativeEvent.shiftKey ?? false)}
                      onClick={(e) => e.stopPropagation()}
                      className="rounded border-gray-600 bg-gray-800 text-blue-500 focus:ring-blue-500"
                    />
                    <div className="flex-1 min-w-0">
                      <span className="text-gray-300 truncate block">{track.title}</span>
                      <span className="text-gray-500 text-xs truncate block">{track.artist}</span>
                    </div>
                    {isScanned && (
                      <span className="text-xs text-green-500 shrink-0">scanned</span>
                    )}
                  </div>
                );
              })}
            </>
          )}

          {items.length === 0 && tracks.length === 0 && (
            <div className="px-3 py-4 text-gray-500 text-sm text-center">Empty</div>
          )}
        </div>
      )}
    </div>
  );
}
