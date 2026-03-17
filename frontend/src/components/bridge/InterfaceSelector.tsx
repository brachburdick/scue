import { useInterfaces, updateBridgeInterface } from "../../api/network";
import { useBridgeStore } from "../../stores/bridgeStore";
import { InterfaceRow } from "./InterfaceRow";

export function InterfaceSelector({
  onInterfaceChanged,
}: {
  onInterfaceChanged: () => void;
}) {
  const isStartingUp = useBridgeStore((s) => s.isStartingUp);
  const { data, isLoading, isFetching, error, refetch } = useInterfaces({
    enabled: !isStartingUp,
  });

  if (isStartingUp) {
    return (
      <div className="space-y-2">
        <h3 className="text-xs font-medium uppercase tracking-wide text-gray-500">
          Network Interfaces
        </h3>
        <div className="rounded-lg border border-dashed border-gray-800 px-4 py-5 text-center">
          <p className="text-xs text-gray-600">Waiting for application startup…</p>
        </div>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="text-sm text-gray-500">Loading interfaces...</div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center gap-3 text-sm text-red-400">
        <span>Failed to load interfaces: {(error as Error).message}</span>
        <button
          onClick={() => refetch()}
          className="text-xs text-gray-400 hover:text-white transition-colors underline underline-offset-2"
        >
          Retry
        </button>
      </div>
    );
  }

  if (!data || data.interfaces.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-gray-700 px-4 py-6 text-center space-y-3">
        <p className="text-sm text-gray-500">
          No network interfaces detected. Connect an Ethernet cable.
        </p>
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="text-xs text-gray-400 hover:text-white transition-colors disabled:opacity-40"
        >
          {isFetching ? "Refreshing…" : "↺ Refresh"}
        </button>
      </div>
    );
  }

  const handleSelect = async (name: string) => {
    if (name === data.configured_interface) return;
    try {
      await updateBridgeInterface(name);
      onInterfaceChanged();
      refetch();
    } catch (err) {
      console.error("Failed to update interface:", err);
    }
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-medium uppercase tracking-wide text-gray-500">
          Network Interfaces
        </h3>
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          title="Refresh interface list"
          className="text-gray-600 hover:text-gray-300 transition-colors disabled:opacity-40"
          aria-label="Refresh interfaces"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 16 16"
            fill="currentColor"
            className={`w-3.5 h-3.5 ${isFetching ? "animate-spin" : ""}`}
          >
            <path
              fillRule="evenodd"
              d="M13.836 2.477a.75.75 0 0 1 .75.75v3.182a.75.75 0 0 1-.75.75h-3.182a.75.75 0 0 1 0-1.5h1.37l-.84-.841a4.5 4.5 0 0 0-7.08 1.01.75.75 0 0 1-1.3-.75 6 6 0 0 1 9.44-1.347l.842.841V3.227a.75.75 0 0 1 .75-.75Zm-.911 7.5A.75.75 0 0 1 13.199 11a6 6 0 0 1-9.44 1.347l-.842-.841v1.225a.75.75 0 0 1-1.5 0V9.55a.75.75 0 0 1 .75-.75h3.182a.75.75 0 0 1 0 1.5H4.013l.841.841A4.5 4.5 0 0 0 11.933 10a.75.75 0 0 1 1.992-.023Z"
              clipRule="evenodd"
            />
          </svg>
        </button>
      </div>
      {data.interfaces.map((iface) => (
        <InterfaceRow
          key={iface.name}
          iface={iface}
          isConfigured={iface.name === data.configured_interface}
          isRecommended={iface.name === data.recommended_interface}
          onSelect={handleSelect}
        />
      ))}
    </div>
  );
}
