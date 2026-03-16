import { useUIStore } from "../../stores/uiStore.ts";

export function Console() {
  const { consoleOpen, toggleConsole } = useUIStore();

  return (
    <div className="border-t border-gray-800 bg-gray-950">
      <button
        onClick={toggleConsole}
        className="w-full px-4 py-1.5 text-xs text-gray-500 hover:text-gray-300 flex items-center gap-2 transition-colors"
      >
        <span>{consoleOpen ? "\u25BC" : "\u25B6"}</span>
        <span>Console</span>
      </button>
      {consoleOpen && (
        <div className="h-48 overflow-y-auto px-4 py-2 font-mono text-xs text-gray-500">
          <p>Console output will appear here.</p>
        </div>
      )}
    </div>
  );
}
