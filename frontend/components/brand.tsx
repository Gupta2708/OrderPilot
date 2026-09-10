"use client";

import { cx } from "@/components/ui";

/**
 * Product mark: a supervising ring around a steady centre — the workflow
 * watching the order. Drawn inline so it needs no asset pipeline and inherits
 * currentColor.
 */
export function Logo({ className = "h-7 w-7" }: { className?: string }) {
  return (
    <span
      className={cx(
        "grid shrink-0 place-items-center rounded-lg bg-gradient-to-br from-brand-600 to-brand-800 text-white shadow-card",
        className,
      )}
      aria-hidden
    >
      <svg viewBox="0 0 24 24" fill="none" className="h-[62%] w-[62%]">
        <circle cx="12" cy="12" r="8.25" stroke="currentColor" strokeWidth="1.9" opacity="0.55" />
        <path
          d="M12 3.75a8.25 8.25 0 0 1 8.25 8.25"
          stroke="currentColor"
          strokeWidth="2.1"
          strokeLinecap="round"
        />
        <circle cx="12" cy="12" r="2.9" fill="currentColor" />
      </svg>
    </span>
  );
}

export function Wordmark({ compact = false }: { compact?: boolean }) {
  return (
    <span className="flex items-baseline gap-1.5">
      <span className="text-[15px] font-semibold tracking-tight text-ink-900">OrderPilot</span>
      {!compact && (
        <span className="hidden text-[11px] font-medium text-ink-400 sm:inline">
          AI Order Operations
        </span>
      )}
    </span>
  );
}
