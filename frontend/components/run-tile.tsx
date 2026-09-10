"use client";

import { motion } from "framer-motion";
import { ArrowUpRight, Bell, Timer, Zap } from "lucide-react";
import Link from "next/link";
import { countdown, durationSince } from "@/lib/format";
import type { RunSummary } from "@/lib/types";
import { StatusBadge, cx } from "@/components/ui";

/**
 * A run as a card rather than a table row: the operator's question is "which
 * order needs me", and that is answered by status, countdown, and activity —
 * not by scanning columns.
 */
export function RunTile({
  run,
  now,
  attention,
  index = 0,
}: {
  run: RunSummary;
  now: number;
  attention: boolean;
  index?: number;
}) {
  const terminal = Boolean(run.completed_at);
  const status = attention && run.status === "SLEEPING" ? "ATTENTION" : run.status;
  const stats = run.stats ?? {};

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: Math.min(index * 0.035, 0.3) }}
    >
      <Link
        href={`/runs/${run.id}`}
        className={cx(
          "group relative flex h-full flex-col overflow-hidden rounded-xl border bg-white p-4 shadow-card transition-all duration-200",
          "hover:-translate-y-0.5 hover:shadow-pop focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2",
          attention ? "border-orange-300 hover:border-orange-400" : "border-ink-200 hover:border-brand-300",
        )}
      >
        {/* Accent rail communicates state before any text is read. */}
        <span
          className={cx(
            "absolute inset-y-0 left-0 w-1 transition-all duration-200 group-hover:w-1.5",
            attention
              ? "bg-orange-400"
              : run.status === "COMPLETED"
                ? "bg-emerald-400"
                : run.status === "TERMINATED"
                  ? "bg-rose-400"
                  : run.status === "ACTING"
                    ? "bg-amber-400"
                    : "bg-sky-300",
          )}
        />

        <div className="flex items-start justify-between gap-2 pl-1.5">
          <div className="min-w-0">
            <p className="truncate font-mono text-sm font-semibold tracking-tight text-ink-900">
              {run.order_id}
            </p>
            <p className="mt-0.5 text-[11px] text-ink-400">
              started {durationSince(run.created_at, now)}
            </p>
          </div>
          <ArrowUpRight
            className="h-4 w-4 shrink-0 text-ink-300 transition-all duration-200 group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-brand-600"
            strokeWidth={2.2}
          />
        </div>

        <div className="mt-2.5 pl-1.5">
          <StatusBadge status={status} pulse />
        </div>

        <div className="mt-3 flex items-center gap-3 border-t border-ink-100 pt-2.5 pl-1.5 text-[11px] text-ink-500">
          <span className="inline-flex items-center gap-1" title="Next scheduled wake">
            <Timer className="h-3 w-3" strokeWidth={2.2} />
            <span className="tnum">{terminal ? "—" : countdown(run.next_wake_at, now)}</span>
          </span>
          <span className="inline-flex items-center gap-1" title="Agent wake-ups">
            <Bell className="h-3 w-3" strokeWidth={2.2} />
            <span className="tnum">{stats.agent_wakeups ?? 0}</span>
          </span>
          <span className="inline-flex items-center gap-1" title="Actions executed">
            <Zap className="h-3 w-3" strokeWidth={2.2} />
            <span className="tnum">{stats.actions_executed ?? 0}</span>
          </span>
          <span className="ml-auto tnum text-ink-400" title="Events received">
            {stats.events_received ?? 0} events
          </span>
        </div>
      </Link>
    </motion.div>
  );
}
