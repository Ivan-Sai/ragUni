"use client";

import { useEffect } from "react";
import { initSentryClient } from "@/lib/sentry";

/**
 * Client-only wrapper that fires Sentry initialisation exactly once on
 * mount. Wrapped in a dedicated component so the call happens *after*
 * hydration, avoiding any risk of the SDK pulling in browser-only APIs
 * during server rendering.
 */
export function SentryProvider({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    void initSentryClient();
  }, []);

  return <>{children}</>;
}
