import type { NetworkInterface } from "../../types";

const TYPE_BADGES: Record<string, { bg: string; text: string }> = {
  ethernet: { bg: "bg-blue-900/50", text: "text-blue-400" },
  wifi: { bg: "bg-purple-900/50", text: "text-purple-400" },
  vpn: { bg: "bg-orange-900/50", text: "text-orange-400" },
  virtual: { bg: "bg-gray-700", text: "text-gray-400" },
  other: { bg: "bg-gray-700", text: "text-gray-400" },
};

export function InterfaceRow({
  iface,
  isConfigured,
  isRecommended,
  onSelect,
}: {
  iface: NetworkInterface;
  isConfigured: boolean;
  isRecommended: boolean;
  onSelect: (name: string) => void;
}) {
  const badge = TYPE_BADGES[iface.type] ?? TYPE_BADGES.other;
  const ipv4 = iface.addresses.find((a) => a.family === "ipv4");

  return (
    <button
      type="button"
      onClick={() => onSelect(iface.name)}
      className={`w-full flex items-center justify-between rounded-lg border px-4 py-3 text-left transition-colors ${
        isConfigured
          ? "border-blue-500/50 bg-blue-900/20"
          : "border-gray-700 bg-gray-800/50 hover:border-gray-600"
      }`}
    >
      <div className="flex items-center gap-3">
        <span className="text-sm font-medium text-white">{iface.name}</span>
        <span
          className={`rounded px-2 py-0.5 text-xs ${badge.bg} ${badge.text}`}
        >
          {iface.type}
        </span>
        {iface.has_link_local && (
          <span className="rounded bg-green-900/50 px-2 py-0.5 text-xs text-green-400">
            Link-Local
          </span>
        )}
        {isRecommended && !isConfigured && (
          <span className="text-xs text-yellow-500">Recommended</span>
        )}
        {isConfigured && (
          <span className="text-xs text-blue-400">Active</span>
        )}
      </div>
      <div className="flex items-center gap-3 text-xs text-gray-500">
        {ipv4 && <span>{ipv4.address}</span>}
        <span
          className={iface.is_up ? "text-green-500" : "text-red-500"}
        >
          {iface.is_up ? "UP" : "DOWN"}
        </span>
        <span>Score: {iface.score}</span>
      </div>
    </button>
  );
}
