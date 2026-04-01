import { useEffect } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "sonner";
import { Shell } from "./components/layout/Shell.tsx";
import { BridgePage } from "./pages/BridgePage.tsx";
import { EnrichmentPage } from "./pages/EnrichmentPage.tsx";
import { LogsPage } from "./pages/LogsPage.tsx";
import { NetworkPage } from "./pages/NetworkPage.tsx";
import { LiveDeckMonitorPage } from "./pages/LiveDeckMonitorPage.tsx";
import { DetectorTuningPage } from "./pages/DetectorTuningPage.tsx";
import { AnnotationPage } from "./pages/AnnotationPage.tsx";
import { WaveformTuningPage } from "./pages/WaveformTuningPage.tsx";
import { LibraryPage } from "./pages/LibraryPage.tsx";
import { AnalysisPage } from "./pages/AnalysisPage.tsx";
import { connectWebSocket, disconnectWebSocket } from "./api/ws";
import { useWaveformPresetStore } from "./stores/waveformPresetStore";

function App() {
  useEffect(() => {
    connectWebSocket();
    useWaveformPresetStore.getState().fetchPresets();
    return () => disconnectWebSocket();
  }, []);

  return (
    <>
    <Toaster position="top-right" theme="dark" richColors closeButton />
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<Navigate to="/library" replace />} />
        <Route path="library" element={<LibraryPage />} />
        <Route path="analysis" element={<AnalysisPage />} />
        <Route path="live" element={<LiveDeckMonitorPage />} />
        <Route path="data/bridge" element={<BridgePage />} />
        <Route path="data/enrichment" element={<EnrichmentPage />} />
        <Route path="logs" element={<LogsPage />} />
        <Route path="network" element={<NetworkPage />} />
        <Route path="dev/detectors" element={<DetectorTuningPage />} />
        <Route path="dev/annotate" element={<AnnotationPage />} />
        <Route path="dev/waveforms" element={<WaveformTuningPage />} />
        {/* Redirects from old routes */}
        <Route path="ingestion" element={<Navigate to="/library" replace />} />
        <Route path="data/db" element={<Navigate to="/library" replace />} />
        <Route path="strata" element={<Navigate to="/analysis" replace />} />
      </Route>
    </Routes>
    </>
  );
}

export default App;
