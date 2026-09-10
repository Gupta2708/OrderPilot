"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { countdown, durationSince, formatDateTime } from "@/lib/format";
import type { RunAnalytics, RunDetail, RunState } from "@/lib/types";
import { usePolling, useNow } from "@/lib/use-polling";
import { Button, Card, ErrorBanner, Stat, StatusBadge } from "@/components/ui";
import { EventSimulator } from "@/components/event-simulator";
import {
  ActionHistoryCard,
  AnalyticsCard,
  ApprovalsCard,
  DecisionCard,
  GuidanceCard,
  FinalOutputCard,
  MemoryCard,
  OrderStateCard,
  TimelineCard,
  WakeCard,
} from "@/components/run-cards";

const REFRESH_MS = 2000;

export default function RunControlRoom() {
  const params = useParams<{ runId: string }>();
  const runId = params.runId;

  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [state, setState] = useState<RunState | null>(null);
  const [analytics, setAnalytics] = useState<RunAnalytics | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [instruction, setInstruction] = useState("");
  const [busy, setBusy] = useState(false);
  const now = useNow();

  const load = useCallback(async () => {
    try {
      const [nextDetail, nextState, nextAnalytics] = await Promise.all([
        api.getRun(runId),
        api.getRunState(runId).catch(() => null),
        api.getRunAnalytics(runId).catch(() => null),
      ]);
      setDetail(nextDetail);
      if (nextState) setState(nextState);
      if (nextAnalytics) setAnalytics(nextAnalytics);
      setError(null);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not load this run");
    }
  }, [runId]);

  usePolling(load, REFRESH_MS);

  /** Every control shares the same optimistic-refresh and error handling. */
  const act = useCallback(
    async (label: string, operation: () => Promise<unknown>) => {
      setBusy(true);
      setError(null);
      try {
        await operation();
        setNotice(`${label} accepted`);
        await load();
      } catch (caught) {
        setError(caught instanceof ApiError ? caught.message : `${label} failed`);
      } finally {
        setBusy(false);
        setTimeout(() => setNotice(null), 2500);
      }
    },
    [load],
  );

  if (!detail) {
    return (
      <div className="space-y-4">
        <ErrorBanner message={error} />
        {!error && <p className="text-sm text-slate-500">Loading run…</p>}
      </div>
    );
  }

  const status = state?.status ?? detail.status;
  const terminal = Boolean(detail.completed_at);
  const stats = state?.stats ?? detail.stats;
  const orderState = state?.order_state ?? detail.order_state;
  const memory = state?.memory_summary ?? detail.memory_summary;
  const decision = state?.latest_decision ?? detail.latest_decision;
  const instructions = state?.run_instructions ?? detail.run_instructions;
  const nextWake = state?.next_wake_at ?? detail.next_wake_at;
  const lastWake = state?.last_wake_at ?? detail.last_wake_at;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Link href="/" className="text-xs text-slate-500 hover:underline">
            ← All runs
          </Link>
          <div className="mt-1 flex flex-wrap items-center gap-2.5">
            <h1 className="text-xl font-semibold">{detail.order_id}</h1>
            <StatusBadge status={status} />
            {state && (
              <span className="text-[11px] text-slate-400">
                state from {state.source}
              </span>
            )}
          </div>
          <p className="mt-1 text-xs text-slate-500">
            Workflow <code className="font-mono">{detail.temporal_workflow_id}</code> · started{" "}
            {formatDateTime(detail.created_at)}
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          <Button
            variant="secondary"
            disabled={busy || terminal || status === "PAUSED"}
            onClick={() => act("Pause", () => api.pause(runId))}
          >
            Pause
          </Button>
          <Button
            variant="secondary"
            disabled={busy || terminal || status !== "PAUSED"}
            onClick={() => act("Resume", () => api.resume(runId))}
          >
            Resume
          </Button>
          <Button
            variant="danger"
            disabled={busy || terminal}
            onClick={() => act("Terminate", () => api.terminate(runId, "Terminated from the UI"))}
          >
            Terminate
          </Button>
        </div>
      </div>

      <ErrorBanner message={error} />
      {notice && (
        <p className="rounded-lg border border-teal-200 bg-teal-50 px-3 py-2 text-sm text-teal-800">
          {notice}
        </p>
      )}

      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <Stat label="Next wake" value={terminal ? "—" : countdown(nextWake, now)} />
        <Stat label="Last wake" value={durationSince(lastWake, now)} />
        <Stat label="Events" value={stats.events_received ?? 0} />
        <Stat label="Wake-ups" value={stats.agent_wakeups ?? 0} />
        <Stat label="No-wake" value={stats.no_wake_events ?? 0} />
        <Stat label="Actions" value={stats.actions_executed ?? 0} />
      </dl>

      <ApprovalsCard
        approvals={state?.pending_approvals ?? []}
        busy={busy}
        onApprove={(approvalId) => act("Approval", () => api.approveAction(runId, approvalId))}
        onReject={(approvalId) =>
          act("Rejection", () => api.rejectAction(runId, approvalId, "Rejected from the UI"))
        }
      />

      {detail.final_output && <FinalOutputCard output={detail.final_output} />}

      <div className="grid gap-5 lg:grid-cols-3">
        <div className="space-y-5">
          <OrderStateCard state={orderState} />
          <MemoryCard memory={memory} />
          <GuidanceCard guidance={state?.wake_guidance ?? detail.wake_guidance} />
          <Card title="Run instructions" subtitle="Live guidance for this run only">
            {instructions.length === 0 ? (
              <p className="text-sm text-slate-500">None yet.</p>
            ) : (
              <ul className="space-y-1.5">
                {instructions.map((line, index) => (
                  <li key={index} className="text-sm leading-6 text-slate-700">
                    • {line}
                  </li>
                ))}
              </ul>
            )}
            <div className="mt-3 flex gap-2">
              <input
                value={instruction}
                onChange={(event) => setInstruction(event.target.value)}
                placeholder="If shipment is delayed, escalate immediately."
                disabled={terminal}
                className="min-w-0 flex-1 rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:border-teal-600 focus:outline-none disabled:bg-slate-50"
              />
              <Button
                disabled={busy || terminal || !instruction.trim()}
                onClick={() =>
                  act("Instruction", async () => {
                    await api.addInstruction(runId, instruction.trim());
                    setInstruction("");
                  })
                }
              >
                Add
              </Button>
            </div>
          </Card>
        </div>

        <div className="space-y-5">
          <DecisionCard decision={decision} />
          <WakeCard wake={state?.latest_wake_decision ?? null} />
          <EventSimulator
            disabled={busy || terminal}
            onSend={(type, payload) =>
              act(`Event ${type}`, () => api.sendEvent(runId, type, payload))
            }
          />
        </div>

        <div className="space-y-5">
          <TimelineCard entries={detail.timeline} />
          <AnalyticsCard analytics={analytics} />
          <ActionHistoryCard entries={detail.timeline} />
        </div>
      </div>
    </div>
  );
}
