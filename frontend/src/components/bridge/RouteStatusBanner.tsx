import { useEffect, useRef } from "react";
import { useRouteStatus, useRouteSetupStatus, useFixRoute } from "../../api/network";
import { useBridgeStore } from "../../stores/bridgeStore";

export function RouteStatusBanner() {
  const isStartingUp = useBridgeStore((s) => s.isStartingUp);
  const status = useBridgeStore((s) => s.status);
  const wsConnected = useBridgeStore((s) => s.wsConnected);
  const { data: route, refetch: refetchRoute } = useRouteStatus({
    enabled: !isStartingUp,
  });
  const { data: setup } = useRouteSetupStatus({ enabled: !isStartingUp });
  const fixMutation = useFixRoute();

  // Auto-fix the route once on startup if a mismatch is detected and sudoers
  // is installed. Fires at most once per page load via the ref guard.
  // Defense-in-depth: the bridge manager also attempts auto-fix before launch,
  // but macOS can reset the route after the subprocess starts.
  const hasAutoFixed = useRef(false);
  const canFix = setup?.sudoers_installed ?? false;

  useEffect(() => {
    if (
      !isStartingUp &&
      route &&
      route.route_applicable &&
      !route.correct &&
      canFix &&
      !hasAutoFixed.current &&
      !fixMutation.isPending
    ) {
      hasAutoFixed.current = true;
      fixMutation
        .mutateAsync(route.expected_interface!)
        .then(() => refetchRoute())
        .catch(() => {
          // Visible via fixMutation.isError — no silent swallow
        });
    }
  }, [isStartingUp, route, canFix]); // eslint-disable-line react-hooks/exhaustive-deps

  // S7: WS disconnected — override startup placeholder with specific message
  if (!wsConnected) {
    return (
      <div className="rounded-lg bg-gray-800/40 px-4 py-3">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-gray-700" />
          <span className="text-sm text-gray-600">Route status — backend unreachable</span>
        </div>
      </div>
    );
  }

  // S4: During startup, show a muted placeholder that matches the banner's layout weight
  if (isStartingUp) {
    return (
      <div className="rounded-lg bg-gray-800/40 px-4 py-3">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-gray-700" />
          <span className="text-sm text-gray-600">Route status — waiting for startup…</span>
        </div>
      </div>
    );
  }

  // S3: crashed — dimmed banner with explanation, no Fix Now button
  if (status === "crashed") {
    return (
      <div className="rounded-lg bg-gray-800/40 px-4 py-3 opacity-60">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-gray-600" />
          <span className="text-sm text-gray-500">
            Route status paused — bridge restarting…
          </span>
        </div>
      </div>
    );
  }

  // S5: waiting_for_hardware — dimmed banner with explanation
  if (status === "waiting_for_hardware") {
    return (
      <div className="rounded-lg bg-gray-800/40 px-4 py-3 opacity-60">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-gray-600" />
          <span className="text-sm text-gray-500">
            Route status unavailable — waiting for hardware
          </span>
        </div>
      </div>
    );
  }

  if (!route || !route.route_applicable) {
    return null; // Not macOS or not applicable
  }

  const handleFix = async () => {
    if (!route.expected_interface) return;
    try {
      await fixMutation.mutateAsync(route.expected_interface);
      refetchRoute();
    } catch {
      // Error handled by mutation state
    }
  };

  if (route.correct) {
    return (
      <div className="rounded-lg bg-green-900/30 px-4 py-3">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-green-500" />
          <span className="text-sm text-green-400">
            Route OK: 169.254.255.255 &rarr; {route.current_interface}
          </span>
        </div>
      </div>
    );
  }

  const competing: string[] = route.competing_interfaces ?? [];

  // Route is wrong
  return (
    <div className="rounded-lg bg-yellow-900/30 px-4 py-3 space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-yellow-500" />
          <span className="text-sm text-yellow-400">
            Route mismatch: 169.254.255.255 &rarr; {route.current_interface ?? "none"}
            {route.expected_interface && (
              <span className="text-gray-400">
                {" "}(should be {route.expected_interface})
              </span>
            )}
          </span>
        </div>
        {canFix && (
          <button
            type="button"
            onClick={handleFix}
            disabled={fixMutation.isPending}
            className="rounded bg-yellow-600 px-3 py-1 text-xs font-medium text-white hover:bg-yellow-500 disabled:opacity-50"
          >
            {fixMutation.isPending ? "Fixing..." : "Fix Now"}
          </button>
        )}
      </div>
      {!canFix && setup && (
        <div className="text-xs text-gray-400">
          Route fix not available. Run:{" "}
          <code className="rounded bg-gray-800 px-1.5 py-0.5 text-gray-300">
            {setup.setup_command}
          </code>
        </div>
      )}
      {fixMutation.isError && (
        <div className="text-xs text-red-400">
          Fix failed: {(fixMutation.error as Error).message}
        </div>
      )}
      {competing.length > 0 && (
        <div className="text-xs text-yellow-400/80">
          Competing subnet routes on: {competing.join(", ")}
          {canFix
            ? " — auto-fix will resolve on next startup"
            : `. Re-run: sudo ./tools/install-route-fix.sh ${route.expected_interface}`}
        </div>
      )}
    </div>
  );
}
