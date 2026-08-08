"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

const NAV = [
  { href: "/", label: "Search" },
  { href: "/map", label: "Map" },
  { href: "/alerts", label: "Alerts" },
  { href: "/profile", label: "My criteria" },
  { href: "/ingest", label: "Add land" },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [theme, setTheme] = useState<"light" | "dark">("light");

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);

  return (
    <div className="min-h-screen">
      <header className="shell-header">
        <div className="mx-auto flex max-w-[1240px] items-center justify-between gap-4 px-4 py-3.5">
          <div className="flex items-center gap-8">
            <Link href="/" className="flex items-baseline gap-2">
              <span className="display text-2xl font-semibold text-[var(--brand)]">LandSignal</span>
              <span className="hidden text-xs text-[var(--muted)] sm:inline">Land investment intelligence</span>
            </Link>
            <nav className="hidden items-center gap-1 md:flex">
              {NAV.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="rounded-full px-3 py-1.5 text-sm"
                  style={{
                    color: pathname === item.href ? "var(--brand)" : "var(--muted)",
                    background: pathname === item.href ? "var(--bg-soft)" : "transparent",
                    fontWeight: pathname === item.href ? 650 : 500,
                  }}
                >
                  {item.label}
                </Link>
              ))}
            </nav>
          </div>
          <button type="button" className="btn btn-ghost text-sm" onClick={() => setTheme((t) => (t === "light" ? "dark" : "light"))}>
            {theme === "light" ? "Dark" : "Light"}
          </button>
        </div>
      </header>
      <main className="mx-auto max-w-[1240px] px-4 py-6">{children}</main>
      <footer className="mx-auto max-w-[1240px] px-4 pb-10 text-sm text-[var(--muted)]">
        LandSignal screens opportunities — it never buys land for you. Every score is explainable and sourced.
      </footer>
    </div>
  );
}
