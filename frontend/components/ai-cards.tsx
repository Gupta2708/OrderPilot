"use client";

import { AnimatePresence, motion } from "framer-motion";
import {
  Activity,
  ArrowRight,
  Bell,
  BellOff,
  BrainCircuit,
  CheckCircle2,
  Compass,
  Cpu,
  MessageSquare,
  Moon,
  ShieldCheck,
  Sparkles,
  Timer,
  XCircle,
} from "lucide-react";
import { formatTime, titleCase } from "@/lib/format";
import type { AgentDecision, FinalOutput, PendingApproval, WakeDecision } from "@/lib/types";
import { Button, Card, Chip, EmptyState, SeverityBadge, cx } from "@/components/ui";

/* ---------------------------------------------------------- AI decision */

const DECISION_TONE: Record<string, { ring: string; text: string; icon: typeof Cpu }> = {
  ACT: { ring: "bg-brand-50 ring-brand-200", text: "text-brand-800", icon: Sparkles },
  SLEEP: { ring: "bg-sky-50 ring-sky-200", text: "text-sky-800", icon: Moon },
  NO_ACTION: { ring: "bg-ink-100 ring-ink-200", text: "text-ink-600", icon: ShieldCheck },
};

/**
 * The single most important card in the product: what the AI decided, why, what
 * it will do, and when it will look again.
 */
export function AIDecisionCard({ decision }: { decision: AgentDecision | null }) {
  return (
    <Card
      title="AI decision"
      subtitle={decision ? `Triggered by ${titleCase(decision.trigger)}` : "The agent's last call"}
      icon={BrainCircuit}
      accent="brand"
      action={decision ? <SeverityBadge severity={decision.priority} /> : undefined}
    >
      {!decision ? (
        <EmptyState icon={BrainCircuit} title="No decision yet">
          The agent has not been woken for this run.
        </EmptyState>
      ) : (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            {(() => {
              const tone = DECISION_TONE[decision.decision] ?? DECISION_TONE.NO_ACTION;
              const Icon = tone.icon;
              return (
                <span
                  className={cx(
                    "inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-bold tracking-wide ring-1 ring-inset",
                    tone.ring,
                    tone.text,
                  )}
                >
                  <Icon className="h-3.5 w-3.5" strokeWidth={2.4} />
                  {decision.decision}
                </span>
              );
            })()}
            <Chip icon={Cpu}>{decision.provider}</Chip>
            <Chip icon={Timer}>next review in {decision.sleep_minutes}m</Chip>
          </div>

          <p className="text-sm leading-6 text-ink-700">{decision.reason_summary}</p>

          {decision.actions.length > 0 && (
            <div className="space-y-1.5 rounded-lg bg-ink-50 p-2.5">
              <p className="text-[10px] font-semibold uppercase tracking-wider text-ink-500">
                Actions chosen
              </p>
              {decision.actions.map((action, index) => (
                <div key={`${action.tool}-${index}`} className="flex items-start gap-1.5 text-xs">
                  <ArrowRight className="mt-0.5 h-3 w-3 shrink-0 text-brand-600" strokeWidth={2.4} />
                  <span className="font-medium text-ink-800">{titleCase(action.tool)}</span>
                </div>
              ))}
            </div>
          )}

          {decision.completion_recommended && (
            <p className="rounded-lg bg-amber-50 px-2.5 py-2 text-[11px] leading-5 text-amber-800 ring-1 ring-inset ring-amber-200">
              The agent recommended completion. The workflow decides whether the run actually ends.
            </p>
          )}
        </div>
      )}
    </Card>
  );
}

/* ------------------------------------------------------------ wake reason */

export function WakeReasonCard({ wake }: { wake: WakeDecision | null }) {
  const woke = wake?.wake_now === true;
  return (
    <Card
      title="Why it woke"
      subtitle="Or why it deliberately did not"
      icon={woke ? Bell : BellOff}
      action={wake ? <SeverityBadge severity={wake.severity} /> : undefined}
    >
      {!wake ? (
        <EmptyState icon={BellOff} title="No events evaluated yet">
          Inject an event to see the wake policy at work.
        </EmptyState>
      ) : (
        <div className="space-y-2.5">
          <div
            className={cx(
              "flex items-center gap-2 rounded-lg px-2.5 py-2 ring-1 ring-inset",
              woke ? "bg-orange-50 ring-orange-200" : "bg-ink-50 ring-ink-200",
            )}
          >
            {woke ? (
              <Bell className="h-4 w-4 shrink-0 text-orange-600" strokeWidth={2.4} />
            ) : (
              <BellOff className="h-4 w-4 shrink-0 text-ink-400" strokeWidth={2.2} />
            )}
            <div className="min-w-0">
              <p
                className={cx(
                  "text-xs font-semibold",
                  woke ? "text-orange-800" : "text-ink-600",
                )}
              >
                {woke ? "Woke the agent" : "Handled without waking"}
              </p>
              {wake.event_type && (
                <p className="truncate text-[11px] text-ink-500">{titleCase(wake.event_type)}</p>
              )}
            </div>
          </div>

          <p className="text-sm leading-6 text-ink-700">{wake.reason}</p>

          <div className="flex flex-wrap items-center gap-1.5 border-t border-ink-100 pt-2">
            <Chip>{wake.category}</Chip>
            <Chip tone={wake.rule.startsWith("ai_classifier") ? "brand" : "neutral"}>
              {wake.rule.startsWith("ai_classifier")
                ? "AI classifier"
                : wake.rule === "classifier_fallback_deterministic"
                  ? "Fallback rules"
                  : "Deterministic rules"}
            </Chip>
          </div>
        </div>
      )}
    </Card>
  );
}

/* ----------------------------------------------------------------- memory */

export function MemoryCard({ memory }: { memory: string }) {
  const lines = memory.split("\n").filter(Boolean);
  return (
    <Card
      title="Compact memory"
      subtitle={lines.length ? `${lines.length} notes kept` : "Rolling summary, not full history"}
      icon={Activity}
    >
      {lines.length === 0 ? (
        <EmptyState icon={Activity} title="Nothing recorded yet">
          Memory builds up as the agent makes decisions.
        </EmptyState>
      ) : (
        <ol className="space-y-2.5">
          {lines.map((line, index) => (
            <motion.li
              key={index}
              initial={{ opacity: 0, x: -4 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: index * 0.04 }}
              className="flex gap-2.5 text-sm leading-6 text-ink-700"
            >
              <span className="tnum mt-0.5 shrink-0 text-[10px] font-semibold text-ink-400">
                {String(index + 1).padStart(2, "0")}
              </span>
              <span className={line.startsWith("[") ? "italic text-ink-400" : ""}>{line}</span>
            </motion.li>
          ))}
        </ol>
      )}
    </Card>
  );
}

/* --------------------------------------------------------------- guidance */

export function GuidanceCard({ guidance }: { guidance: string[] }) {
  if (guidance.length === 0) return null;
  return (
    <Card
      title="Adaptive wake guidance"
      subtitle="Written by the agent; advises triage, never widens permissions"
      icon={Compass}
    >
      <ul className="space-y-2">
        {guidance.map((line, index) => (
          <li key={index} className="flex gap-2 text-sm leading-6 text-ink-700">
            <Sparkles className="mt-1 h-3 w-3 shrink-0 text-violet-500" strokeWidth={2.4} />
            {line}
          </li>
        ))}
      </ul>
    </Card>
  );
}

/* --------------------------------------------------------------- approval */

export function ApprovalCard({
  approvals,
  busy,
  terminal = false,
  onApprove,
  onReject,
}: {
  approvals: PendingApproval[];
  busy: boolean;
  /** A closed workflow accepts no signals, so offering to approve would only 409. */
  terminal?: boolean;
  onApprove: (id: string) => void;
  onReject: (id: string) => void;
}) {
  return (
    <AnimatePresence>
      {approvals.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: -8, height: 0 }}
          animate={{ opacity: 1, y: 0, height: "auto" }}
          exit={{ opacity: 0, y: -8, height: 0 }}
          transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
        >
          <div
            className={cx(
              "overflow-hidden rounded-xl border shadow-lift",
              terminal
                ? "border-ink-200 bg-white"
                : "border-orange-300 bg-gradient-to-br from-orange-50 to-white",
            )}
          >
            <header
              className={cx(
                "flex items-center gap-2.5 border-b px-4 py-3",
                terminal ? "border-ink-100" : "border-orange-200/70",
              )}
            >
              <span
                className={cx(
                  "grid h-7 w-7 place-items-center rounded-lg ring-1 ring-inset",
                  terminal
                    ? "bg-ink-100 text-ink-500 ring-ink-200"
                    : "bg-orange-100 text-orange-700 ring-orange-200",
                )}
              >
                <ShieldCheck className="h-4 w-4" strokeWidth={2.3} />
              </span>
              <div>
                <h2
                  className={cx(
                    "text-[13px] font-semibold",
                    terminal ? "text-ink-700" : "text-orange-900",
                  )}
                >
                  {terminal ? "Unresolved at completion" : "Waiting on you"}
                </h2>
                <p className={cx("text-[11px]", terminal ? "text-ink-500" : "text-orange-700/80")}>
                  {terminal
                    ? "The run ended before these were decided, so they never executed"
                    : "These actions will not run until a human decides"}
                </p>
              </div>
            </header>
            <div className="space-y-3 px-4 py-3.5">
              {approvals.map((approval) => (
                <div
                  key={approval.approval_id}
                  className={cx(
                    "rounded-lg border bg-white p-3 shadow-card",
                    terminal ? "border-ink-200" : "border-orange-200",
                  )}
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="inline-flex items-center gap-1.5 text-sm font-semibold text-ink-900">
                      <MessageSquare
                        className={cx("h-3.5 w-3.5", terminal ? "text-ink-400" : "text-orange-600")}
                        strokeWidth={2.3}
                      />
                      {titleCase(approval.tool)}
                    </span>
                    <span className="tnum text-[11px] text-ink-400">
                      requested {formatTime(approval.requested_at)}
                    </span>
                  </div>
                  {typeof approval.arguments.message === "string" && (
                    <blockquote className="mt-2 border-l-2 border-orange-300 bg-orange-50/60 py-1.5 pl-3 pr-2 text-sm leading-6 text-ink-700">
                      {approval.arguments.message}
                    </blockquote>
                  )}
                  {terminal ? (
                    <p className="mt-2.5 inline-flex items-center gap-1.5 rounded-md bg-ink-50 px-2 py-1 text-[11px] text-ink-500">
                      <XCircle className="h-3 w-3" strokeWidth={2.2} />
                      Never sent — the workflow closed before this was decided
                    </p>
                  ) : (
                    <div className="mt-3 flex flex-wrap gap-2">
                      <Button
                        variant="success"
                        size="sm"
                        icon={CheckCircle2}
                        disabled={busy}
                        onClick={() => onApprove(approval.approval_id)}
                      >
                        Approve &amp; send
                      </Button>
                      <Button
                        variant="secondary"
                        size="sm"
                        icon={XCircle}
                        disabled={busy}
                        onClick={() => onReject(approval.approval_id)}
                      >
                        Reject
                      </Button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

/* ----------------------------------------------------------- final output */

export function FinalOutputCard({ output }: { output: FinalOutput }) {
  return (
    <div className="overflow-hidden rounded-xl border border-emerald-200 bg-gradient-to-br from-emerald-50/80 to-white shadow-card">
      <header className="flex items-center gap-2.5 border-b border-emerald-200/70 px-4 py-3">
        <span className="grid h-7 w-7 place-items-center rounded-lg bg-emerald-100 text-emerald-700 ring-1 ring-inset ring-emerald-200">
          <CheckCircle2 className="h-4 w-4" strokeWidth={2.3} />
        </span>
        <div>
          <h2 className="text-[13px] font-semibold text-emerald-900">Final output</h2>
          <p className="text-[11px] text-emerald-700/80">
            Run ended: {titleCase(output.terminal_reason)}
          </p>
        </div>
      </header>
      <div className="space-y-4 px-4 py-3.5">
        <p className="text-sm leading-6 text-ink-700">{output.final_summary}</p>
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wider text-ink-500">
              Key learnings
            </p>
            <ul className="mt-1.5 space-y-1.5">
              {output.learnings.map((item, index) => (
                <li key={index} className="flex gap-2 text-sm leading-6 text-ink-700">
                  <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-emerald-500" />
                  {item}
                </li>
              ))}
            </ul>
          </div>
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wider text-ink-500">
              Recommendations
            </p>
            <ul className="mt-1.5 space-y-1.5">
              {output.recommendations.map((item, index) => (
                <li key={index} className="flex gap-2 text-sm leading-6 text-ink-700">
                  <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-brand-500" />
                  {item}
                </li>
              ))}
            </ul>
          </div>
        </div>
        {output.important_actions.length > 0 && (
          <div className="border-t border-emerald-200/60 pt-3">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-ink-500">
              Important actions
            </p>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {output.important_actions.map((action, index) => (
                <Chip key={index} tone="success">
                  {titleCase(String((action as { tool?: string }).tool ?? ""))}
                </Chip>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
