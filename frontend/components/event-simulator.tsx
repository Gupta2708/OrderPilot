"use client";

import { motion } from "framer-motion";
import { Check, CircleDot, FlaskConical, Play, RotateCcw, Send } from "lucide-react";
import { useState } from "react";
import { titleCase } from "@/lib/format";
import { EVENT_TYPES, SCENARIOS } from "@/lib/scenarios";
import { Button, Card, Field, inputClass, cx } from "@/components/ui";

interface Props {
  disabled: boolean;
  onSend: (type: string, payload: Record<string, unknown>) => Promise<void>;
}

export function EventSimulator({ disabled, onSend }: Props) {
  const [scenarioId, setScenarioId] = useState(SCENARIOS[0].id);
  const [stepIndex, setStepIndex] = useState(0);
  const [sending, setSending] = useState(false);
  const [manualType, setManualType] = useState("payment_confirmed");
  const [message, setMessage] = useState("");

  const scenario = SCENARIOS.find((item) => item.id === scenarioId) ?? SCENARIOS[0];
  const nextStep = scenario.steps[stepIndex];
  const progress = Math.round((stepIndex / scenario.steps.length) * 100);

  async function runNextStep() {
    if (!nextStep) return;
    setSending(true);
    try {
      await onSend(nextStep.type, nextStep.payload ?? {});
      setStepIndex((index) => index + 1);
    } finally {
      setSending(false);
    }
  }

  async function sendManual() {
    setSending(true);
    try {
      const payload: Record<string, unknown> = {};
      if (manualType === "customer_message_received" && message.trim()) {
        payload.message = message.trim();
      }
      if (manualType === "shipment_delayed") payload.reason = "manual injection";
      if (manualType === "payment_failed") payload.reason = "card_declined";
      await onSend(manualType, payload);
      setMessage("");
    } finally {
      setSending(false);
    }
  }

  return (
    <Card
      title="Event simulator"
      subtitle="Drive the order forward one event at a time"
      icon={FlaskConical}
    >
      <div className="grid gap-5 lg:grid-cols-2">
        {/* ------------------------------------------------------ scenario */}
        <div className="space-y-3">
          <Field label="Scenario preset" htmlFor="scenario" hint={scenario.description}>
            <select
              id="scenario"
              value={scenarioId}
              onChange={(event) => {
                setScenarioId(event.target.value);
                setStepIndex(0);
              }}
              className={inputClass}
            >
              {SCENARIOS.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </Field>

          <div>
            <div className="mb-1.5 flex items-center justify-between text-[10px] font-semibold uppercase tracking-wider text-ink-500">
              <span>Progress</span>
              <span className="tnum">
                {stepIndex}/{scenario.steps.length}
              </span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-ink-100">
              <motion.div
                className="h-full rounded-full bg-brand-500"
                animate={{ width: `${progress}%` }}
                transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
              />
            </div>
          </div>

          <ol className="space-y-1">
            {scenario.steps.map((step, index) => {
              const done = index < stepIndex;
              const current = index === stepIndex;
              return (
                <li
                  key={`${step.type}-${index}`}
                  className={cx(
                    "flex items-center gap-2 rounded-md px-2 py-1.5 text-xs transition-colors duration-150",
                    done
                      ? "text-ink-400"
                      : current
                        ? "bg-brand-50 font-medium text-brand-900 ring-1 ring-inset ring-brand-200"
                        : "text-ink-600",
                  )}
                >
                  {done ? (
                    <Check className="h-3.5 w-3.5 shrink-0 text-emerald-500" strokeWidth={2.6} />
                  ) : (
                    <CircleDot
                      className={cx(
                        "h-3.5 w-3.5 shrink-0",
                        current ? "text-brand-600" : "text-ink-300",
                      )}
                      strokeWidth={2.2}
                    />
                  )}
                  <span className={done ? "line-through" : ""}>{step.label}</span>
                </li>
              );
            })}
          </ol>

          <div className="flex flex-wrap gap-2">
            <Button
              onClick={runNextStep}
              disabled={disabled || !nextStep}
              loading={sending && Boolean(nextStep)}
              icon={Play}
              size="sm"
            >
              {nextStep ? `Run: ${nextStep.label}` : "Scenario complete"}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              icon={RotateCcw}
              onClick={() => setStepIndex(0)}
              disabled={sending || stepIndex === 0}
            >
              Reset
            </Button>
          </div>
        </div>

        {/* -------------------------------------------------------- manual */}
        <div className="space-y-3 border-t border-ink-100 pt-4 lg:border-l lg:border-t-0 lg:pl-5 lg:pt-0">
          <Field
            label="Inject any event"
            htmlFor="manual"
            hint="Includes an unrecognised type, so unknown-event escalation can be shown."
          >
            <select
              id="manual"
              value={manualType}
              onChange={(event) => setManualType(event.target.value)}
              className={inputClass}
            >
              {EVENT_TYPES.map((type) => (
                <option key={type} value={type}>
                  {titleCase(type)}
                  {type === "warehouse_fire" ? "  (unknown type)" : ""}
                </option>
              ))}
            </select>
          </Field>

          {manualType === "customer_message_received" && (
            <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }}>
              <Field label="Customer message" htmlFor="customer-message">
                <textarea
                  id="customer-message"
                  value={message}
                  onChange={(event) => setMessage(event.target.value)}
                  rows={3}
                  placeholder="Where is my order? I need it tomorrow or I am cancelling."
                  className={inputClass}
                />
              </Field>
            </motion.div>
          )}

          <Button
            variant="secondary"
            size="sm"
            icon={Send}
            onClick={sendManual}
            disabled={disabled}
            loading={sending && !nextStep}
          >
            Inject event
          </Button>
        </div>
      </div>
    </Card>
  );
}
