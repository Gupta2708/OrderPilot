"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { Supervisor } from "@/lib/types";
import { usePolling } from "@/lib/use-polling";
import { Button, Card, ErrorBanner } from "@/components/ui";

function suggestOrderId(): string {
  return `ORD-${Math.random().toString(36).slice(2, 8).toUpperCase()}`;
}

export default function NewRunPage() {
  const router = useRouter();
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

  async function submit(event: React.FormEvent) {
    event.preventDefault();
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
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Start a run</h1>
        <p className="mt-1 text-sm text-slate-600">
          Starting a run creates exactly one durable workflow for this order.
        </p>
      </div>

      <ErrorBanner message={error} />

      {supervisors.length === 0 && !error && (
        <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
          No supervisors are configured yet.{" "}
          <Link href="/supervisors" className="underline">
            Create one first
          </Link>
          .
        </p>
      )}

      <Card>
        <form onSubmit={submit} className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label htmlFor="order" className="block text-xs font-medium text-slate-700">
                Order ID
              </label>
              <div className="mt-1 flex gap-2">
                <input
                  id="order"
                  value={orderId}
                  onChange={(event) => setOrderId(event.target.value)}
                  required
                  placeholder="ORD-4K2P9Z"
                  className="min-w-0 flex-1 rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:border-teal-600 focus:outline-none"
                />
                <Button variant="secondary" onClick={() => setOrderId(suggestOrderId())}>
                  Suggest
                </Button>
              </div>
            </div>
            <div>
              <label htmlFor="supervisor" className="block text-xs font-medium text-slate-700">
                Supervisor
              </label>
              <select
                id="supervisor"
                value={supervisorId}
                onChange={(event) => setSupervisorId(event.target.value)}
                required
                className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm focus:border-teal-600 focus:outline-none"
              >
                {supervisors.map((supervisor) => (
                  <option key={supervisor.id} value={supervisor.id}>
                    {supervisor.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="tier" className="block text-xs font-medium text-slate-700">
                Customer tier
              </label>
              <select
                id="tier"
                value={customerTier}
                onChange={(event) => setCustomerTier(event.target.value)}
                className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm focus:border-teal-600 focus:outline-none"
              >
                <option value="standard">Standard</option>
                <option value="vip">VIP</option>
              </select>
            </div>
            <div>
              <label htmlFor="value" className="block text-xs font-medium text-slate-700">
                Order value
              </label>
              <input
                id="value"
                value={orderValue}
                onChange={(event) => setOrderValue(event.target.value)}
                inputMode="decimal"
                className="mt-1 w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:border-teal-600 focus:outline-none"
              />
            </div>
          </div>

          <div>
            <label htmlFor="notes" className="block text-xs font-medium text-slate-700">
              Order notes (optional)
            </label>
            <input
              id="notes"
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              placeholder="Gift order, deliver before Friday"
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:border-teal-600 focus:outline-none"
            />
          </div>

          <div>
            <label htmlFor="instruction" className="block text-xs font-medium text-slate-700">
              Initial run instruction (optional)
            </label>
            <input
              id="instruction"
              value={instruction}
              onChange={(event) => setInstruction(event.target.value)}
              placeholder="If shipment is delayed, escalate immediately."
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:border-teal-600 focus:outline-none"
            />
            <p className="mt-1 text-[11px] text-slate-500">
              Applies to this run only. More can be added at any time while it runs.
            </p>
          </div>

          <Button type="submit" disabled={starting || !supervisorId || !orderId.trim()}>
            {starting ? "Starting…" : "Start run"}
          </Button>
        </form>
      </Card>
    </div>
  );
}
