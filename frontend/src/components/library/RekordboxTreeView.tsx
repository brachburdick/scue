import { useState } from "react";
import type { PlaylistNode } from "../../types/ingestion";

interface RekordboxTreeViewProps {
  playlists: PlaylistNode[];
  selectedPlaylistId: number | null;
  onSelectPlaylist: (id: number | null, trackIds: number[]) => void;
}

export function RekordboxTreeView({ playlists, selectedPlaylistId, onSelectPlaylist }: RekordboxTreeViewProps) {
  return (
    <div className="overflow-auto rounded border border-gray-800 bg-gray-950 p-2" style={{ maxHeight: "calc(100vh - 400px)" }}>
      <button
        onClick={() => onSelectPlaylist(null, [])}
        className={`w-full text-left px-2 py-1 text-sm rounded transition-colors mb-1 ${
          selectedPlaylistId === null
            ? "bg-blue-900/30 text-blue-400"
            : "text-gray-400 hover:text-gray-200 hover:bg-gray-800"
        }`}
      >
        All Tracks
      </button>
      {playlists.map((node) => (
        <TreeNode
          key={node.id}
          node={node}
          depth={0}
          selectedId={selectedPlaylistId}
          onSelect={onSelectPlaylist}
        />
      ))}
    </div>
  );
}

function TreeNode({
  node,
  depth,
  selectedId,
  onSelect,
}: {
  node: PlaylistNode;
  depth: number;
  selectedId: number | null;
  onSelect: (id: number | null, trackIds: number[]) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const isSelected = selectedId === node.id;
  const hasChildren = node.children.length > 0;
  const paddingLeft = 8 + depth * 16;

  return (
    <div>
      <button
        className={`w-full text-left py-1 pr-2 text-sm rounded transition-colors flex items-center gap-1 ${
          isSelected
            ? "bg-blue-900/30 text-blue-400"
            : "text-gray-400 hover:text-gray-200 hover:bg-gray-800"
        }`}
        style={{ paddingLeft }}
        onClick={() => {
          if (node.is_folder) {
            setExpanded((e) => !e);
          } else {
            onSelect(node.id, node.track_ids ?? []);
          }
        }}
      >
        {node.is_folder ? (
          <span className={`text-[10px] transition-transform inline-block ${expanded ? "rotate-90" : ""}`}>
            ▶
          </span>
        ) : (
          <span className="text-gray-600 text-xs">♫</span>
        )}
        <span className="truncate">{node.name}</span>
        <span className="ml-auto text-xs text-gray-600 shrink-0">{node.track_count}</span>
      </button>
      {hasChildren && expanded && (
        <div>
          {node.children.map((child) => (
            <TreeNode
              key={child.id}
              node={child}
              depth={depth + 1}
              selectedId={selectedId}
              onSelect={onSelect}
            />
          ))}
        </div>
      )}
    </div>
  );
}
