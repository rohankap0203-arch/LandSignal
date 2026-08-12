"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useId, useState } from "react";
import { AccountMenu } from "@/components/account-menu";
import { MapPinMark } from "@/components/map-pin-mark";

const NAV = [
  { href: "/", label: "Search" },
  { href: "/watchlist", label: "Watchlist" },
  { href: "/alerts", label: "Land Alerts" },
  { href: "/profile", label: "My criteria" },
];

function navActive(pathname: string, href: string) {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const [menuOpen, setMenuOpen] = useState(false);
  const menuId = useId();
  const isAuthPage = pathname === "/login";

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);

  useEffect(() => {
    setMenuOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMenuOpen(false);
    };
    // Do not lock body overflow — hiding the scrollbar reflows the header and shifts this control.
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [menuOpen]);

  if (isAuthPage) {
    return <div className="min-h-screen">{children}</div>;
  }

  return (
    <div className="min-h-screen">
      <header className="shell-header">
        <div className="shell-header-inner">
          <div className="shell-header-left">
            <Link
              href="/"
              className="shell-brand"
              aria-label="LandSignal home"
              title="Back to home"
              onClick={() => setMenuOpen(false)}
            >
              <MapPinMark className="shell-brand-mark" />
              <span className="shell-brand-name display font-semibold text-[var(--brand)]">LandSignal</span>
              <span className="shell-brand-tagline hidden text-xs text-[var(--muted)] lg:inline">
                Land investment intelligence
              </span>
            </Link>
            <nav className="shell-nav" aria-label="Primary">
              {NAV.map((item) => {
                const active = navActive(pathname, item.href);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className="rounded-full px-3 py-1.5 text-sm"
                    style={{
                      color: active ? "var(--brand)" : "var(--muted)",
                      background: active ? "var(--bg-soft)" : "transparent",
                      fontWeight: active ? 650 : 500,
                    }}
                  >
                    {item.label}
                  </Link>
                );
              })}
            </nav>
          </div>
          <div className="shell-header-actions">
            <button
              type="button"
              className="shell-menu-toggle"
              data-open={menuOpen ? "true" : "false"}
              aria-expanded={menuOpen}
              aria-controls={menuId}
              aria-label={menuOpen ? "Close site menu" : "Open site menu"}
              onClick={() => setMenuOpen((open) => !open)}
            >
              <span className="shell-menu-toggle-bars" data-open={menuOpen ? "true" : "false"} />
            </button>
            <AccountMenu />
          </div>
        </div>
        {menuOpen ? (
          <>
            <button
              type="button"
              className="shell-menu-backdrop"
              aria-label="Close site menu"
              onClick={() => setMenuOpen(false)}
            />
            <nav id={menuId} className="shell-menu-panel" aria-label="Site sections">
              {NAV.map((item) => {
                const active = navActive(pathname, item.href);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className="shell-menu-link"
                    data-active={active ? "true" : "false"}
                    onClick={() => setMenuOpen(false)}
                  >
                    {item.label}
                  </Link>
                );
              })}
              <button
                type="button"
                className="shell-menu-link shell-menu-theme"
                onClick={() => setTheme((t) => (t === "light" ? "dark" : "light"))}
              >
                {theme === "light" ? "Dark mode" : "Light mode"}
              </button>
            </nav>
          </>
        ) : null}
      </header>
      <main className="mx-auto max-w-[1240px] px-4 py-6">{children}</main>
      <footer className="mx-auto max-w-[1240px] px-4 pb-10 text-center text-sm text-[var(--muted)]">
        LandSignal ranks public land deals with access to intelligent insight on location information
      </footer>
    </div>
  );
}
