/** Shared QueryClient instance.
 *
 * Extracted from main.tsx so non-React modules (e.g., ws.ts) can
 * import the client for programmatic query invalidation without
 * needing a React context.
 */

import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
    },
  },
});
