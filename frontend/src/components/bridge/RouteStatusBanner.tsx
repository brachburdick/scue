import { useRouteStatus, useRouteSetupStatus, useFixRoute } from "../../api/network";

export function RouteStatusBanner() {
  const { data: route, refetch: refetchRoute } = useRouteStatus();
  const { data: setup } = useRouteSetupStatus();
  const fixMutation = useFixRoute();

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

  // Route is wrong
  const canFix = setup?.sudoers_installed ?? false;

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
    </div>
  );
}
