import { useEffect } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { Shell } from "./components/layout/Shell.tsx";
import { TracksPage } from "./pages/TracksPage.tsx";
import { BridgePage } from "./pages/BridgePage.tsx";
import { EnrichmentPage } from "./pages/EnrichmentPage.tsx";
import { LogsPage } from "./pages/LogsPage.tsx";
import { NetworkPage } from "./pages/NetworkPage.tsx";
import { AnalysisViewerPage } from "./pages/AnalysisViewerPage.tsx";
import { LiveDeckMonitorPage } from "./pages/LiveDeckMonitorPage.tsx";
import { DetectorTuningPage } from "./pages/DetectorTuningPage.tsx";
import { connectWebSocket, disconnectWebSocket } from "./api/ws";

function App() {
  useEffect(() => {
    connectWebSocket();
    return () => disconnectWebSocket();
  }, []);

  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<Navigate to="/data/db" replace />} />
        <Route path="analysis" element={<AnalysisViewerPage />} />
        <Route path="live" element={<LiveDeckMonitorPage />} />
        <Route path="data/db" element={<TracksPage />} />
        <Route path="data/bridge" element={<BridgePage />} />
        <Route path="data/enrichment" element={<EnrichmentPage />} />
        <Route path="logs" element={<LogsPage />} />
        <Route path="network" element={<NetworkPage />} />
        <Route path="dev/detectors" element={<DetectorTuningPage />} />
      </Route>
    </Routes>
  );
}

export default App;
