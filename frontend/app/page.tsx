"use client";

import Link from "next/link";
import { useCallback, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { countdown, durationSince } from "@/lib/format";
import type { RunSummary } from "@/lib/types";
import { usePolling, useNow } from "@/lib/use-polling";
import { Card, EmptyState, ErrorBanner, Stat, StatusBadge } from "@/components/ui";

const REFRESH_MS = 3000;

/** Runs needing a human eye: paused, terminated, or overdue for a wake. */
function needsAttention(run: RunSummary, now: number): boolean {
  if (run.status === "PAUSED" || run.status === "TERMINATED") return true;
  if (run.status === "SLEEPING" && run.next_wake_at) {
    return new Date(run.next_wake_at).getTime() < now - 60_000;
  }
  return false;
}

export default function DashboardPage() {
  const [runs, setRuns] = useState<RunSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const now = useNow();

  const load = useCallback(async () => {
    try {
      setRuns(await api.listRuns());
      setError(null);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not load runs");
    }
  }, []);

  usePolling(load, REFRESH_MS);

  const active = runs?.filter((run) => run.status === "ACTING") ?? [];
  const sleeping = runs?.filter((run) => run.status === "SLEEPING") ?? [];
  const attention = runs?.filter((run) => needsAttention(run, now)) ?? [];
  const completed = runs?.filter((run) => run.status === "COMPLETED") ?? [];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Operations dashboard</h1>
          <p className="mt-1 text-sm text-slate-600">
            Every supervised order, and what each one is doing right now.
          </p>
        </div>
        <Link
          href="/runs/new"
          className="rounded-md bg-teal-700 px-3 py-1.5 text-sm font-medium text-white transition hover:bg-teal-800"
        >
          Start a run
        </Link>
      </div>

      <ErrorBanner message={error} />

      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Acting" value={active.length} />
        <Stat label="Sleeping" value={sleeping.length} />
        <Stat label="Attention" value={attention.length} />
        <Stat label="Completed" value={completed.length} />
      </dl>

      <Card title="Runs" subtitle={runs ? `${runs.length} total` : undefined}>
        {runs === null ? (
          <EmptyState>Loading runs…</EmptyState>
        ) : runs.length === 0 ? (
          <EmptyState>
            No runs yet. <Link href="/runs/new" className="text-teal-700 underline">Start one</Link>{" "}
            to see the supervisor work.
          </EmptyState>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[46rem] text-left text-sm">
              <thead className="text-[11px] uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="pb-2 pr-3 font-medium">Order</th>
                  <th className="pb-2 pr-3 font-medium">Status</th>
                  <th className="pb-2 pr-3 font-medium">Next wake</th>
                  <th className="pb-2 pr-3 font-medium">Last wake</th>
                  <th className="pb-2 pr-3 font-medium">Events</th>
                  <th className="pb-2 pr-3 font-medium">Wake-ups</th>
                  <th className="pb-2 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {runs.map((run) => (
                  <tr key={run.id} className="hover:bg-slate-50">
                    <td className="py-2 pr-3">
                      <Link
                        href={`/runs/${run.id}`}
                        className="font-medium text-teal-700 hover:underline"
                      >
                        {run.order_id}
                      </Link>
                    </td>
                    <td className="py-2 pr-3">
                      <StatusBadge
                        status={needsAttention(run, now) && run.status === "SLEEPING" ? "ATTENTION" : run.status}
                      />
                    </td>
                    <td className="py-2 pr-3 tabular-nums text-slate-600">
                      {run.completed_at ? "—" : countdown(run.next_wake_at, now)}
                    </td>
                    <td className="py-2 pr-3 tabular-nums text-slate-600">
                      {durationSince(run.last_wake_at, now)}
                    </td>
                    <td className="py-2 pr-3 tabular-nums">{run.stats.events_received ?? 0}</td>
                    <td className="py-2 pr-3 tabular-nums">{run.stats.agent_wakeups ?? 0}</td>
                    <td className="py-2 tabular-nums">{run.stats.actions_executed ?? 0}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
