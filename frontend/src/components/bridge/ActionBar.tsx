import { useEffect, useState } from "react";
import { useRestartBridge } from "../../api/network";
import { useBridgeStore } from "../../stores/bridgeStore";

export function ActionBar({
  pendingChanges,
}: {
  pendingChanges: boolean;
}) {
  const restartMutation = useRestartBridge();
  const status = useBridgeStore((s) => s.status);
  const wsConnected = useBridgeStore((s) => s.wsConnected);

  const isRecovering = useBridgeStore((s) => s.isRecovering);

  // S6: brief disable during recovery, then re-enable.
  // recoveryDisabled tracks the brief disable period at the start of recovery.
  const [recoveryDisabled, setRecoveryDisabled] = useState(false);

  useEffect(() => {
    if (isRecovering) {
      setRecoveryDisabled(true);
      const timer = setTimeout(() => setRecoveryDisabled(false), 2000);
      return () => clearTimeout(timer);
    }
    setRecoveryDisabled(false);
  }, [isRecovering]);

  // Determine status message and button state
  const getStateConfig = () => {
    // S7: WS disconnected
    if (!wsConnected) {
      return {
        message: "Backend unreachable.",
        buttonLabel: "Apply & Restart Bridge",
        buttonDisabled: true,
        tooltip: "Cannot restart — backend unreachable",
      };
    }

    // S3: crashed
    if (status === "crashed") {
      return {
        message: "Bridge crashed. Automatic restart in progress.",
        buttonLabel: "Apply & Restart Bridge",
        buttonDisabled: true,
        tooltip: "Wait for automatic restart to complete",
      };
    }

    // S4: starting
    if (status === "starting") {
      return {
        message: "Bridge starting…",
        buttonLabel: "Apply & Restart Bridge",
        buttonDisabled: true,
        tooltip: "Bridge is starting up",
      };
    }

    // S5: waiting_for_hardware — Force Restart enabled
    if (status === "waiting_for_hardware") {
      return {
        message: "Waiting for hardware.",
        buttonLabel: "Force Restart",
        buttonDisabled: false,
        tooltip: undefined,
      };
    }

    // S6: recovering — brief disable then enable
    if (isRecovering) {
      return {
        message: "Bridge reconnected. Refreshing data…",
        buttonLabel: "Apply & Restart Bridge",
        buttonDisabled: recoveryDisabled,
        tooltip: recoveryDisabled ? "Waiting for data refresh" : undefined,
      };
    }

    // S1/S2: normal running
    return {
      message: pendingChanges
        ? "Interface changed. Restart to apply."
        : "Bridge configuration is current.",
      buttonLabel: "Apply & Restart Bridge",
      buttonDisabled: false,
      tooltip: undefined,
    };
  };

  const config = getStateConfig();
  const isDisabled = config.buttonDisabled || restartMutation.isPending;

  return (
    <div className="flex items-center justify-between rounded-lg border border-gray-700 bg-gray-800/50 px-4 py-3">
      <div className="text-xs text-gray-400">{config.message}</div>
      <button
        type="button"
        onClick={() => restartMutation.mutate()}
        disabled={isDisabled}
        title={config.tooltip}
        className="rounded bg-blue-600 px-4 py-1.5 text-xs font-medium text-white hover:bg-blue-500 disabled:opacity-50"
      >
        {restartMutation.isPending ? "Restarting…" : config.buttonLabel}
      </button>
    </div>
  );
}
