"use client";

import { AnimatePresence, motion } from "framer-motion";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  Crown,
  MessageSquarePlus,
  Package,
  Rocket,
  ShieldCheck,
  Shuffle,
  Timer,
  User,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { Supervisor } from "@/lib/types";
import { usePolling } from "@/lib/use-polling";
import {
  Button,
  Card,
  ErrorBanner,
  Field,
  SectionHeading,
  cx,
  inputClass,
} from "@/components/ui";

function suggestOrderId(): string {
  return `ORD-${Math.random().toString(36).slice(2, 8).toUpperCase()}`;
}

const STEPS = [
  { id: 0, label: "Order", icon: Package },
  { id: 1, label: "Supervisor", icon: ShieldCheck },
  { id: 2, label: "Instructions", icon: MessageSquarePlus },
  { id: 3, label: "Launch", icon: Rocket },
];

const SUGGESTIONS = [
  "If shipment is delayed, escalate immediately and tell the customer.",
  "Never contact the customer without approval.",
  "Treat any payment problem as critical for this order.",
];

export default function NewRunPage() {
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [supervisors, setSupervisors] = useState<Supervisor[]>([]);
  const [supervisorId, setSupervisorId] = useState("");
  const [orderId, setOrderId] = useState("");
  const [customerTier, setCustomerTier] = useState("standard");
  const [orderValue, setOrderValue] = useState("249.00");
  const [notes, setNotes] = useState("");
  const [instruction, setInstruction] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  const loadSupervisors = useCallback(async () => {
    try {
      const items = await api.listSupervisors();
      setSupervisors(items);
      setSupervisorId((current) => current || items[0]?.id || "");
      setError(null);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not load supervisors");
    }
  }, []);

  usePolling(loadSupervisors, 15000);

  const selected = supervisors.find((item) => item.id === supervisorId);
  const canAdvance = step === 0 ? orderId.trim().length > 0 : step === 1 ? Boolean(supervisorId) : true;

  async function launch() {
    setStarting(true);
    setError(null);
    try {
      const run = await api.createRun({
        order_id: orderId.trim() || suggestOrderId(),
        supervisor_id: supervisorId,
        order_context: {
          customer_tier: customerTier,
          order_value: Number(orderValue) || 0,
          ...(notes.trim() ? { notes: notes.trim() } : {}),
        },
        initial_instructions: instruction.trim() ? [instruction.trim()] : [],
      });
      router.push(`/runs/${run.id}`);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not start the run");
      setStarting(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <SectionHeading
        eyebrow="New run"
        title="Start a supervised order"
        description="Starting a run creates exactly one durable Temporal workflow for this order."
      />

      {/* --------------------------------------------------------- stepper */}
      <ol className="flex items-center gap-1.5">
        {STEPS.map((item, index) => {
          const done = index < step;
          const active = index === step;
          return (
            <li key={item.id} className="flex flex-1 items-center gap-1.5">
              <button
                type="button"
                onClick={() => index <= step && setStep(index)}
                disabled={index > step}
                className={cx(
                  "flex w-full items-center gap-2 rounded-lg border px-2.5 py-2 text-left transition-all duration-200",
                  active
                    ? "border-brand-400 bg-brand-50 shadow-card"
                    : done
                      ? "border-emerald-200 bg-emerald-50/60 hover:bg-emerald-50"
                      : "border-ink-200 bg-white opacity-60",
                )}
              >
                <span
                  className={cx(
                    "grid h-6 w-6 shrink-0 place-items-center rounded-full text-[10px] font-bold",
                    active
                      ? "bg-brand-600 text-white"
                      : done
                        ? "bg-emerald-500 text-white"
                        : "bg-ink-200 text-ink-500",
                  )}
                >
                  {done ? <Check className="h-3 w-3" strokeWidth={3} /> : index + 1}
                </span>
                <span
                  className={cx(
                    "hidden text-xs font-medium sm:block",
                    active ? "text-brand-900" : done ? "text-emerald-800" : "text-ink-500",
                  )}
                >
                  {item.label}
                </span>
              </button>
            </li>
          );
        })}
      </ol>

      <ErrorBanner message={error} />

      {supervisors.length === 0 && !error && (
        <p className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          No supervisors are configured yet.{" "}
          <Link href="/supervisors" className="font-medium underline">
            Create one first
          </Link>
          .
        </p>
      )}

      <AnimatePresence mode="wait">
        <motion.div
          key={step}
          initial={{ opacity: 0, x: 12 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: -12 }}
          transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
        >
          {/* ------------------------------------------------- step 0 */}
          {step === 0 && (
            <Card title="The order" subtitle="What is being supervised" icon={Package}>
              <div className="space-y-4">
                <Field label="Order ID" htmlFor="order">
                  <div className="mt-1.5 flex gap-2">
                    <input
                      id="order"
                      value={orderId}
                      onChange={(event) => setOrderId(event.target.value)}
                      required
                      placeholder="ORD-4K2P9Z"
                      className={cx(inputClass, "mt-0 min-w-0 flex-1")}
                    />
                    <Button
                      variant="secondary"
                      icon={Shuffle}
                      onClick={() => setOrderId(suggestOrderId())}
                    >
                      Suggest
                    </Button>
                  </div>
                </Field>

                <div className="grid gap-3 sm:grid-cols-2">
                  <Field label="Customer tier" htmlFor="tier">
                    <select
                      id="tier"
                      value={customerTier}
                      onChange={(event) => setCustomerTier(event.target.value)}
                      className={inputClass}
                    >
                      <option value="standard">Standard</option>
                      <option value="vip">VIP</option>
                    </select>
                  </Field>
                  <Field label="Order value" htmlFor="value">
                    <input
                      id="value"
                      value={orderValue}
                      onChange={(event) => setOrderValue(event.target.value)}
                      inputMode="decimal"
                      className={inputClass}
                    />
                  </Field>
                </div>

                <Field label="Order notes" htmlFor="notes" hint="Optional context for the agent.">
                  <input
                    id="notes"
                    value={notes}
                    onChange={(event) => setNotes(event.target.value)}
                    placeholder="Gift order, deliver before Friday"
                    className={inputClass}
                  />
                </Field>
              </div>
            </Card>
          )}

          {/* ------------------------------------------------- step 1 */}
          {step === 1 && (
            <Card
              title="Choose a supervisor"
              subtitle="Its policy governs everything that follows"
              icon={ShieldCheck}
            >
              <div className="space-y-2">
                {supervisors.map((supervisor) => {
                  const chosen = supervisor.id === supervisorId;
                  return (
                    <button
                      key={supervisor.id}
                      type="button"
                      onClick={() => setSupervisorId(supervisor.id)}
                      className={cx(
                        "flex w-full items-start gap-3 rounded-lg border p-3 text-left transition-all duration-200",
                        chosen
                          ? "border-brand-400 bg-brand-50/70 ring-1 ring-brand-200"
                          : "border-ink-200 bg-white hover:border-brand-300 hover:bg-ink-50",
                      )}
                    >
                      <span
                        className={cx(
                          "mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-lg",
                          chosen ? "bg-brand-600 text-white" : "bg-ink-100 text-ink-500",
                        )}
                      >
                        {chosen ? (
                          <Check className="h-3.5 w-3.5" strokeWidth={3} />
                        ) : (
                          <Crown className="h-3.5 w-3.5" strokeWidth={2.2} />
                        )}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block text-sm font-semibold text-ink-900">
                          {supervisor.name}
                        </span>
                        <span className="mt-0.5 line-clamp-2 block text-[11px] leading-4 text-ink-500">
                          {supervisor.base_instruction}
                        </span>
                        <span className="mt-1.5 flex flex-wrap items-center gap-1.5 text-[10px] text-ink-500">
                          <span className="rounded bg-ink-100 px-1.5 py-0.5 font-semibold">
                            {supervisor.config.wake_aggressiveness ?? "BALANCED"}
                          </span>
                          <span className="inline-flex items-center gap-1">
                            <Timer className="h-2.5 w-2.5" strokeWidth={2.4} />
                            every {supervisor.config.default_wake_minutes ?? 60}m
                          </span>
                          {(supervisor.config.require_approval_for?.length ?? 0) > 0 && (
                            <span className="text-orange-600">approval gate</span>
                          )}
                        </span>
                      </span>
                    </button>
                  );
                })}
              </div>
            </Card>
          )}

          {/* ------------------------------------------------- step 2 */}
          {step === 2 && (
            <Card
              title="Run instructions"
              subtitle="Guidance that applies to this run alone"
              icon={MessageSquarePlus}
            >
              <div className="space-y-3">
                <Field
                  label="Initial instruction"
                  htmlFor="instruction"
                  hint="Optional. More can be added at any time while the run is live."
                >
                  <textarea
                    id="instruction"
                    value={instruction}
                    onChange={(event) => setInstruction(event.target.value)}
                    rows={3}
                    placeholder="If shipment is delayed, escalate immediately."
                    className={inputClass}
                  />
                </Field>
                <div>
                  <p className="text-[11px] font-medium text-ink-500">Common instructions</p>
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {SUGGESTIONS.map((suggestion) => (
                      <button
                        key={suggestion}
                        type="button"
                        onClick={() => setInstruction(suggestion)}
                        className="rounded-full border border-ink-200 bg-white px-2.5 py-1 text-[11px] text-ink-600 transition-colors hover:border-brand-300 hover:bg-brand-50 hover:text-brand-800"
                      >
                        {suggestion}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </Card>
          )}

          {/* ------------------------------------------------- step 3 */}
          {step === 3 && (
            <Card title="Review and launch" subtitle="One durable workflow, one order" icon={Rocket}>
              <dl className="divide-y divide-ink-100">
                {[
                  { label: "Order ID", value: orderId || "—", mono: true, icon: Package },
                  { label: "Supervisor", value: selected?.name ?? "—", icon: ShieldCheck },
                  { label: "Customer tier", value: customerTier, icon: User },
                  { label: "Order value", value: orderValue, icon: Package },
                  { label: "Instruction", value: instruction || "None", icon: MessageSquarePlus },
                ].map((row) => (
                  <div key={row.label} className="flex items-start justify-between gap-4 py-2.5">
                    <dt className="flex items-center gap-1.5 text-xs text-ink-500">
                      <row.icon className="h-3.5 w-3.5 text-ink-400" strokeWidth={2.2} />
                      {row.label}
                    </dt>
                    <dd
                      className={cx(
                        "max-w-[60%] text-right text-xs font-medium text-ink-900",
                        row.mono && "font-mono",
                      )}
                    >
                      {row.value}
                    </dd>
                  </div>
                ))}
              </dl>
              <p className="mt-3 rounded-lg bg-ink-50 px-3 py-2 text-[11px] leading-5 text-ink-500">
                The workflow will be created with the ID{" "}
                <code className="font-mono text-ink-700">
                  order-supervisor:{orderId || "<order-id>"}
                </code>
                . The agent wakes once immediately, then sleeps on a durable timer.
              </p>
            </Card>
          )}
        </motion.div>
      </AnimatePresence>

      {/* ------------------------------------------------------ navigation */}
      <div className="flex items-center justify-between gap-3">
        <Button
          variant="ghost"
          icon={ArrowLeft}
          onClick={() => setStep((current) => Math.max(0, current - 1))}
          disabled={step === 0 || starting}
        >
          Back
        </Button>
        {step < STEPS.length - 1 ? (
          <Button
            onClick={() => setStep((current) => current + 1)}
            disabled={!canAdvance || supervisors.length === 0}
          >
            Continue
            <ArrowRight className="h-3.5 w-3.5" strokeWidth={2.2} />
          </Button>
        ) : (
          <Button
            icon={Rocket}
            loading={starting}
            disabled={!supervisorId || !orderId.trim()}
            onClick={launch}
          >
            Launch supervisor
          </Button>
        )}
      </div>
    </div>
  );
}
