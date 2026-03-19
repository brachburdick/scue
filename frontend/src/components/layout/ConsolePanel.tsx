import { useEffect, useRef } from "react";
import { useConsoleStore } from "../../stores/consoleStore";
import { LogEntry } from "./LogEntry";

export function ConsolePanel() {
  const entries = useConsoleStore((s) => s.entries);
  const verboseMode = useConsoleStore((s) => s.verboseMode);
  const scrollRef = useRef<HTMLDivElement>(null);
  const isAtBottomRef = useRef(true);

  const filtered = verboseMode ? entries : entries.filter((e) => !e.verbose);

  // Track whether user is at the bottom
  function handleScroll() {
    const el = scrollRef.current;
    if (!el) return;
    isAtBottomRef.current = el.scrollTop + el.clientHeight >= el.scrollHeight - 20;
  }

  // Auto-scroll to bottom when new entries arrive (if user is at bottom)
  useEffect(() => {
    const el = scrollRef.current;
    if (el && isAtBottomRef.current) {
      el.scrollTop = el.scrollHeight;
    }
  }, [filtered.length]);

  if (filtered.length === 0) {
    return (
      <div className="h-48 flex items-center justify-center text-xs text-gray-600">
        No console entries yet.
      </div>
    );
  }

  return (
    <div
      ref={scrollRef}
      onScroll={handleScroll}
      className="h-48 overflow-y-auto"
      role="log"
      aria-live="polite"
    >
      {filtered.map((entry) => (
        <LogEntry key={entry.id} entry={entry} />
      ))}
    </div>
  );
}
