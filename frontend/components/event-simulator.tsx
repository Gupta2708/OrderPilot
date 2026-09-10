"use client";

import { useState } from "react";
import { titleCase } from "@/lib/format";
import { EVENT_TYPES, SCENARIOS } from "@/lib/scenarios";
import { Button, Card } from "@/components/ui";

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
    <Card title="Event simulator" subtitle="Drive the order forward one event at a time">
      <div className="space-y-4">
        <div>
          <label htmlFor="scenario" className="block text-xs font-medium text-slate-700">
            Scenario preset
          </label>
          <select
            id="scenario"
            value={scenarioId}
            onChange={(event) => {
              setScenarioId(event.target.value);
              setStepIndex(0);
            }}
            className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm focus:border-teal-600 focus:outline-none"
          >
            {SCENARIOS.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
          <p className="mt-1 text-[11px] text-slate-500">{scenario.description}</p>
        </div>

        <ol className="space-y-1">
          {scenario.steps.map((step, index) => (
            <li
              key={`${step.type}-${index}`}
              className={`flex items-center gap-2 rounded px-2 py-1 text-xs ${
                index < stepIndex
                  ? "text-slate-400 line-through"
                  : index === stepIndex
                    ? "bg-teal-50 font-medium text-teal-800"
                    : "text-slate-600"
              }`}
            >
              <span className="tabular-nums text-slate-400">{index + 1}.</span>
              {step.label}
            </li>
          ))}
        </ol>

        <div className="flex flex-wrap gap-2">
          <Button onClick={runNextStep} disabled={disabled || sending || !nextStep}>
            {nextStep ? `Run next: ${nextStep.label}` : "Scenario complete"}
          </Button>
          <Button variant="secondary" onClick={() => setStepIndex(0)} disabled={sending}>
            Reset steps
          </Button>
        </div>

        <div className="border-t border-slate-100 pt-3">
          <label htmlFor="manual" className="block text-xs font-medium text-slate-700">
            Or inject any event
          </label>
          <div className="mt-1 flex flex-wrap gap-2">
            <select
              id="manual"
              value={manualType}
              onChange={(event) => setManualType(event.target.value)}
              className="min-w-[12rem] flex-1 rounded-md border border-slate-300 px-2 py-1.5 text-sm focus:border-teal-600 focus:outline-none"
            >
              {EVENT_TYPES.map((type) => (
                <option key={type} value={type}>
                  {titleCase(type)}
                  {type === "warehouse_fire" ? " (unknown type)" : ""}
                </option>
              ))}
            </select>
            <Button variant="secondary" onClick={sendManual} disabled={disabled || sending}>
              Inject
            </Button>
          </div>
          {manualType === "customer_message_received" && (
            <input
              value={message}
              onChange={(event) => setMessage(event.target.value)}
              placeholder="Where is my order? I need it tomorrow."
              className="mt-2 w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:border-teal-600 focus:outline-none"
            />
          )}
        </div>
      </div>
    </Card>
  );
}
