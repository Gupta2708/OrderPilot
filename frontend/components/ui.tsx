"use client";

import { motion } from "framer-motion";
import type { LucideIcon } from "lucide-react";
import { AlertTriangle, Loader2 } from "lucide-react";
import type { ReactNode } from "react";

export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

/* ------------------------------------------------------------------ status */

/**
 * Run status colours. Each state reads differently at a glance, because the
 * dashboard's job is to make "which order needs me" answerable without reading.
 */
const STATUS_STYLES: Record<string, { dot: string; chip: string; label?: string }> = {
  ACTING: { dot: "bg-amber-500", chip: "bg-amber-50 text-amber-800 ring-amber-200" },
  SLEEPING: { dot: "bg-sky-500", chip: "bg-sky-50 text-sky-800 ring-sky-200" },
  PAUSED: { dot: "bg-ink-400", chip: "bg-ink-100 text-ink-700 ring-ink-300" },
  PENDING: { dot: "bg-ink-300", chip: "bg-ink-50 text-ink-600 ring-ink-200" },
  AWAITING_APPROVAL: {
    dot: "bg-orange-500",
    chip: "bg-orange-50 text-orange-800 ring-orange-200",
    label: "AWAITING APPROVAL",
  },
  ATTENTION: { dot: "bg-orange-500", chip: "bg-orange-50 text-orange-800 ring-orange-200" },
  COMPLETED: { dot: "bg-emerald-500", chip: "bg-emerald-50 text-emerald-800 ring-emerald-200" },
  TERMINATED: { dot: "bg-rose-500", chip: "bg-rose-50 text-rose-800 ring-rose-200" },
};

export function StatusBadge({
  status,
  size = "md",
  pulse = false,
}: {
  status: string;
  size?: "sm" | "md";
  pulse?: boolean;
}) {
  const style = STATUS_STYLES[status] ?? STATUS_STYLES.PENDING;
  const live = pulse && (status === "ACTING" || status === "AWAITING_APPROVAL");
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1.5 rounded-full font-semibold uppercase tracking-wide ring-1 ring-inset",
        size === "sm" ? "px-2 py-0.5 text-[10px]" : "px-2.5 py-1 text-[11px]",
        style.chip,
      )}
    >
      <span className={cx("relative inline-flex h-1.5 w-1.5 rounded-full", style.dot)}>
        {live && <span className="pulse-ring absolute inset-0 rounded-full" />}
      </span>
      {style.label ?? status}
    </span>
  );
}

const SEVERITY_STYLES: Record<string, string> = {
  LOW: "bg-ink-100 text-ink-600 ring-ink-200",
  MEDIUM: "bg-amber-50 text-amber-800 ring-amber-200",
  HIGH: "bg-orange-50 text-orange-800 ring-orange-200",
  CRITICAL: "bg-rose-50 text-rose-800 ring-rose-200",
};

export function SeverityBadge({ severity }: { severity: string }) {
  return (
    <span
      className={cx(
        "inline-flex items-center rounded-md px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ring-1 ring-inset",
        SEVERITY_STYLES[severity] ?? SEVERITY_STYLES.LOW,
      )}
    >
      {severity}
    </span>
  );
}

export function Chip({
  children,
  tone = "neutral",
  icon: Icon,
}: {
  children: ReactNode;
  tone?: "neutral" | "brand" | "warn" | "danger" | "success";
  icon?: LucideIcon;
}) {
  const tones = {
    neutral: "bg-ink-50 text-ink-600 ring-ink-200",
    brand: "bg-brand-50 text-brand-800 ring-brand-200",
    warn: "bg-amber-50 text-amber-800 ring-amber-200",
    danger: "bg-rose-50 text-rose-800 ring-rose-200",
    success: "bg-emerald-50 text-emerald-800 ring-emerald-200",
  }[tone];
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset",
        tones,
      )}
    >
      {Icon && <Icon className="h-3 w-3" strokeWidth={2.2} />}
      {children}
    </span>
  );
}

/* -------------------------------------------------------------------- card */

export function Card({
  title,
  subtitle,
  icon: Icon,
  action,
  children,
  className = "",
  bodyClassName = "",
  accent,
}: {
  title?: string;
  subtitle?: string;
  icon?: LucideIcon;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
  accent?: "brand" | "warn" | "success" | "danger";
}) {
  const accents = {
    brand: "border-brand-200",
    warn: "border-amber-300",
    success: "border-emerald-200",
    danger: "border-rose-200",
  };
  return (
    <section
      className={cx(
        "rounded-xl border border-ink-200 bg-white shadow-card transition-shadow duration-200 hover:shadow-lift",
        accent && accents[accent],
        className,
      )}
    >
      {(title || action) && (
        <header className="flex items-start justify-between gap-3 border-b border-ink-100 px-4 py-3">
          <div className="flex min-w-0 items-start gap-2.5">
            {Icon && (
              <span className="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-md bg-ink-50 text-ink-500 ring-1 ring-inset ring-ink-200">
                <Icon className="h-3.5 w-3.5" strokeWidth={2.2} />
              </span>
            )}
            <div className="min-w-0">
              {title && (
                <h2 className="truncate text-[13px] font-semibold tracking-tight text-ink-900">
                  {title}
                </h2>
              )}
              {subtitle && <p className="mt-0.5 text-[11px] text-ink-500">{subtitle}</p>}
            </div>
          </div>
          {action && <div className="shrink-0">{action}</div>}
        </header>
      )}
      <div className={cx("px-4 py-3.5", bodyClassName)}>{children}</div>
    </section>
  );
}

/** Cards animate in on first paint; a stagger reads as "the page assembled". */
export function AnimatedCard({
  delay = 0,
  children,
  className = "",
}: {
  delay?: number;
  children: ReactNode;
  className?: string;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.32, delay, ease: [0.22, 1, 0.36, 1] }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

/* -------------------------------------------------------------------- stat */

export function Stat({
  label,
  value,
  hint,
  icon: Icon,
  tone = "neutral",
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  icon?: LucideIcon;
  tone?: "neutral" | "brand" | "warn" | "success" | "danger";
}) {
  const tones = {
    neutral: "text-ink-900",
    brand: "text-brand-700",
    warn: "text-amber-700",
    success: "text-emerald-700",
    danger: "text-rose-700",
  }[tone];
  return (
    <div className="group rounded-xl border border-ink-200 bg-white px-4 py-3 shadow-card transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lift">
      <div className="flex items-center gap-1.5">
        {Icon && <Icon className="h-3.5 w-3.5 text-ink-400" strokeWidth={2.2} />}
        <p className="text-[10px] font-semibold uppercase tracking-wider text-ink-500">{label}</p>
      </div>
      <p className={cx("tnum mt-1.5 text-2xl font-semibold leading-none tracking-tight", tones)}>
        {value}
      </p>
      {hint && <p className="mt-1 text-[11px] text-ink-400">{hint}</p>}
    </div>
  );
}

/* ------------------------------------------------------------------ button */

export function Button({
  children,
  onClick,
  disabled,
  loading,
  variant = "primary",
  size = "md",
  type = "button",
  icon: Icon,
  title,
  className = "",
}: {
  children?: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  loading?: boolean;
  variant?: "primary" | "secondary" | "ghost" | "danger" | "success";
  size?: "sm" | "md";
  type?: "button" | "submit";
  icon?: LucideIcon;
  title?: string;
  className?: string;
}) {
  const variants = {
    primary:
      "bg-brand-700 text-white shadow-card hover:bg-brand-800 active:bg-brand-900 disabled:bg-brand-700/40 disabled:shadow-none",
    secondary:
      "bg-white text-ink-700 ring-1 ring-inset ring-ink-300 shadow-card hover:bg-ink-50 hover:text-ink-900 active:bg-ink-100 disabled:text-ink-400 disabled:shadow-none",
    ghost: "text-ink-600 hover:bg-ink-100 hover:text-ink-900 disabled:text-ink-300",
    danger:
      "bg-rose-600 text-white shadow-card hover:bg-rose-700 active:bg-rose-800 disabled:bg-rose-600/40 disabled:shadow-none",
    success:
      "bg-emerald-600 text-white shadow-card hover:bg-emerald-700 active:bg-emerald-800 disabled:bg-emerald-600/40 disabled:shadow-none",
  }[variant];
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled || loading}
      title={title}
      className={cx(
        "inline-flex items-center justify-center gap-1.5 rounded-lg font-medium transition-all duration-150",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2",
        "disabled:cursor-not-allowed active:scale-[0.98]",
        size === "sm" ? "px-2.5 py-1.5 text-xs" : "px-3.5 py-2 text-sm",
        variants,
        className,
      )}
    >
      {loading ? (
        <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={2.4} />
      ) : (
        Icon && <Icon className="h-3.5 w-3.5" strokeWidth={2.2} />
      )}
      {children}
    </button>
  );
}

/* -------------------------------------------------------------------- tabs */

export function Tabs<T extends string>({
  tabs,
  active,
  onChange,
}: {
  tabs: Array<{ id: T; label: string; icon?: LucideIcon; count?: number }>;
  active: T;
  onChange: (id: T) => void;
}) {
  return (
    <div
      role="tablist"
      className="flex gap-1 overflow-x-auto rounded-lg bg-ink-100/70 p-1 scroll-slim"
    >
      {tabs.map((tab) => {
        const selected = tab.id === active;
        return (
          <button
            key={tab.id}
            role="tab"
            aria-selected={selected}
            onClick={() => onChange(tab.id)}
            className={cx(
              "relative flex shrink-0 items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors duration-150",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500",
              selected ? "text-ink-900" : "text-ink-500 hover:text-ink-800",
            )}
          >
            {selected && (
              <motion.span
                layoutId="tab-pill"
                className="absolute inset-0 rounded-md bg-white shadow-card"
                transition={{ type: "spring", stiffness: 380, damping: 32 }}
              />
            )}
            <span className="relative flex items-center gap-1.5">
              {tab.icon && <tab.icon className="h-3.5 w-3.5" strokeWidth={2.2} />}
              {tab.label}
              {typeof tab.count === "number" && (
                <span
                  className={cx(
                    "tnum rounded px-1 py-px text-[10px] font-semibold",
                    selected ? "bg-ink-100 text-ink-600" : "bg-ink-200/70 text-ink-500",
                  )}
                >
                  {tab.count}
                </span>
              )}
            </span>
          </button>
        );
      })}
    </div>
  );
}

/* ------------------------------------------------------- states and inputs */

export function ErrorBanner({ message, onRetry }: { message: string | null; onRetry?: () => void }) {
  if (!message) return null;
  return (
    <motion.div
      initial={{ opacity: 0, y: -6 }}
      animate={{ opacity: 1, y: 0 }}
      role="alert"
      className="flex items-start justify-between gap-3 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3"
    >
      <div className="flex items-start gap-2.5">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-rose-600" strokeWidth={2.2} />
        <p className="text-sm text-rose-800">{message}</p>
      </div>
      {onRetry && (
        <Button variant="secondary" size="sm" onClick={onRetry}>
          Retry
        </Button>
      )}
    </motion.div>
  );
}

export function EmptyState({
  icon: Icon,
  title,
  children,
  action,
}: {
  icon?: LucideIcon;
  title?: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-4 py-10 text-center">
      {Icon && (
        <span className="grid h-9 w-9 place-items-center rounded-full bg-ink-50 text-ink-400 ring-1 ring-inset ring-ink-200">
          <Icon className="h-4 w-4" strokeWidth={2} />
        </span>
      )}
      {title && <p className="text-sm font-medium text-ink-700">{title}</p>}
      {children && <p className="max-w-sm text-xs leading-5 text-ink-500">{children}</p>}
      {action && <div className="mt-1">{action}</div>}
    </div>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={cx("skeleton rounded-md", className)} />;
}

export function Field({
  label,
  hint,
  htmlFor,
  children,
}: {
  label: string;
  hint?: string;
  htmlFor?: string;
  children: ReactNode;
}) {
  return (
    <div>
      <label htmlFor={htmlFor} className="block text-xs font-medium text-ink-700">
        {label}
      </label>
      {children}
      {hint && <p className="mt-1 text-[11px] leading-4 text-ink-500">{hint}</p>}
    </div>
  );
}

export const inputClass =
  "mt-1.5 w-full rounded-lg border border-ink-300 bg-white px-3 py-2 text-sm text-ink-900 placeholder:text-ink-400 " +
  "transition-colors focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20 " +
  "disabled:bg-ink-50 disabled:text-ink-400";

export function SectionHeading({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div>
        {eyebrow && (
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-brand-700">
            {eyebrow}
          </p>
        )}
        <h1 className="mt-1 text-xl font-semibold tracking-tight text-ink-900">{title}</h1>
        {description && <p className="mt-1 max-w-2xl text-sm text-ink-500">{description}</p>}
      </div>
      {action}
    </div>
  );
}
