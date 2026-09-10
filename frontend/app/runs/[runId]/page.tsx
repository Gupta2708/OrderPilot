"use client";

import { AnimatePresence, motion } from "framer-motion";
import {
  ArrowLeft,
  Ban,
  Bell,
  Gauge,
  History,
  ListTree,
  MessageSquarePlus,
  Pause,
  Play,
  Radio,
  Timer,
  Zap,
} from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { countdown, durationSince, formatDateTime } from "@/lib/format";
import type { RunAnalytics, RunDetail, RunState } from "@/lib/types";
import { useNow, usePolling } from "@/lib/use-polling";
import {
  AIDecisionCard,
  ApprovalCard,
  FinalOutputCard,
  GuidanceCard,
  MemoryCard,
  WakeReasonCard,
} from "@/components/ai-cards";
import { EventSimulator } from "@/components/event-simulator";
import {
  ActionHistoryCard,
  AnalyticsCard,
  OrderLifecycle,
  TimelineCard,
} from "@/components/run-cards";
import {
  AnimatedCard,
  Button,
  Card,
  Chip,
  ErrorBanner,
  Skeleton,
  StatusBadge,
  Tabs,
  cx,
  inputClass,
} from "@/components/ui";

const REFRESH_MS = 2000;

type DetailTab = "timeline" | "actions" | "analytics";

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
  const [tab, setTab] = useState<DetailTab>("timeline");
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
        setTimeout(() => setNotice(null), 2600);
      }
    },
    [load],
  );

  /* ------------------------------------------------------- loading state */
  if (!detail) {
    return (
      <div className="space-y-5">
        <ErrorBanner message={error} onRetry={() => void load()} />
        {!error && (
          <>
            <Skeleton className="h-28 w-full rounded-2xl" />
            <div className="grid gap-4 lg:grid-cols-2">
              <Skeleton className="h-52 w-full rounded-xl" />
              <Skeleton className="h-52 w-full rounded-xl" />
            </div>
            <Skeleton className="h-32 w-full rounded-xl" />
          </>
        )}
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
  const guidance = state?.wake_guidance ?? detail.wake_guidance;
  const nextWake = state?.next_wake_at ?? detail.next_wake_at;
  const lastWake = state?.last_wake_at ?? detail.last_wake_at;
  const liveSource = state?.source === "workflow";

  const submitInstruction = () =>
    act("Instruction", async () => {
      await api.addInstruction(runId, instruction.trim());
      setInstruction("");
    });

  return (
    <div className="space-y-5">
      {/* ------------------------------------------------------------ hero */}
      <motion.section
        initial={{ opacity: 0, y: -6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
        className="overflow-hidden rounded-2xl border border-ink-200 bg-white shadow-card"
      >
        <div className="hero-grid px-5 py-4 sm:px-6">
          <Link
            href="/"
            className="inline-flex items-center gap-1 text-[11px] text-ink-500 transition-colors hover:text-ink-800"
          >
            <ArrowLeft className="h-3 w-3" strokeWidth={2.4} />
            All runs
          </Link>

          <div className="mt-2 flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2.5">
                <h1 className="font-mono text-xl font-semibold tracking-tight text-ink-900 sm:text-2xl">
                  {detail.order_id}
                </h1>
                <StatusBadge status={status} pulse />
                {/* The honest Temporal signal: did the workflow itself answer? */}
                <Chip tone={liveSource ? "success" : "neutral"} icon={Radio}>
                  {liveSource ? "live from workflow" : "from database"}
                </Chip>
              </div>
              <p className="mt-1.5 text-[11px] text-ink-500">
                Workflow{" "}
                <code className="font-mono text-ink-600">{detail.temporal_workflow_id}</code>
                {" · started "}
                {formatDateTime(detail.created_at)}
              </p>
            </div>

            <div className="flex flex-wrap gap-2">
              <Button
                variant="secondary"
                size="sm"
                icon={Pause}
                disabled={busy || terminal || status === "PAUSED"}
                onClick={() => act("Pause", () => api.pause(runId))}
              >
                Pause
              </Button>
              <Button
                variant="secondary"
                size="sm"
                icon={Play}
                disabled={busy || terminal || status !== "PAUSED"}
                onClick={() => act("Resume", () => api.resume(runId))}
              >
                Resume
              </Button>
              <Button
                variant="danger"
                size="sm"
                icon={Ban}
                disabled={busy || terminal}
                onClick={() =>
                  act("Terminate", () => api.terminate(runId, "Terminated from the UI"))
                }
              >
                Terminate
              </Button>
            </div>
          </div>

          {/* Vital signs: the numbers an operator actually watches. */}
          <div className="mt-4 grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-6">
            {[
              {
                label: "Next wake",
                value: terminal ? "—" : countdown(nextWake, now),
                icon: Timer,
                highlight: !terminal,
              },
              { label: "Last wake", value: durationSince(lastWake, now), icon: History },
              { label: "Events", value: stats.events_received ?? 0, icon: ListTree },
              { label: "Wake-ups", value: stats.agent_wakeups ?? 0, icon: Bell },
              { label: "No-wake", value: stats.no_wake_events ?? 0, icon: Gauge },
              { label: "Actions", value: stats.actions_executed ?? 0, icon: Zap },
            ].map((item) => (
              <div
                key={item.label}
                className={cx(
                  "rounded-lg border px-3 py-2 transition-colors duration-200",
                  item.highlight
                    ? "border-brand-200 bg-brand-50/60"
                    : "border-ink-200 bg-white/70 hover:bg-white",
                )}
              >
                <div className="flex items-center gap-1">
                  <item.icon className="h-3 w-3 text-ink-400" strokeWidth={2.2} />
                  <p className="text-[9px] font-semibold uppercase tracking-wider text-ink-500">
                    {item.label}
                  </p>
                </div>
                <p
                  className={cx(
                    "tnum mt-0.5 text-base font-semibold leading-tight",
                    item.highlight ? "text-brand-800" : "text-ink-900",
                  )}
                >
                  {item.value}
                </p>
              </div>
            ))}
          </div>
        </div>
      </motion.section>

      <ErrorBanner message={error} onRetry={() => void load()} />

      <AnimatePresence>
        {notice && (
          <motion.p
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            className="rounded-xl border border-brand-200 bg-brand-50 px-4 py-2.5 text-sm text-brand-800"
          >
            {notice}
          </motion.p>
        )}
      </AnimatePresence>

      {/* -------------------------------------------------------- approval */}
      <ApprovalCard
        approvals={state?.pending_approvals ?? []}
        busy={busy}
        terminal={terminal}
        onApprove={(id) => act("Approval", () => api.approveAction(runId, id))}
        onReject={(id) =>
          act("Rejection", () => api.rejectAction(runId, id, "Rejected from the UI"))
        }
      />

      {/* ---------------------------------------------------- final output */}
      {detail.final_output && (
        <AnimatedCard delay={0.04}>
          <FinalOutputCard output={detail.final_output} />
        </AnimatedCard>
      )}

      {/* --------------------------------------------- decision + why woke */}
      <div className="grid gap-4 lg:grid-cols-2">
        <AnimatedCard delay={0.06}>
          <AIDecisionCard decision={decision} />
        </AnimatedCard>
        <AnimatedCard delay={0.1}>
          <WakeReasonCard wake={state?.latest_wake_decision ?? null} />
        </AnimatedCard>
      </div>

      {/* ------------------------------------------------- order lifecycle */}
      <AnimatedCard delay={0.14}>
        <OrderLifecycle state={orderState} />
      </AnimatedCard>

      {/* ------------------------------------------- memory + instructions */}
      <div className="grid gap-4 lg:grid-cols-3">
        <AnimatedCard delay={0.18}>
          <MemoryCard memory={memory} />
        </AnimatedCard>

        <AnimatedCard delay={0.2}>
          <Card
            title="Run instructions"
            subtitle="Live guidance for this run only"
            icon={MessageSquarePlus}
          >
            {instructions.length === 0 ? (
              <p className="text-sm text-ink-400">None yet.</p>
            ) : (
              <ul className="space-y-2">
                {instructions.map((line, index) => (
                  <li key={index} className="flex gap-2 text-sm leading-6 text-ink-700">
                    <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-indigo-400" />
                    {line}
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
                onKeyDown={(event) => {
                  if (event.key === "Enter" && instruction.trim() && !busy && !terminal) {
                    void submitInstruction();
                  }
                }}
                className={cx(inputClass, "mt-0 min-w-0 flex-1")}
              />
              <Button
                size="sm"
                disabled={busy || terminal || !instruction.trim()}
                onClick={submitInstruction}
              >
                Add
              </Button>
            </div>
          </Card>
        </AnimatedCard>

        <AnimatedCard delay={0.22}>
          {guidance.length > 0 ? (
            <GuidanceCard guidance={guidance} />
          ) : (
            <Card
              title="Adaptive wake guidance"
              subtitle="Set by the agent, when it has an opinion"
            >
              <p className="py-2 text-sm text-ink-400">
                The agent has not written any standing guidance for this run.
              </p>
            </Card>
          )}
        </AnimatedCard>
      </div>

      {/* ---------------------------------- timeline / actions / analytics */}
      <AnimatedCard delay={0.26}>
        <div className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-sm font-semibold tracking-tight text-ink-900">Run record</h2>
            <Tabs
              active={tab}
              onChange={setTab}
              tabs={[
                { id: "timeline", label: "Timeline", icon: ListTree, count: detail.timeline.length },
                { id: "actions", label: "Actions", icon: Zap, count: stats.actions_executed ?? 0 },
                { id: "analytics", label: "Analytics", icon: Gauge },
              ]}
            />
          </div>
          <AnimatePresence mode="wait">
            <motion.div
              key={tab}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.2 }}
            >
              {tab === "timeline" && <TimelineCard entries={detail.timeline} />}
              {tab === "actions" && <ActionHistoryCard entries={detail.timeline} />}
              {tab === "analytics" && <AnalyticsCard analytics={analytics} />}
            </motion.div>
          </AnimatePresence>
        </div>
      </AnimatedCard>

      {/* ------------------------------------------------------- simulator */}
      <AnimatedCard delay={0.3}>
        <EventSimulator
          disabled={busy || terminal}
          onSend={(type, payload) => act(`Event ${type}`, () => api.sendEvent(runId, type, payload))}
        />
      </AnimatedCard>
    </div>
  );
}
