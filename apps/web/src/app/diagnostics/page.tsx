"use client";

import { useEffect, useState } from "react";

type Diag = Record<string, unknown>;

export default function SearchDiagnosticsPage() {
  const [search, setSearch] = useState<Diag | null>(null);
  const [attom, setAttom] = useState<Diag | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [s, a] = await Promise.all([
          fetch("/v1/diagnostics/search").then((r) => r.json()),
          fetch("/v1/diagnostics/attom").then((r) => r.json()),
        ]);
        if (!cancelled) {
          setSearch(s);
          setAttom(a);
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load diagnostics");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className="mx-auto max-w-5xl px-4 py-10">
      <h1 className="display text-3xl font-semibold text-[var(--ink)]">Search diagnostics</h1>
      <p className="mt-2 max-w-2xl text-[var(--muted)]">
        Internal observability for Show Matches and ATTOM enrichment. API keys are never shown.
      </p>
      {error ? <p className="mt-4 text-[var(--danger)]">{error}</p> : null}
      <section className="panel mt-8 p-5">
        <h2 className="text-lg font-semibold">ATTOM</h2>
        <pre className="mt-3 overflow-auto text-xs leading-relaxed text-[var(--ink)]">
          {attom ? JSON.stringify(attom, null, 2) : "Loading…"}
        </pre>
      </section>
      <section className="panel mt-6 p-5">
        <h2 className="text-lg font-semibold">Recent searches</h2>
        <pre className="mt-3 overflow-auto text-xs leading-relaxed text-[var(--ink)]">
          {search ? JSON.stringify(search, null, 2) : "Loading…"}
        </pre>
      </section>
    </main>
  );
}
