"use client";

import { motion } from "framer-motion";
import type { LucideIcon } from "lucide-react";
import {
  AlertTriangle,
  Ban,
  BellRing,
  BrainCircuit,
  CheckCircle2,
  Copy,
  CreditCard,
  Flag,
  Gauge,
  History,
  Inbox,
  ListTree,
  MessageSquare,
  Moon,
  NotebookPen,
  Package,
  PauseCircle,
  PlayCircle,
  Rocket,
  ShieldCheck,
  ShieldX,
  Sparkles,
  Truck,
  XCircle,
} from "lucide-react";
import { formatTime, titleCase } from "@/lib/format";
import type { ActivityEntry, OrderState, RunAnalytics } from "@/lib/types";
import { Card, Chip, EmptyState, cx } from "@/components/ui";

/* -------------------------------------------------------- order lifecycle */

type StageTone = "done" | "active" | "risk" | "idle";

const STAGE_TONE: Record<StageTone, { ring: string; dot: string; text: string }> = {
  done: { ring: "ring-emerald-200 bg-emerald-50", dot: "bg-emerald-500", text: "text-emerald-800" },
  active: { ring: "ring-brand-200 bg-brand-50", dot: "bg-brand-500", text: "text-brand-800" },
  risk: { ring: "ring-orange-200 bg-orange-50", dot: "bg-orange-500", text: "text-orange-800" },
  idle: { ring: "ring-ink-200 bg-ink-50", dot: "bg-ink-300", text: "text-ink-500" },
};

const RISK_VALUES = new Set(["failed", "delayed", "requested", "cancelled"]);
const DONE_VALUES = new Set([
  "confirmed",
  "delivered",
  "completed",
  "shipped",
  "ready_to_pick",
  "created",
]);

function toneFor(value: string): StageTone {
  if (RISK_VALUES.has(value)) return "risk";
  if (DONE_VALUES.has(value)) return "done";
  if (value === "pending" || value === "not_started" || value === "not_created" || value === "none")
    return "idle";
  return "active";
}

/** The order's own progress, as a stepper rather than a list of key/values. */
export function OrderLifecycle({ state }: { state: OrderState }) {
  const stages: Array<{
    label: string;
    value: string;
    icon: LucideIcon;
    note?: string | null;
  }> = [
    {
      label: "Payment",
      value: state.payment?.status ?? "—",
      icon: CreditCard,
      note: state.payment?.reason,
    },
    { label: "Fulfillment", value: state.fulfillment?.status ?? "—", icon: Package },
    {
      label: "Shipment",
      value: state.shipment?.status ?? "—",
      icon: Truck,
      note: state.shipment?.delay_reason,
    },
    { label: "Delivery", value: state.delivery?.status ?? "—", icon: Flag },
    { label: "Refund", value: state.refund?.status ?? "—", icon: Ban, note: state.refund?.reason },
  ];

  return (
    <Card
      title="Order lifecycle"
      subtitle="Structured state, never inferred from prose"
      icon={Package}
    >
      <div className="grid gap-2.5 sm:grid-cols-3 lg:grid-cols-5">
        {stages.map((stage, index) => {
          const tone = STAGE_TONE[toneFor(stage.value)];
          return (
            <motion.div
              key={stage.label}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.05, duration: 0.3 }}
              className={cx(
                "rounded-lg p-2.5 ring-1 ring-inset transition-transform duration-200 hover:-translate-y-0.5",
                tone.ring,
              )}
            >
              <div className="flex items-center gap-1.5">
                <stage.icon className={cx("h-3.5 w-3.5", tone.text)} strokeWidth={2.2} />
                <p className="text-[10px] font-semibold uppercase tracking-wider text-ink-500">
                  {stage.label}
                </p>
              </div>
              <p className={cx("mt-1 flex items-center gap-1.5 text-sm font-semibold", tone.text)}>
                <span className={cx("h-1.5 w-1.5 rounded-full", tone.dot)} />
                {titleCase(stage.value)}
              </p>
              {stage.note && (
                <p className="mt-0.5 truncate text-[10px] text-ink-500" title={stage.note}>
                  {stage.note}
                </p>
              )}
            </motion.div>
          );
        })}
      </div>
      {state.customer?.last_message && (
        <div className="mt-3 flex gap-2 border-t border-ink-100 pt-3">
          <MessageSquare className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ink-400" strokeWidth={2.2} />
          <p className="text-xs leading-5 text-ink-600">
            <span className="font-medium text-ink-500">Last customer message: </span>
            &ldquo;{state.customer.last_message}&rdquo;
          </p>
        </div>
      )}
    </Card>
  );
}

/* --------------------------------------------------------------- timeline */

type TimelineStyle = { icon: LucideIcon; dot: string; ring: string; category: string };

const TIMELINE: Record<string, TimelineStyle> = {
  RUN_STARTED: { icon: Rocket, dot: "bg-brand-600", ring: "ring-brand-200", category: "Lifecycle" },
  EVENT_RECEIVED: { icon: Inbox, dot: "bg-sky-500", ring: "ring-sky-200", category: "Event" },
  EVENT_REJECTED: {
    icon: AlertTriangle,
    dot: "bg-rose-400",
    ring: "ring-rose-200",
    category: "Event",
  },
  EVENT_DUPLICATE_IGNORED: {
    icon: Copy,
    dot: "bg-ink-300",
    ring: "ring-ink-200",
    category: "Event",
  },
  WAKE_DECISION: { icon: BellRing, dot: "bg-amber-500", ring: "ring-amber-200", category: "Triage" },
  AGENT_DECISION: {
    icon: BrainCircuit,
    dot: "bg-violet-500",
    ring: "ring-violet-200",
    category: "AI",
  },
  ACTION_EXECUTED: {
    icon: CheckCircle2,
    dot: "bg-emerald-500",
    ring: "ring-emerald-200",
    category: "Action",
  },
  ACTION_FAILED: { icon: XCircle, dot: "bg-rose-500", ring: "ring-rose-200", category: "Action" },
  ACTION_REJECTED: { icon: ShieldX, dot: "bg-rose-400", ring: "ring-rose-200", category: "Action" },
  ACTION_PENDING_APPROVAL: {
    icon: ShieldCheck,
    dot: "bg-orange-500",
    ring: "ring-orange-200",
    category: "Approval",
  },
  ACTION_APPROVED: {
    icon: CheckCircle2,
    dot: "bg-emerald-500",
    ring: "ring-emerald-200",
    category: "Approval",
  },
  ACTION_DENIED: { icon: ShieldX, dot: "bg-rose-500", ring: "ring-rose-200", category: "Approval" },
  MEMORY_UPDATED: {
    icon: NotebookPen,
    dot: "bg-ink-300",
    ring: "ring-ink-200",
    category: "Memory",
  },
  SLEEP_SCHEDULED: { icon: Moon, dot: "bg-sky-400", ring: "ring-sky-200", category: "Sleep" },
  INSTRUCTION_ADDED: {
    icon: MessageSquare,
    dot: "bg-indigo-500",
    ring: "ring-indigo-200",
    category: "Operator",
  },
  RUN_PAUSED: { icon: PauseCircle, dot: "bg-ink-400", ring: "ring-ink-200", category: "Control" },
  RUN_RESUMED: { icon: PlayCircle, dot: "bg-ink-400", ring: "ring-ink-200", category: "Control" },
  RUN_TERMINATED: { icon: Ban, dot: "bg-rose-600", ring: "ring-rose-200", category: "Lifecycle" },
  RUN_COMPLETED: {
    icon: CheckCircle2,
    dot: "bg-emerald-600",
    ring: "ring-emerald-200",
    category: "Lifecycle",
  },
  FINAL_OUTPUT: { icon: Flag, dot: "bg-emerald-600", ring: "ring-emerald-200", category: "Lifecycle" },
  WAKE_GUIDANCE_UPDATED: {
    icon: Sparkles,
    dot: "bg-violet-400",
    ring: "ring-violet-200",
    category: "AI",
  },
  RUN_CONTINUED: {
    icon: History,
    dot: "bg-fuchsia-500",
    ring: "ring-fuchsia-200",
    category: "Lifecycle",
  },
};

const FALLBACK: TimelineStyle = {
  icon: ListTree,
  dot: "bg-ink-300",
  ring: "ring-ink-200",
  category: "Event",
};

function summarise(entry: ActivityEntry): string {
  const payload = entry.payload as Record<string, string | undefined>;
  return (
    payload.reason_summary ??
    payload.detail ??
    payload.reason ??
    payload.instruction ??
    payload.type ??
    payload.final_summary ??
    payload.terminal_reason ??
    payload.memory_update ??
    ""
  );
}

/** One event in the vertical timeline. */
export function TimelineEventCard({ entry, isLast }: { entry: ActivityEntry; isLast: boolean }) {
  const style = TIMELINE[entry.type] ?? FALLBACK;
  const Icon = style.icon;
  const summary = summarise(entry);
  return (
    <li className="relative flex gap-3 pb-3.5 last:pb-0">
      {!isLast && (
        <span className="absolute bottom-0 left-[13px] top-7 w-px bg-ink-200" aria-hidden />
      )}
      <span
        className={cx(
          "relative z-10 mt-0.5 grid h-[26px] w-[26px] shrink-0 place-items-center rounded-full bg-white ring-2 ring-inset",
          style.ring,
        )}
      >
        <Icon className="h-3.5 w-3.5 text-ink-600" strokeWidth={2.2} />
      </span>
      <div className="min-w-0 flex-1 rounded-lg px-2 py-1 transition-colors duration-150 hover:bg-ink-50">
        <div className="flex flex-wrap items-baseline justify-between gap-x-2">
          <p className="text-xs font-semibold text-ink-800">{titleCase(entry.type)}</p>
          <time className="tnum shrink-0 text-[10px] text-ink-400">
            {formatTime(entry.created_at)}
          </time>
        </div>
        <div className="mt-0.5 flex items-center gap-1.5">
          <span className={cx("h-1 w-1 rounded-full", style.dot)} />
          <span className="text-[10px] font-medium uppercase tracking-wide text-ink-400">
            {style.category}
          </span>
        </div>
        {summary && <p className="mt-1 break-words text-xs leading-5 text-ink-600">{summary}</p>}
      </div>
    </li>
  );
}

export function TimelineCard({ entries }: { entries: ActivityEntry[] }) {
  const ordered = [...entries].sort((a, b) => b.seq - a.seq);
  return (
    <Card
      title="Unified timeline"
      subtitle={`${entries.length} entries, newest first`}
      icon={ListTree}
      bodyClassName="px-3 py-3"
    >
      {ordered.length === 0 ? (
        <EmptyState icon={ListTree} title="Nothing has happened yet">
          Every wake, decision, and action will appear here as it happens.
        </EmptyState>
      ) : (
        <ol className="scroll-slim max-h-[30rem] overflow-y-auto pr-1">
          {ordered.map((entry, index) => (
            <TimelineEventCard
              key={entry.seq}
              entry={entry}
              isLast={index === ordered.length - 1}
            />
          ))}
        </ol>
      )}
    </Card>
  );
}

/* --------------------------------------------------------- action history */

export function ActionHistoryCard({ entries }: { entries: ActivityEntry[] }) {
  const actions = entries.filter(
    (entry) => entry.type === "ACTION_EXECUTED" || entry.type === "ACTION_FAILED",
  );
  return (
    <Card title="Action history" subtitle={`${actions.length} executed`} icon={History}>
      {actions.length === 0 ? (
        <EmptyState icon={History} title="No actions taken yet">
          Actions appear once the agent decides one is warranted.
        </EmptyState>
      ) : (
        <ul className="scroll-slim max-h-[30rem] space-y-2 overflow-y-auto pr-1">
          {actions.map((entry) => {
            const payload = entry.payload as { tool?: string; detail?: string; ok?: boolean };
            return (
              <li
                key={entry.seq}
                className={cx(
                  "rounded-lg border p-2.5 transition-colors duration-150",
                  payload.ok
                    ? "border-ink-200 bg-white hover:border-emerald-200 hover:bg-emerald-50/40"
                    : "border-rose-200 bg-rose-50/50",
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <p className="text-xs font-semibold text-ink-800">
                    {titleCase(payload.tool ?? "action")}
                  </p>
                  <Chip tone={payload.ok ? "success" : "danger"}>
                    {payload.ok ? "sent" : "failed"}
                  </Chip>
                </div>
                <p className="mt-1 break-words text-xs leading-5 text-ink-600">{payload.detail}</p>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}

/* -------------------------------------------------------------- analytics */

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ${seconds % 60}s`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m`;
}

function Meter({ value, tone }: { value: number; tone: string }) {
  return (
    <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-ink-100">
      <motion.div
        initial={{ width: 0 }}
        animate={{ width: `${Math.min(100, Math.max(0, value))}%` }}
        transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
        className={cx("h-full rounded-full", tone)}
      />
    </div>
  );
}

export function AnalyticsCard({ analytics }: { analytics: RunAnalytics | null }) {
  if (!analytics) {
    return (
      <Card title="Run analytics" subtitle="What this supervisor actually did" icon={Gauge}>
        <EmptyState icon={Gauge}>Analytics appear once the run has started.</EmptyState>
      </Card>
    );
  }
  const rows: Array<[string, number | string]> = [
    ["Events received", analytics.events_received],
    ["Agent wake-ups", analytics.agent_wakeups],
    ["Handled without waking", analytics.no_wake_events],
    ["Classifier calls", analytics.classifier_calls],
    ["Scheduled reviews", analytics.scheduled_reviews],
    ["Actions executed", analytics.actions_executed],
    ["Customer actions", analytics.customer_actions],
    ["Approvals granted", analytics.approvals_granted],
    ["Approvals rejected", analytics.approvals_denied],
    ["Continuations", analytics.continuations],
    ["Run duration", formatDuration(analytics.duration_seconds)],
  ];
  const wakePct = Math.round(analytics.wake_rate * 100);
  return (
    <Card title="Run analytics" subtitle="What this supervisor actually did" icon={Gauge}>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="rounded-lg bg-ink-50 p-3">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-ink-500">
            Wake rate
          </p>
          <p className="tnum mt-0.5 text-2xl font-semibold leading-none text-ink-900">{wakePct}%</p>
          <Meter value={wakePct} tone="bg-brand-500" />
          <p className="mt-1.5 text-[11px] text-ink-500">of events needed the agent</p>
        </div>
        <div className="rounded-lg bg-ink-50 p-3">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-ink-500">
            Actions / wake
          </p>
          <p className="tnum mt-0.5 text-2xl font-semibold leading-none text-ink-900">
            {analytics.actions_per_wake}
          </p>
          <Meter value={Math.min(100, analytics.actions_per_wake * 33)} tone="bg-violet-500" />
          <p className="mt-1.5 text-[11px] text-ink-500">work done per consultation</p>
        </div>
      </div>
      <dl className="mt-3 divide-y divide-ink-100 border-t border-ink-100">
        {rows.map(([label, value]) => (
          <div key={label} className="flex items-center justify-between gap-3 py-1.5">
            <dt className="text-xs text-ink-500">{label}</dt>
            <dd className="tnum text-xs font-semibold text-ink-800">{value}</dd>
          </div>
        ))}
      </dl>
    </Card>
  );
}
