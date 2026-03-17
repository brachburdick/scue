import { useInterfaces, updateBridgeInterface } from "../../api/network";
import { InterfaceRow } from "./InterfaceRow";

export function InterfaceSelector({
  onInterfaceChanged,
}: {
  onInterfaceChanged: () => void;
}) {
  const { data, isLoading, error, refetch } = useInterfaces();

  if (isLoading) {
    return (
      <div className="text-sm text-gray-500">Loading interfaces...</div>
    );
  }

  if (error) {
    return (
      <div className="text-sm text-red-400">
        Failed to load interfaces: {(error as Error).message}
      </div>
    );
  }

  if (!data || data.interfaces.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-gray-700 px-4 py-6 text-center">
        <p className="text-sm text-gray-500">
          No network interfaces detected. Connect an Ethernet cable.
        </p>
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
      <h3 className="text-xs font-medium uppercase tracking-wide text-gray-500">
        Network Interfaces
      </h3>
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
