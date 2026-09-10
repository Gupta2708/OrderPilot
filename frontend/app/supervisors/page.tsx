"use client";

import { useCallback, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { titleCase } from "@/lib/format";
import type { Supervisor } from "@/lib/types";
import { usePolling } from "@/lib/use-polling";
import { Button, Card, EmptyState, ErrorBanner } from "@/components/ui";

const ALL_ACTIONS = [
  "message_fulfillment_team",
  "message_payments_team",
  "message_logistics_team",
  "message_customer",
  "create_internal_note",
];

const AGGRESSIVENESS = ["LOW", "BALANCED", "HIGH"];

export default function SupervisorsPage() {
  const [supervisors, setSupervisors] = useState<Supervisor[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const [name, setName] = useState("Standard Order Supervisor");
  const [instruction, setInstruction] = useState(
    "Supervise this order until it reaches a terminal state. Escalate risks early and keep the customer informed.",
  );
  const [actions, setActions] = useState<string[]>(ALL_ACTIONS);
  const [approvalActions, setApprovalActions] = useState<string[]>(["message_customer"]);
  const [aggressiveness, setAggressiveness] = useState("BALANCED");
  const [wakeMinutes, setWakeMinutes] = useState(60);
  const [maxAgeMinutes, setMaxAgeMinutes] = useState(7 * 24 * 60);

  const load = useCallback(async () => {
    try {
      setSupervisors(await api.listSupervisors());
      setError(null);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not load supervisors");
    }
  }, []);

  usePolling(load, 10000);

  function toggleAction(action: string) {
    setActions((current) =>
      current.includes(action) ? current.filter((item) => item !== action) : [...current, action],
    );
  }

  function toggleApproval(action: string) {
    setApprovalActions((current) =>
      current.includes(action) ? current.filter((item) => item !== action) : [...current, action],
    );
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await api.createSupervisor({
        name,
        base_instruction: instruction,
        allowed_actions: actions,
        wake_aggressiveness: aggressiveness,
        default_wake_minutes: wakeMinutes,
        max_age_minutes: maxAgeMinutes,
        require_approval_for: approvalActions,
      });
      await load();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not save supervisor");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Supervisors</h1>
        <p className="mt-1 text-sm text-slate-600">
          A supervisor is the reusable policy a run is started from: its instruction, the actions it
          may take, and how eagerly it wakes.
        </p>
      </div>

      <ErrorBanner message={error} />

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="New supervisor">
          <form onSubmit={submit} className="space-y-4">
            <div>
              <label htmlFor="name" className="block text-xs font-medium text-slate-700">
                Name
              </label>
              <input
                id="name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                required
                maxLength={200}
                className="mt-1 w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:border-teal-600 focus:outline-none"
              />
            </div>

            <div>
              <label htmlFor="instruction" className="block text-xs font-medium text-slate-700">
                Base instruction
              </label>
              <textarea
                id="instruction"
                value={instruction}
                onChange={(event) => setInstruction(event.target.value)}
                required
                rows={4}
                maxLength={4000}
                className="mt-1 w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:border-teal-600 focus:outline-none"
              />
            </div>

            <fieldset>
              <legend className="text-xs font-medium text-slate-700">Allowed actions</legend>
              <div className="mt-2 grid gap-1.5 sm:grid-cols-2">
                {ALL_ACTIONS.map((action) => (
                  <label key={action} className="flex items-center gap-2 text-sm text-slate-700">
                    <input
                      type="checkbox"
                      checked={actions.includes(action)}
                      onChange={() => toggleAction(action)}
                      className="h-4 w-4 rounded border-slate-300 text-teal-700"
                    />
                    {titleCase(action)}
                  </label>
                ))}
              </div>
            </fieldset>

            <fieldset>
              <legend className="text-xs font-medium text-slate-700">
                Require human approval before running
              </legend>
              <p className="mt-0.5 text-[11px] text-slate-500">
                These actions are proposed but held until someone approves them.
              </p>
              <div className="mt-2 grid gap-1.5 sm:grid-cols-2">
                {ALL_ACTIONS.filter((action) => actions.includes(action)).map((action) => (
                  <label key={action} className="flex items-center gap-2 text-sm text-slate-700">
                    <input
                      type="checkbox"
                      checked={approvalActions.includes(action)}
                      onChange={() => toggleApproval(action)}
                      className="h-4 w-4 rounded border-slate-300 text-teal-700"
                    />
                    {titleCase(action)}
                  </label>
                ))}
              </div>
            </fieldset>

            <div className="grid gap-3 sm:grid-cols-3">
              <div>
                <label htmlFor="aggr" className="block text-xs font-medium text-slate-700">
                  Wake sensitivity
                </label>
                <select
                  id="aggr"
                  value={aggressiveness}
                  onChange={(event) => setAggressiveness(event.target.value)}
                  className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm focus:border-teal-600 focus:outline-none"
                >
                  {AGGRESSIVENESS.map((level) => (
                    <option key={level} value={level}>
                      {level}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="wake" className="block text-xs font-medium text-slate-700">
                  Review every (min)
                </label>
                <input
                  id="wake"
                  type="number"
                  min={1}
                  max={10080}
                  value={wakeMinutes}
                  onChange={(event) => setWakeMinutes(Number(event.target.value))}
                  className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm focus:border-teal-600 focus:outline-none"
                />
              </div>
              <div>
                <label htmlFor="maxage" className="block text-xs font-medium text-slate-700">
                  Max age (min)
                </label>
                <input
                  id="maxage"
                  type="number"
                  min={1}
                  value={maxAgeMinutes}
                  onChange={(event) => setMaxAgeMinutes(Number(event.target.value))}
                  className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm focus:border-teal-600 focus:outline-none"
                />
              </div>
            </div>

            <Button type="submit" disabled={saving || actions.length === 0}>
              {saving ? "Saving…" : "Create supervisor"}
            </Button>
          </form>
        </Card>

        <Card title="Configured supervisors">
          {supervisors === null ? (
            <EmptyState>Loading…</EmptyState>
          ) : supervisors.length === 0 ? (
            <EmptyState>No supervisors yet. Create one to start a run.</EmptyState>
          ) : (
            <ul className="divide-y divide-slate-100">
              {supervisors.map((supervisor) => (
                <li key={supervisor.id} className="py-3 first:pt-0 last:pb-0">
                  <p className="text-sm font-medium text-slate-900">{supervisor.name}</p>
                  <p className="mt-1 line-clamp-2 text-xs text-slate-600">
                    {supervisor.base_instruction}
                  </p>
                  <p className="mt-1.5 text-[11px] text-slate-500">
                    {supervisor.allowed_actions.length} actions ·{" "}
                    {supervisor.config.wake_aggressiveness ?? "BALANCED"} · review every{" "}
                    {supervisor.config.default_wake_minutes ?? 60}m
                    {supervisor.config.require_approval_for?.length
                      ? ` · ${supervisor.config.require_approval_for.length} need approval`
                      : ""}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}
