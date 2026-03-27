import { useEffect } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "sonner";
import { Shell } from "./components/layout/Shell.tsx";
import { TracksPage } from "./pages/TracksPage.tsx";
import { BridgePage } from "./pages/BridgePage.tsx";
import { EnrichmentPage } from "./pages/EnrichmentPage.tsx";
import { LogsPage } from "./pages/LogsPage.tsx";
import { NetworkPage } from "./pages/NetworkPage.tsx";
import { AnalysisViewerPage } from "./pages/AnalysisViewerPage.tsx";
import { LiveDeckMonitorPage } from "./pages/LiveDeckMonitorPage.tsx";
import { DetectorTuningPage } from "./pages/DetectorTuningPage.tsx";
import { AnnotationPage } from "./pages/AnnotationPage.tsx";
import { StrataPage } from "./pages/StrataPage.tsx";
import { WaveformTuningPage } from "./pages/WaveformTuningPage.tsx";
import { IngestionPage } from "./pages/IngestionPage.tsx";
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
        <Route index element={<Navigate to="/data/db" replace />} />
        <Route path="strata" element={<StrataPage />} />
        <Route path="analysis" element={<AnalysisViewerPage />} />
        <Route path="live" element={<LiveDeckMonitorPage />} />
        <Route path="ingestion" element={<IngestionPage />} />
        <Route path="data/db" element={<TracksPage />} />
        <Route path="data/bridge" element={<BridgePage />} />
        <Route path="data/enrichment" element={<EnrichmentPage />} />
        <Route path="logs" element={<LogsPage />} />
        <Route path="network" element={<NetworkPage />} />
        <Route path="dev/detectors" element={<DetectorTuningPage />} />
        <Route path="dev/annotate" element={<AnnotationPage />} />
        <Route path="dev/waveforms" element={<WaveformTuningPage />} />
      </Route>
    </Routes>
    </>
  );
}

export default App;
