"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { cn } from "@/lib/cn";

const NAV = [
  { href: "/", label: "Opportunity Radar" },
  { href: "/map", label: "Map" },
  { href: "/ingest", label: "Ingest" },
  { href: "/alerts", label: "Alerts" },
  { href: "/profile", label: "Investor Profile" },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [theme, setTheme] = useState<"dark" | "light">("dark");

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);

  return (
    <div className="min-h-screen">
      <header className="border-b border-[var(--border)] bg-[var(--bg-elevated)]/90 backdrop-blur sticky top-0 z-20">
        <div className="mx-auto flex max-w-[1600px] items-center justify-between gap-4 px-4 py-3">
          <div className="flex items-center gap-6">
            <Link href="/" className="flex items-baseline gap-2">
              <span className="text-lg font-semibold tracking-tight">LandSignal</span>
              <span className="mono text-[11px] text-[var(--muted)]">v0.1 · SCREENING</span>
            </Link>
            <nav className="hidden items-center gap-1 md:flex">
              {NAV.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "px-3 py-1.5 text-sm text-[var(--muted)] hover:text-[var(--text)]",
                    pathname === item.href && "text-[var(--text)] border-b border-[var(--accent)]",
                  )}
                >
                  {item.label}
                </Link>
              ))}
            </nav>
          </div>
          <button
            type="button"
            className="panel px-3 py-1.5 text-xs text-[var(--muted)]"
            onClick={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
          >
            {theme === "dark" ? "Light" : "Dark"} mode
          </button>
        </div>
      </header>
      <main className="mx-auto max-w-[1600px] px-4 py-5">{children}</main>
      <footer className="mx-auto max-w-[1600px] px-4 pb-8 text-xs text-[var(--muted)]">
        LandSignal does not execute purchases. Scores are screening intelligence, not appraisals or legal opinions.
      </footer>
    </div>
  );
}
