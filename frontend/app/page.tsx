"use client";

import { motion } from "framer-motion";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Inbox,
  Moon,
  Plus,
  SlidersHorizontal,
  Zap,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useMemo, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { RunSummary, Supervisor } from "@/lib/types";
import { useNow, usePolling } from "@/lib/use-polling";
import { RunTile } from "@/components/run-tile";
import {
  Button,
  Card,
  EmptyState,
  ErrorBanner,
  Skeleton,
  Stat,
  Tabs,
  cx,
} from "@/components/ui";

const REFRESH_MS = 3000;

/** Runs needing a human eye: paused, terminated, or overdue for a wake. */
function needsAttention(run: RunSummary, now: number): boolean {
  if (run.status === "PAUSED" || run.status === "TERMINATED") return true;
  if (run.status === "AWAITING_APPROVAL") return true;
  if (run.status === "SLEEPING" && run.next_wake_at) {
    return new Date(run.next_wake_at).getTime() < now - 60_000;
  }
  return false;
}

type Filter = "all" | "live" | "attention" | "completed";

export default function DashboardPage() {
  const [runs, setRuns] = useState<RunSummary[] | null>(null);
  const [supervisors, setSupervisors] = useState<Supervisor[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const now = useNow();

  const load = useCallback(async () => {
    try {
      const [nextRuns, nextSupervisors] = await Promise.all([
        api.listRuns(),
        api.listSupervisors().catch(() => [] as Supervisor[]),
      ]);
      setRuns(nextRuns);
      setSupervisors(nextSupervisors);
      setError(null);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not load runs");
    }
  }, []);

  usePolling(load, REFRESH_MS);

  const buckets = useMemo(() => {
    const all = runs ?? [];
    return {
      all,
      acting: all.filter((run) => run.status === "ACTING"),
      sleeping: all.filter((run) => run.status === "SLEEPING"),
      attention: all.filter((run) => needsAttention(run, now)),
      completed: all.filter((run) => run.status === "COMPLETED"),
      live: all.filter((run) => !run.completed_at),
    };
  }, [runs, now]);

  const visible = buckets[filter === "all" ? "all" : filter];

  return (
    <div className="space-y-6">
      {/* ------------------------------------------------------------ hero */}
      <motion.section
        initial={{ opacity: 0, y: -6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35 }}
        className="hero-grid overflow-hidden rounded-2xl border border-ink-200 bg-white px-5 py-6 shadow-card sm:px-7 sm:py-8"
      >
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div className="max-w-2xl">
            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-brand-700">
              AI Order Operations
            </p>
            <h1 className="mt-1.5 text-2xl font-semibold tracking-tight text-ink-900 sm:text-3xl">
              Operations control center
            </h1>
            <p className="mt-2 text-sm leading-6 text-ink-500">
              Every supervised order, and what its AI supervisor is doing right now. Temporal owns
              each run&apos;s lifecycle — the agent is woken only when an event actually needs it.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link href="/supervisors">
              <Button variant="secondary" icon={SlidersHorizontal}>
                Supervisors
              </Button>
            </Link>
            <Link href="/runs/new">
              <Button icon={Plus}>Start a run</Button>
            </Link>
          </div>
        </div>

        <dl className="mt-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Stat
            label="Acting"
            value={runs ? buckets.acting.length : "—"}
            hint="agent deciding now"
            icon={Zap}
            tone="warn"
          />
          <Stat
            label="Sleeping"
            value={runs ? buckets.sleeping.length : "—"}
            hint="on a durable timer"
            icon={Moon}
          />
          <Stat
            label="Attention"
            value={runs ? buckets.attention.length : "—"}
            hint="paused, overdue, or awaiting you"
            icon={AlertTriangle}
            tone={buckets.attention.length > 0 ? "danger" : "neutral"}
          />
          <Stat
            label="Completed"
            value={runs ? buckets.completed.length : "—"}
            hint="reached a terminal rule"
            icon={CheckCircle2}
            tone="success"
          />
        </dl>
      </motion.section>

      <ErrorBanner message={error} onRetry={() => void load()} />

      {/* ------------------------------------------------------ attention */}
      {buckets.attention.length > 0 && filter !== "attention" && (
        <motion.div
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex flex-wrap items-center gap-3 rounded-xl border border-orange-200 bg-orange-50/70 px-4 py-3"
        >
          <AlertTriangle className="h-4 w-4 shrink-0 text-orange-600" strokeWidth={2.3} />
          <p className="text-sm text-orange-900">
            <span className="font-semibold">{buckets.attention.length}</span>{" "}
            {buckets.attention.length === 1 ? "run needs" : "runs need"} a human — paused,
            overdue for a wake, or waiting on an approval.
          </p>
          <Button
            variant="secondary"
            size="sm"
            className="ml-auto"
            onClick={() => setFilter("attention")}
          >
            Review them
          </Button>
        </motion.div>
      )}

      {/* ------------------------------------------------------------ runs */}
      <section className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-sm font-semibold tracking-tight text-ink-900">Supervised orders</h2>
          <Tabs
            active={filter}
            onChange={setFilter}
            tabs={[
              { id: "all", label: "All", count: buckets.all.length },
              { id: "live", label: "Live", count: buckets.live.length },
              { id: "attention", label: "Attention", count: buckets.attention.length },
              { id: "completed", label: "Completed", count: buckets.completed.length },
            ]}
          />
        </div>

        {runs === null ? (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {[0, 1, 2, 3, 4, 5].map((key) => (
              <div key={key} className="rounded-xl border border-ink-200 bg-white p-4 shadow-card">
                <Skeleton className="h-4 w-28" />
                <Skeleton className="mt-2 h-3 w-20" />
                <Skeleton className="mt-3 h-5 w-24 rounded-full" />
                <Skeleton className="mt-4 h-3 w-full" />
              </div>
            ))}
          </div>
        ) : visible.length === 0 ? (
          <Card>
            <EmptyState
              icon={Inbox}
              title={filter === "all" ? "No runs yet" : "Nothing in this view"}
              action={
                filter === "all" ? (
                  <Link href="/runs/new">
                    <Button size="sm" icon={Plus}>
                      Start your first run
                    </Button>
                  </Link>
                ) : (
                  <Button size="sm" variant="secondary" onClick={() => setFilter("all")}>
                    Show all runs
                  </Button>
                )
              }
            >
              {filter === "all"
                ? "Start a run to watch a durable AI supervisor take an order from creation to completion."
                : "Try another filter — the other views may have runs."}
            </EmptyState>
          </Card>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {visible.map((run, index) => (
              <RunTile
                key={run.id}
                run={run}
                now={now}
                index={index}
                attention={needsAttention(run, now)}
              />
            ))}
          </div>
        )}
      </section>

      {/* ---------------------------------------------------- supervisors */}
      <Card
        title="Supervisor policies"
        subtitle={`${supervisors.length} configured`}
        icon={SlidersHorizontal}
        action={
          <Link href="/supervisors">
            <Button variant="ghost" size="sm">
              Manage
            </Button>
          </Link>
        }
      >
        {supervisors.length === 0 ? (
          <EmptyState icon={SlidersHorizontal} title="No supervisors configured">
            A supervisor is the reusable policy a run is started from.
          </EmptyState>
        ) : (
          <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
            {supervisors.slice(0, 6).map((supervisor) => {
              const runCount = (runs ?? []).filter(
                (run) => run.supervisor_id === supervisor.id,
              ).length;
              return (
                <div
                  key={supervisor.id}
                  className="rounded-lg border border-ink-200 bg-white p-3 transition-colors duration-200 hover:border-brand-300 hover:bg-brand-50/30"
                >
                  <div className="flex items-start justify-between gap-2">
                    <p className="truncate text-xs font-semibold text-ink-900">{supervisor.name}</p>
                    <span className="tnum shrink-0 rounded bg-ink-100 px-1.5 py-0.5 text-[10px] font-semibold text-ink-600">
                      {runCount} {runCount === 1 ? "run" : "runs"}
                    </span>
                  </div>
                  <p className="mt-1 line-clamp-2 text-[11px] leading-4 text-ink-500">
                    {supervisor.base_instruction}
                  </p>
                  <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[10px] text-ink-500">
                    <span
                      className={cx(
                        "rounded px-1.5 py-0.5 font-semibold ring-1 ring-inset",
                        supervisor.config.wake_aggressiveness === "HIGH"
                          ? "bg-orange-50 text-orange-700 ring-orange-200"
                          : supervisor.config.wake_aggressiveness === "LOW"
                            ? "bg-ink-50 text-ink-600 ring-ink-200"
                            : "bg-sky-50 text-sky-700 ring-sky-200",
                      )}
                    >
                      {supervisor.config.wake_aggressiveness ?? "BALANCED"}
                    </span>
                    <span className="inline-flex items-center gap-1">
                      <Activity className="h-3 w-3" strokeWidth={2.2} />
                      every {supervisor.config.default_wake_minutes ?? 60}m
                    </span>
                    {(supervisor.config.require_approval_for?.length ?? 0) > 0 && (
                      <span className="text-orange-600">approval gate</span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Card>
    </div>
  );
}
