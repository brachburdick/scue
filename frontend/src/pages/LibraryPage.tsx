import { Component, type ReactNode, type ErrorInfo } from "react";
import { RekordboxTab } from "../components/ingestion/RekordboxTab";
import { HardwareTab } from "../components/ingestion/HardwareTab";
import { AudioTab } from "../components/ingestion/AudioTab";
import { ScueLibraryTab } from "../components/library/ScueLibraryTab";
import { ImportSettingsBar } from "../components/library/ImportSettingsBar";
import { useLibraryStore } from "../stores/libraryStore";
import type { LibraryTab } from "../types/library";

class TabErrorBoundary extends Component<
  { children: ReactNode },
  { error: Error | null }
> {
  state: { error: Error | null } = { error: null };
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("TabErrorBoundary caught:", error, info.componentStack);
  }
  render() {
    if (this.state.error) {
      return (
        <div className="rounded border border-red-800 bg-red-900/20 p-4 text-sm text-red-400">
          <p className="font-medium">Tab render error</p>
          <pre className="mt-2 text-xs text-red-300 whitespace-pre-wrap">
            {this.state.error.message}
          </pre>
          {this.state.error.stack && (
            <pre className="mt-1 text-xs text-red-400/60 whitespace-pre-wrap">
              {this.state.error.stack}
            </pre>
          )}
        </div>
      );
    }
    return this.props.children;
  }
}

const TABS: { id: LibraryTab; label: string }[] = [
  { id: "rekordbox", label: "Rekordbox" },
  { id: "hardware", label: "Hardware" },
  { id: "audio", label: "Audio Files" },
  { id: "scue_library", label: "SCUE Library" },
];

const IMPORT_TABS: Set<LibraryTab> = new Set(["rekordbox", "hardware", "audio"]);

export function LibraryPage() {
  const activeTab = useLibraryStore((s) => s.activeTab);
  const setActiveTab = useLibraryStore((s) => s.setActiveTab);

  return (
    <div className="space-y-4">
      {/* Header */}
      <h1 className="text-xl font-semibold">Library</h1>

      {/* Tabs */}
      <div className="flex items-center gap-1 border-b border-gray-800">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${
              activeTab === tab.id
                ? "border-blue-500 text-blue-400"
                : "border-transparent text-gray-400 hover:text-gray-200"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Import Settings Bar — shown on import tabs only */}
      {IMPORT_TABS.has(activeTab) && <ImportSettingsBar />}

      {/* Tab content */}
      <TabErrorBoundary key={activeTab}>
        <div>
          {activeTab === "rekordbox" && <RekordboxTab />}
          {activeTab === "hardware" && <HardwareTab />}
          {activeTab === "audio" && <AudioTab />}
          {activeTab === "scue_library" && <ScueLibraryTab />}
        </div>
      </TabErrorBoundary>
    </div>
  );
}
