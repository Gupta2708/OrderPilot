"use client";

import { motion } from "framer-motion";
import { LayoutDashboard, PlusCircle, SlidersHorizontal } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useState } from "react";
import { Logo, Wordmark } from "@/components/brand";
import { API_BASE } from "@/lib/api";
import { usePolling } from "@/lib/use-polling";
import { cx } from "@/components/ui";

const LINKS = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard, exact: true },
  { href: "/supervisors", label: "Supervisors", icon: SlidersHorizontal },
  { href: "/runs/new", label: "Start run", icon: PlusCircle },
];

type Health = "checking" | "online" | "offline";

/**
 * Control-plane health, polled from the API's own liveness endpoint.
 *
 * Deliberately labelled "API" rather than "Temporal": the API stays up and
 * serves reads even when Temporal is unreachable, so claiming Temporal health
 * here would be a guess. The per-run header shows whether a run's state came
 * from the workflow or the database, which is the honest Temporal signal.
 */
function StatusPill() {
  const [health, setHealth] = useState<Health>("checking");

  const check = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/health`, { cache: "no-store" });
      setHealth(response.ok ? "online" : "offline");
    } catch {
      setHealth("offline");
    }
  }, []);

  usePolling(check, 10000);

  const config = {
    checking: { dot: "bg-ink-300", text: "text-ink-500", label: "Connecting" },
    online: { dot: "bg-emerald-500", text: "text-ink-600", label: "API live" },
    offline: { dot: "bg-rose-500", text: "text-rose-700", label: "API offline" },
  }[health];

  return (
    <span
      title={
        health === "offline"
          ? "The control plane is not reachable on port 8000."
          : "Control plane reachable. Per-run Temporal state is shown on each run."
      }
      className={cx(
        "hidden items-center gap-1.5 rounded-full border border-ink-200 bg-white px-2.5 py-1 text-[11px] font-medium shadow-card sm:inline-flex",
        config.text,
      )}
    >
      <span className={cx("relative inline-flex h-1.5 w-1.5 rounded-full", config.dot)}>
        {health === "online" && <span className="pulse-ring absolute inset-0 rounded-full" />}
      </span>
      {config.label}
    </span>
  );
}

export function Nav() {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-40 border-b border-ink-200/80 bg-white/85 backdrop-blur-md">
      <div className="mx-auto flex h-14 max-w-[1400px] items-center gap-3 px-4 sm:px-6">
        <Link
          href="/"
          className="flex items-center gap-2.5 rounded-lg transition-opacity hover:opacity-80"
        >
          <Logo />
          <Wordmark />
        </Link>

        <nav className="ml-2 flex items-center gap-0.5 sm:ml-6">
          {LINKS.map((link) => {
            const active = link.exact ? pathname === link.href : pathname.startsWith(link.href);
            return (
              <Link
                key={link.href}
                href={link.href}
                className={cx(
                  "relative flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[13px] font-medium transition-colors duration-150",
                  active ? "text-ink-900" : "text-ink-500 hover:bg-ink-100 hover:text-ink-800",
                )}
              >
                {active && (
                  <motion.span
                    layoutId="nav-active"
                    className="absolute inset-0 rounded-lg bg-ink-100"
                    transition={{ type: "spring", stiffness: 400, damping: 34 }}
                  />
                )}
                <span className="relative flex items-center gap-1.5">
                  <link.icon className="h-3.5 w-3.5" strokeWidth={2.2} />
                  <span className="hidden sm:inline">{link.label}</span>
                </span>
              </Link>
            );
          })}
        </nav>

        <div className="ml-auto flex items-center gap-2">
          <StatusPill />
          <a
            href="http://127.0.0.1:8233"
            target="_blank"
            rel="noreferrer"
            title="Open the Temporal Web UI"
            className="hidden rounded-lg border border-ink-200 bg-white px-2.5 py-1 text-[11px] font-medium text-ink-600 shadow-card transition-colors hover:bg-ink-50 hover:text-ink-900 md:inline-flex"
          >
            Temporal UI
          </a>
        </div>
      </div>
    </header>
  );
}
