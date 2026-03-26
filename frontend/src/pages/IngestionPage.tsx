import { useState } from "react";
import { useTracks } from "../api/tracks";
import { LibraryTab } from "../components/ingestion/LibraryTab";
import { HardwareTab } from "../components/ingestion/HardwareTab";
import { AudioTab } from "../components/ingestion/AudioTab";
import { Component, type ReactNode, type ErrorInfo } from "react";

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
        </div>
      );
    }
    return this.props.children;
  }
}
import { TrackLibraryTable } from "../components/ingestion/TrackLibraryTable";
import type { IngestionTab } from "../types/ingestion";

const TABS: { id: IngestionTab; label: string }[] = [
  { id: "library", label: "Library" },
  { id: "hardware", label: "Hardware" },
  { id: "audio", label: "Audio Files" },
];

export function IngestionPage() {
  const [activeTab, setActiveTab] = useState<IngestionTab>("library");
  const [search, setSearch] = useState("");

  const { data: trackData, refetch } = useTracks({ limit: 1000 });
  const tracks = trackData?.tracks ?? [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Ingestion</h1>
        <button
          onClick={() => refetch()}
          className="px-3 py-1.5 text-xs font-medium rounded bg-gray-800 hover:bg-gray-700 text-gray-300 transition-colors"
        >
          Refresh
        </button>
      </div>

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

      {/* Tab content */}
      <TabErrorBoundary key={activeTab}>
        <div>
          {activeTab === "library" && <LibraryTab />}
          {activeTab === "hardware" && <HardwareTab />}
          {activeTab === "audio" && <AudioTab />}
        </div>
      </TabErrorBoundary>

      {/* Track Library Table — always visible */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-medium text-gray-300">
            Track Library
            <span className="text-gray-500 font-normal ml-2">
              {tracks.length} track{tracks.length !== 1 ? "s" : ""}
            </span>
          </h2>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search tracks..."
            className="px-3 py-1.5 text-sm rounded border border-gray-700 bg-gray-800 text-gray-300 placeholder-gray-500 w-64 focus:outline-none focus:border-blue-500"
          />
        </div>
        <TrackLibraryTable data={tracks} globalFilter={search} />
      </div>
    </div>
  );
}
