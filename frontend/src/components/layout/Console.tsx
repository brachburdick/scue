import { useState, useCallback } from "react";
import { useUIStore } from "../../stores/uiStore";
import { useConsoleStore } from "../../stores/consoleStore";
import { ConsoleHeader } from "./ConsoleHeader";
import { ConsolePanel } from "./ConsolePanel";
import { exportConsoleLog } from "../../utils/consoleExport";

export function Console() {
  const consoleOpen = useUIStore((s) => s.consoleOpen);
  const [isSaving, setIsSaving] = useState(false);

  const handleStopRecording = useCallback(() => {
    const buffer = useConsoleStore.getState().stopRecording();
    setIsSaving(true);
    // Brief saving state, then trigger export
    try {
      exportConsoleLog(buffer);
    } finally {
      setIsSaving(false);
    }
  }, []);

  return (
    <div className="border-t border-gray-800 bg-gray-950">
      <ConsoleHeader onStopRecording={handleStopRecording} isSaving={isSaving} />
      {consoleOpen && <ConsolePanel />}
    </div>
  );
}
