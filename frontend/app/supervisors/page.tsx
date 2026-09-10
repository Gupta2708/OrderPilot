"use client";

import { motion } from "framer-motion";
import type { LucideIcon } from "lucide-react";
import {
  BadgeCheck,
  Check,
  Crown,
  Gauge,
  PiggyBank,
  Repeat,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Timer,
  Wand2,
} from "lucide-react";
import { useCallback, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { titleCase } from "@/lib/format";
import type { Supervisor, SupervisorTemplate } from "@/lib/types";
import { usePolling } from "@/lib/use-polling";
import {
  AnimatedCard,
  Button,
  Card,
  EmptyState,
  ErrorBanner,
  Field,
  SectionHeading,
  Skeleton,
  cx,
  inputClass,
} from "@/components/ui";

const ALL_ACTIONS = [
  "message_fulfillment_team",
  "message_payments_team",
  "message_logistics_team",
  "message_customer",
  "create_internal_note",
];

const AGGRESSIVENESS = ["LOW", "BALANCED", "HIGH"] as const;

const TEMPLATE_ART: Record<string, { icon: LucideIcon; ring: string; tint: string }> = {
  standard: { icon: BadgeCheck, ring: "ring-sky-200", tint: "from-sky-50" },
  vip: { icon: Crown, ring: "ring-amber-200", tint: "from-amber-50" },
  cost_conscious: { icon: PiggyBank, ring: "ring-emerald-200", tint: "from-emerald-50" },
};

export default function SupervisorsPage() {
  const [supervisors, setSupervisors] = useState<Supervisor[] | null>(null);
  const [templates, setTemplates] = useState<SupervisorTemplate[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [appliedTemplate, setAppliedTemplate] = useState<string | null>(null);

  const [name, setName] = useState("Standard Order Supervisor");
  const [instruction, setInstruction] = useState(
    "Supervise this order until it reaches a terminal state. Escalate risks early and keep the customer informed.",
  );
  const [actions, setActions] = useState<string[]>(ALL_ACTIONS);
  const [approvalActions, setApprovalActions] = useState<string[]>(["message_customer"]);
  const [aggressiveness, setAggressiveness] = useState<string>("BALANCED");
  const [wakeMinutes, setWakeMinutes] = useState(60);
  const [maxAgeMinutes, setMaxAgeMinutes] = useState(7 * 24 * 60);
  const [continueAfter, setContinueAfter] = useState(0);

  const load = useCallback(async () => {
    try {
      const [items, presets] = await Promise.all([
        api.listSupervisors(),
        api.listTemplates().catch(() => [] as SupervisorTemplate[]),
      ]);
      setSupervisors(items);
      setTemplates(presets);
      setError(null);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not load supervisors");
    }
  }, []);

  usePolling(load, 10000);

  function toggle(list: string[], setList: (next: string[]) => void, action: string) {
    setList(list.includes(action) ? list.filter((item) => item !== action) : [...list, action]);
  }

  /** Load a preset into the form so it can still be adjusted before saving. */
  function applyTemplate(template: SupervisorTemplate) {
    setName(template.name);
    setInstruction(template.base_instruction);
    setActions(template.allowed_actions);
    setApprovalActions(template.require_approval_for);
    setAggressiveness(template.wake_aggressiveness);
    setWakeMinutes(template.default_wake_minutes);
    setMaxAgeMinutes(template.max_age_minutes);
    setAppliedTemplate(template.key);
    document
      .getElementById("supervisor-form")
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
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
        continue_as_new_after_events: continueAfter,
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
      <SectionHeading
        eyebrow="Policies"
        title="Supervisors"
        description="A supervisor is the reusable policy a run starts from: what it may do, how eagerly it wakes, and what needs a human before it happens."
      />

      <ErrorBanner message={error} onRetry={() => void load()} />

      {/* ------------------------------------------------------- templates */}
      {templates.length > 0 && (
        <section className="space-y-3">
          <div className="flex items-center gap-2">
            <Sparkles className="h-3.5 w-3.5 text-brand-600" strokeWidth={2.4} />
            <h2 className="text-sm font-semibold tracking-tight text-ink-900">
              Start from a template
            </h2>
          </div>
          <div className="grid gap-3 lg:grid-cols-3">
            {templates.map((template, index) => {
              const art = TEMPLATE_ART[template.key] ?? TEMPLATE_ART.standard;
              const Icon = art.icon;
              const applied = appliedTemplate === template.key;
              return (
                <motion.button
                  key={template.key}
                  type="button"
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: index * 0.06, duration: 0.3 }}
                  onClick={() => applyTemplate(template)}
                  className={cx(
                    "group relative overflow-hidden rounded-xl border bg-gradient-to-b to-white p-4 text-left shadow-card transition-all duration-200",
                    "hover:-translate-y-0.5 hover:shadow-pop focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2",
                    art.tint,
                    applied ? "border-brand-400 ring-2 ring-brand-200" : "border-ink-200",
                  )}
                >
                  <div className="flex items-start justify-between gap-2">
                    <span
                      className={cx(
                        "grid h-9 w-9 place-items-center rounded-lg bg-white text-ink-700 ring-1 ring-inset",
                        art.ring,
                      )}
                    >
                      <Icon className="h-4 w-4" strokeWidth={2.1} />
                    </span>
                    {applied && (
                      <span className="inline-flex items-center gap-1 rounded-full bg-brand-600 px-2 py-0.5 text-[10px] font-semibold text-white">
                        <Check className="h-3 w-3" strokeWidth={3} />
                        Loaded
                      </span>
                    )}
                  </div>

                  <h3 className="mt-3 text-sm font-semibold text-ink-900">{template.name}</h3>
                  <p className="mt-1 text-xs leading-5 text-ink-600">{template.description}</p>

                  <dl className="mt-3 space-y-1.5 border-t border-ink-200/70 pt-2.5 text-[11px]">
                    <div className="flex items-center justify-between">
                      <dt className="flex items-center gap-1 text-ink-500">
                        <Gauge className="h-3 w-3" strokeWidth={2.2} />
                        Wake sensitivity
                      </dt>
                      <dd className="font-semibold text-ink-800">{template.wake_aggressiveness}</dd>
                    </div>
                    <div className="flex items-center justify-between">
                      <dt className="flex items-center gap-1 text-ink-500">
                        <Timer className="h-3 w-3" strokeWidth={2.2} />
                        Review interval
                      </dt>
                      <dd className="font-semibold text-ink-800">
                        {template.default_wake_minutes}m
                      </dd>
                    </div>
                    <div className="flex items-center justify-between">
                      <dt className="flex items-center gap-1 text-ink-500">
                        <ShieldCheck className="h-3 w-3" strokeWidth={2.2} />
                        Human approval
                      </dt>
                      <dd className="font-semibold text-ink-800">
                        {template.require_approval_for.length > 0
                          ? `${template.require_approval_for.length} action${
                              template.require_approval_for.length > 1 ? "s" : ""
                            }`
                          : "Not required"}
                      </dd>
                    </div>
                    <div className="flex items-center justify-between">
                      <dt className="text-ink-500">Allowed actions</dt>
                      <dd className="font-semibold text-ink-800">
                        {template.allowed_actions.length} of 5
                      </dd>
                    </div>
                  </dl>

                  <span className="mt-3 inline-flex items-center gap-1 text-[11px] font-medium text-brand-700 opacity-0 transition-opacity duration-200 group-hover:opacity-100">
                    <Wand2 className="h-3 w-3" strokeWidth={2.4} />
                    Load into the form
                  </span>
                </motion.button>
              );
            })}
          </div>
        </section>
      )}

      <div className="grid gap-5 lg:grid-cols-5">
        {/* ---------------------------------------------------------- form */}
        <div className="lg:col-span-3" id="supervisor-form">
          <AnimatedCard>
            <Card
              title="New supervisor"
              subtitle="Every field is a policy the workflow enforces"
              icon={SlidersHorizontal}
            >
              <form onSubmit={submit} className="space-y-4">
                <Field label="Name" htmlFor="name">
                  <input
                    id="name"
                    value={name}
                    onChange={(event) => setName(event.target.value)}
                    required
                    maxLength={200}
                    className={inputClass}
                  />
                </Field>

                <Field
                  label="Base instruction"
                  htmlFor="instruction"
                  hint="Sent to the agent on every decision, alongside live run instructions."
                >
                  <textarea
                    id="instruction"
                    value={instruction}
                    onChange={(event) => setInstruction(event.target.value)}
                    required
                    rows={4}
                    maxLength={4000}
                    className={inputClass}
                  />
                </Field>

                <fieldset>
                  <legend className="text-xs font-medium text-ink-700">Allowed actions</legend>
                  <p className="mt-0.5 text-[11px] text-ink-500">
                    Enforced in the schema, in the activity, and again at execution.
                  </p>
                  <div className="mt-2 grid gap-1.5 sm:grid-cols-2">
                    {ALL_ACTIONS.map((action) => {
                      const on = actions.includes(action);
                      return (
                        <label
                          key={action}
                          className={cx(
                            "flex cursor-pointer items-center gap-2 rounded-lg border px-2.5 py-2 text-xs transition-colors duration-150",
                            on
                              ? "border-brand-200 bg-brand-50/60 text-ink-900"
                              : "border-ink-200 bg-white text-ink-600 hover:bg-ink-50",
                          )}
                        >
                          <input
                            type="checkbox"
                            checked={on}
                            onChange={() => toggle(actions, setActions, action)}
                            className="h-3.5 w-3.5 rounded border-ink-300 text-brand-600 focus:ring-brand-500"
                          />
                          {titleCase(action)}
                        </label>
                      );
                    })}
                  </div>
                </fieldset>

                <fieldset>
                  <legend className="text-xs font-medium text-ink-700">
                    Require human approval before running
                  </legend>
                  <p className="mt-0.5 text-[11px] text-ink-500">
                    These are proposed but held until someone decides.
                  </p>
                  <div className="mt-2 grid gap-1.5 sm:grid-cols-2">
                    {ALL_ACTIONS.filter((action) => actions.includes(action)).map((action) => {
                      const on = approvalActions.includes(action);
                      return (
                        <label
                          key={action}
                          className={cx(
                            "flex cursor-pointer items-center gap-2 rounded-lg border px-2.5 py-2 text-xs transition-colors duration-150",
                            on
                              ? "border-orange-200 bg-orange-50/60 text-ink-900"
                              : "border-ink-200 bg-white text-ink-600 hover:bg-ink-50",
                          )}
                        >
                          <input
                            type="checkbox"
                            checked={on}
                            onChange={() => toggle(approvalActions, setApprovalActions, action)}
                            className="h-3.5 w-3.5 rounded border-ink-300 text-orange-600 focus:ring-orange-500"
                          />
                          {titleCase(action)}
                        </label>
                      );
                    })}
                  </div>
                </fieldset>

                <div>
                  <span className="text-xs font-medium text-ink-700">Wake sensitivity</span>
                  <div className="mt-1.5 grid grid-cols-3 gap-1.5">
                    {AGGRESSIVENESS.map((level) => (
                      <button
                        key={level}
                        type="button"
                        onClick={() => setAggressiveness(level)}
                        className={cx(
                          "rounded-lg border px-2 py-2 text-xs font-medium transition-all duration-150",
                          aggressiveness === level
                            ? "border-brand-400 bg-brand-50 text-brand-900 ring-1 ring-brand-200"
                            : "border-ink-200 bg-white text-ink-600 hover:bg-ink-50",
                        )}
                      >
                        {level}
                        <span className="mt-0.5 block text-[10px] font-normal text-ink-500">
                          {level === "LOW"
                            ? "critical only"
                            : level === "HIGH"
                              ? "wake often"
                              : "balanced"}
                        </span>
                      </button>
                    ))}
                  </div>
                </div>

                <div className="grid gap-3 sm:grid-cols-3">
                  <Field label="Review every (min)" htmlFor="wake">
                    <input
                      id="wake"
                      type="number"
                      min={1}
                      max={10080}
                      value={wakeMinutes}
                      onChange={(event) => setWakeMinutes(Number(event.target.value))}
                      className={inputClass}
                    />
                  </Field>
                  <Field label="Max age (min)" htmlFor="maxage">
                    <input
                      id="maxage"
                      type="number"
                      min={1}
                      value={maxAgeMinutes}
                      onChange={(event) => setMaxAgeMinutes(Number(event.target.value))}
                      className={inputClass}
                    />
                  </Field>
                  <Field label="Continue-As-New" htmlFor="can" hint="0 disables it">
                    <input
                      id="can"
                      type="number"
                      min={0}
                      value={continueAfter}
                      onChange={(event) => setContinueAfter(Number(event.target.value))}
                      className={inputClass}
                    />
                  </Field>
                </div>

                <div className="flex items-center gap-3 border-t border-ink-100 pt-4">
                  <Button
                    type="submit"
                    loading={saving}
                    disabled={actions.length === 0}
                    icon={Sparkles}
                  >
                    Create supervisor
                  </Button>
                  {actions.length === 0 && (
                    <p className="text-[11px] text-rose-600">Select at least one action.</p>
                  )}
                </div>
              </form>
            </Card>
          </AnimatedCard>
        </div>

        {/* ------------------------------------------------- existing list */}
        <div className="lg:col-span-2">
          <AnimatedCard delay={0.08}>
            <Card
              title="Configured supervisors"
              subtitle={supervisors ? `${supervisors.length} total` : undefined}
              icon={ShieldCheck}
            >
              {supervisors === null ? (
                <div className="space-y-2.5">
                  {[0, 1, 2].map((key) => (
                    <div key={key} className="rounded-lg border border-ink-200 p-3">
                      <Skeleton className="h-3.5 w-32" />
                      <Skeleton className="mt-2 h-3 w-full" />
                      <Skeleton className="mt-1.5 h-3 w-24" />
                    </div>
                  ))}
                </div>
              ) : supervisors.length === 0 ? (
                <EmptyState icon={ShieldCheck} title="No supervisors yet">
                  Load a template above, adjust it, and create your first policy.
                </EmptyState>
              ) : (
                <ul className="scroll-slim max-h-[34rem] space-y-2.5 overflow-y-auto pr-1">
                  {supervisors.map((supervisor) => (
                    <li
                      key={supervisor.id}
                      className="rounded-lg border border-ink-200 bg-white p-3 transition-colors duration-200 hover:border-brand-300 hover:bg-brand-50/20"
                    >
                      <p className="text-xs font-semibold text-ink-900">{supervisor.name}</p>
                      <p className="mt-1 line-clamp-2 text-[11px] leading-4 text-ink-500">
                        {supervisor.base_instruction}
                      </p>
                      <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[10px]">
                        <span className="rounded bg-ink-100 px-1.5 py-0.5 font-semibold text-ink-600">
                          {supervisor.config.wake_aggressiveness ?? "BALANCED"}
                        </span>
                        <span className="text-ink-500">
                          {supervisor.allowed_actions.length} actions
                        </span>
                        <span className="text-ink-400">·</span>
                        <span className="text-ink-500">
                          every {supervisor.config.default_wake_minutes ?? 60}m
                        </span>
                        {(supervisor.config.require_approval_for?.length ?? 0) > 0 && (
                          <span className="inline-flex items-center gap-1 rounded bg-orange-50 px-1.5 py-0.5 font-medium text-orange-700">
                            <ShieldCheck className="h-2.5 w-2.5" strokeWidth={2.4} />
                            approval
                          </span>
                        )}
                        {(supervisor.config.continue_as_new_after_events ?? 0) > 0 && (
                          <span className="inline-flex items-center gap-1 rounded bg-fuchsia-50 px-1.5 py-0.5 font-medium text-fuchsia-700">
                            <Repeat className="h-2.5 w-2.5" strokeWidth={2.4} />
                            {supervisor.config.continue_as_new_after_events}
                          </span>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </AnimatedCard>
        </div>
      </div>
    </div>
  );
}
