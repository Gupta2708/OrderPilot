"use client";

import { formatTime, titleCase } from "@/lib/format";
import type {
  ActivityEntry,
  AgentDecision,
  FinalOutput,
  OrderState,
  WakeDecision,
} from "@/lib/types";
import { Card, EmptyState, SeverityBadge } from "@/components/ui";

const STATE_TONE: Record<string, string> = {
  confirmed: "text-emerald-700",
  delivered: "text-emerald-700",
  completed: "text-emerald-700",
  shipped: "text-emerald-700",
  created: "text-sky-700",
  ready_to_pick: "text-sky-700",
  failed: "text-rose-700",
  delayed: "text-orange-700",
  requested: "text-orange-700",
  cancelled: "text-rose-700",
};

export function OrderStateCard({ state }: { state: OrderState }) {
  const rows: [string, string][] = [
    ["Payment", state.payment?.status ?? "—"],
    ["Fulfillment", state.fulfillment?.status ?? "—"],
    ["Shipment", state.shipment?.status ?? "—"],
    ["Delivery", state.delivery?.status ?? "—"],
    ["Refund", state.refund?.status ?? "—"],
  ];
  return (
    <Card title="Order state" subtitle="Structured, not inferred from memory">
      <dl className="space-y-1.5">
        {rows.map(([label, value]) => (
          <div key={label} className="flex items-center justify-between gap-3 text-sm">
            <dt className="text-slate-500">{label}</dt>
            <dd className={`font-medium ${STATE_TONE[value] ?? "text-slate-800"}`}>
              {titleCase(value)}
            </dd>
          </div>
        ))}
      </dl>
      {state.customer?.last_message && (
        <p className="mt-3 border-t border-slate-100 pt-2 text-xs text-slate-600">
          <span className="font-medium text-slate-500">Last customer message: </span>
          &ldquo;{state.customer.last_message}&rdquo;
        </p>
      )}
    </Card>
  );
}

export function DecisionCard({ decision }: { decision: AgentDecision | null }) {
  return (
    <Card
      title="Latest decision"
      subtitle={decision ? `Triggered by ${titleCase(decision.trigger)}` : undefined}
      action={decision ? <SeverityBadge severity={decision.priority} /> : undefined}
    >
      {!decision ? (
        <EmptyState>No decision yet.</EmptyState>
      ) : (
        <div className="space-y-2.5">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-700">
              {decision.decision}
            </span>
            <span className="text-[11px] text-slate-500">
              via {decision.provider} · next review in {decision.sleep_minutes}m
            </span>
          </div>
          <p className="text-sm leading-6 text-slate-700">{decision.reason_summary}</p>
          {decision.actions.length > 0 && (
            <ul className="space-y-1">
              {decision.actions.map((action, index) => (
                <li key={`${action.tool}-${index}`} className="text-xs text-slate-600">
                  → <span className="font-medium">{titleCase(action.tool)}</span>
                </li>
              ))}
            </ul>
          )}
          {decision.completion_recommended && (
            <p className="rounded bg-amber-50 px-2 py-1 text-[11px] text-amber-800">
              The agent recommended completion. The workflow decides whether the run actually ends.
            </p>
          )}
        </div>
      )}
    </Card>
  );
}

export function WakeCard({ wake }: { wake: WakeDecision | null }) {
  return (
    <Card
      title="Wake decision"
      subtitle="Why the main agent was, or was not, woken"
      action={wake ? <SeverityBadge severity={wake.severity} /> : undefined}
    >
      {!wake ? (
        <EmptyState>No events evaluated yet.</EmptyState>
      ) : (
        <div className="space-y-2">
          <p className="text-sm">
            <span
              className={`font-semibold ${wake.wake_now ? "text-orange-700" : "text-slate-600"}`}
            >
              {wake.wake_now ? "Woke the agent" : "Handled without waking"}
            </span>
            {wake.event_type && (
              <span className="text-slate-500"> · {titleCase(wake.event_type)}</span>
            )}
          </p>
          <p className="text-sm leading-6 text-slate-700">{wake.reason}</p>
          <p className="text-[11px] text-slate-500">
            {wake.category} · rule: {wake.rule}
          </p>
        </div>
      )}
    </Card>
  );
}

export function MemoryCard({ memory }: { memory: string }) {
  const lines = memory.split("\n").filter(Boolean);
  return (
    <Card title="Compact memory" subtitle="Rolling summary, not full history">
      {lines.length === 0 ? (
        <EmptyState>Nothing recorded yet.</EmptyState>
      ) : (
        <ul className="space-y-1.5">
          {lines.map((line, index) => (
            <li key={index} className="text-sm leading-6 text-slate-700">
              {line}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

const TIMELINE_TONE: Record<string, string> = {
  AGENT_DECISION: "bg-teal-500",
  ACTION_EXECUTED: "bg-emerald-500",
  ACTION_FAILED: "bg-rose-500",
  ACTION_REJECTED: "bg-rose-400",
  EVENT_RECEIVED: "bg-sky-500",
  EVENT_REJECTED: "bg-rose-400",
  EVENT_DUPLICATE_IGNORED: "bg-slate-300",
  WAKE_DECISION: "bg-amber-500",
  SLEEP_SCHEDULED: "bg-slate-300",
  MEMORY_UPDATED: "bg-slate-300",
  INSTRUCTION_ADDED: "bg-indigo-500",
  RUN_PAUSED: "bg-slate-400",
  RUN_RESUMED: "bg-slate-400",
  RUN_TERMINATED: "bg-rose-600",
  RUN_COMPLETED: "bg-emerald-600",
  FINAL_OUTPUT: "bg-emerald-600",
  RUN_STARTED: "bg-teal-600",
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

export function TimelineCard({ entries }: { entries: ActivityEntry[] }) {
  const ordered = [...entries].sort((a, b) => b.seq - a.seq);
  return (
    <Card title="Unified timeline" subtitle={`${entries.length} entries, newest first`}>
      {ordered.length === 0 ? (
        <EmptyState>Nothing has happened yet.</EmptyState>
      ) : (
        <ol className="max-h-[28rem] space-y-2 overflow-y-auto pr-1">
          {ordered.map((entry) => (
            <li key={entry.seq} className="flex gap-2.5">
              <span
                className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${
                  TIMELINE_TONE[entry.type] ?? "bg-slate-300"
                }`}
                aria-hidden
              />
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline justify-between gap-2">
                  <p className="text-xs font-semibold text-slate-800">{titleCase(entry.type)}</p>
                  <time className="shrink-0 text-[11px] tabular-nums text-slate-400">
                    {formatTime(entry.created_at)}
                  </time>
                </div>
                {summarise(entry) && (
                  <p className="mt-0.5 break-words text-xs leading-5 text-slate-600">
                    {summarise(entry)}
                  </p>
                )}
              </div>
            </li>
          ))}
        </ol>
      )}
    </Card>
  );
}

export function ActionHistoryCard({ entries }: { entries: ActivityEntry[] }) {
  const actions = entries.filter(
    (entry) => entry.type === "ACTION_EXECUTED" || entry.type === "ACTION_FAILED",
  );
  return (
    <Card title="Action history" subtitle={`${actions.length} executed`}>
      {actions.length === 0 ? (
        <EmptyState>No actions taken yet.</EmptyState>
      ) : (
        <ul className="space-y-2">
          {actions.map((entry) => {
            const payload = entry.payload as { tool?: string; detail?: string; ok?: boolean };
            return (
              <li key={entry.seq} className="rounded-md border border-slate-100 bg-slate-50 p-2">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-xs font-semibold text-slate-800">
                    {titleCase(payload.tool ?? "action")}
                  </p>
                  <span
                    className={`text-[11px] font-medium ${
                      payload.ok ? "text-emerald-700" : "text-rose-700"
                    }`}
                  >
                    {payload.ok ? "ok" : "failed"}
                  </span>
                </div>
                <p className="mt-0.5 break-words text-xs leading-5 text-slate-600">
                  {payload.detail}
                </p>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}

export function FinalOutputCard({ output }: { output: FinalOutput }) {
  return (
    <Card
      title="Final output"
      subtitle={`Run ended: ${titleCase(output.terminal_reason)}`}
      className="border-emerald-200"
    >
      <div className="space-y-3">
        <p className="text-sm leading-6 text-slate-700">{output.final_summary}</p>

        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Key learnings
            </h3>
            <ul className="mt-1 list-disc space-y-1 pl-4 text-sm text-slate-700">
              {output.learnings.map((item, index) => (
                <li key={index}>{item}</li>
              ))}
            </ul>
          </div>
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Recommendations
            </h3>
            <ul className="mt-1 list-disc space-y-1 pl-4 text-sm text-slate-700">
              {output.recommendations.map((item, index) => (
                <li key={index}>{item}</li>
              ))}
            </ul>
          </div>
        </div>

        {output.important_actions.length > 0 && (
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Important actions
            </h3>
            <ul className="mt-1 space-y-1 text-sm text-slate-700">
              {output.important_actions.map((action, index) => (
                <li key={index}>{titleCase(String((action as { tool?: string }).tool ?? ""))}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </Card>
  );
}
