import { useConsoleStore } from "../../stores/consoleStore";
import { useUIStore } from "../../stores/uiStore";

interface ConsoleHeaderProps {
  onStopRecording: () => void;
  isSaving: boolean;
}

export function ConsoleHeader({ onStopRecording, isSaving }: ConsoleHeaderProps) {
  const { consoleOpen, toggleConsole } = useUIStore();
  const verboseMode = useConsoleStore((s) => s.verboseMode);
  const isRecording = useConsoleStore((s) => s.isRecording);
  const setVerboseMode = useConsoleStore((s) => s.setVerboseMode);
  const startRecording = useConsoleStore((s) => s.startRecording);
  const clearEntries = useConsoleStore((s) => s.clearEntries);

  return (
    <div className="flex items-center justify-between px-4 py-1.5">
      {/* Left: chevron + label */}
      <button
        onClick={toggleConsole}
        className="flex items-center gap-2 text-xs text-gray-500 hover:text-gray-300 transition-colors"
        aria-label={consoleOpen ? "Collapse console" : "Expand console"}
      >
        <span>{consoleOpen ? "\u25BC" : "\u25B6"}</span>
        <span>Console</span>
        {/* Pulsing red dot visible even when collapsed */}
        {isRecording && !isSaving && (
          <span className="inline-block w-2 h-2 rounded-full bg-red-500 animate-pulse" />
        )}
      </button>

      {/* Right: controls */}
      <div className="flex items-center gap-2">
        {/* Mode toggle */}
        <button
          onClick={() => setVerboseMode(!verboseMode)}
          className={`px-2 py-0.5 rounded text-xs transition-colors ${
            verboseMode
              ? "bg-gray-700 text-gray-200"
              : "bg-gray-800 text-gray-500 hover:text-gray-300"
          }`}
          aria-label={verboseMode ? "Switch to Clean mode" : "Switch to Verbose mode"}
        >
          {verboseMode ? "Verbose" : "Clean"}
        </button>

        {/* Record button */}
        {isSaving ? (
          <button
            disabled
            className="px-2 py-0.5 text-xs text-gray-400"
            aria-label="Saving recording"
          >
            {/* Spinner */}
            <svg
              className="animate-spin h-3 w-3"
              viewBox="0 0 24 24"
              fill="none"
            >
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
              />
            </svg>
          </button>
        ) : isRecording ? (
          <button
            onClick={onStopRecording}
            className="flex items-center gap-1 px-2 py-0.5 rounded text-xs text-red-500 hover:text-red-400 transition-colors"
            aria-label="Stop recording"
          >
            <span className="inline-block w-2 h-2 rounded-full bg-red-500 animate-pulse" />
            <span>Stop</span>
          </button>
        ) : (
          <button
            onClick={startRecording}
            className="px-2 py-0.5 rounded text-xs text-gray-500 hover:text-gray-300 transition-colors"
            aria-label="Start recording"
          >
            {/* Circle icon (outline) */}
            <span className="inline-block w-3 h-3 rounded-full border border-current" />
          </button>
        )}

        {/* Clear button */}
        <button
          onClick={clearEntries}
          className="px-2 py-0.5 rounded text-xs text-gray-500 hover:text-gray-300 transition-colors"
          aria-label="Clear console"
        >
          &times;
        </button>
      </div>
    </div>
  );
}
