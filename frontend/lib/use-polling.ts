"use client";

import { useEffect, useState } from "react";

/**
 * Poll an async loader on an interval, starting immediately.
 *
 * Runs are live: they wake, act, and sleep on their own, so the UI subscribes
 * to the API rather than rendering a single snapshot. Polling is deliberate
 * here — it keeps the client trivial, and the API is local.
 */
export function usePolling(load: () => Promise<void>, intervalMs: number): void {
  useEffect(() => {
    // Every state update inside `load` happens after an await; this effect is
    // a subscription to an external system, which is what effects are for.
    void load();
    const timer = setInterval(() => {
      void load();
    }, intervalMs);
    return () => clearInterval(timer);
  }, [load, intervalMs]);
}

/** A clock that ticks so countdowns re-render without refetching. */
export function useNow(intervalMs = 1000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(timer);
  }, [intervalMs]);
  return now;
}
