import type { DeviceInfo } from "../../types";

export function DeviceCard({
  ip,
  device,
}: {
  ip: string;
  device: DeviceInfo;
}) {
  return (
    <div className="flex items-center justify-between rounded-lg border border-gray-700 bg-gray-800/50 px-4 py-3">
      <div className="flex items-center gap-3">
        <span className="text-sm font-medium text-white">
          {device.device_name}
        </span>
        <span className="rounded bg-gray-700 px-2 py-0.5 text-xs text-gray-300 uppercase">
          {device.device_type}
        </span>
        {device.uses_dlp && (
          <span className="rounded bg-blue-900/50 px-2 py-0.5 text-xs text-blue-400">
            DLP
          </span>
        )}
      </div>
      <div className="flex items-center gap-3 text-xs text-gray-500">
        <span>#{device.device_number}</span>
        <span>{ip}</span>
      </div>
    </div>
  );
}
