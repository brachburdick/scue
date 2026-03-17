import { useRestartBridge } from "../../api/network";

export function ActionBar({
  pendingChanges,
}: {
  pendingChanges: boolean;
}) {
  const restartMutation = useRestartBridge();

  return (
    <div className="flex items-center justify-between rounded-lg border border-gray-700 bg-gray-800/50 px-4 py-3">
      <div className="text-xs text-gray-400">
        {pendingChanges
          ? "Interface changed. Restart to apply."
          : "Bridge configuration is current."}
      </div>
      <button
        type="button"
        onClick={() => restartMutation.mutate()}
        disabled={restartMutation.isPending}
        className="rounded bg-blue-600 px-4 py-1.5 text-xs font-medium text-white hover:bg-blue-500 disabled:opacity-50"
      >
        {restartMutation.isPending ? "Restarting..." : "Apply & Restart Bridge"}
      </button>
    </div>
  );
}
