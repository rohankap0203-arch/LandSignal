"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { ScoreBar } from "@/components/score-bar";
import { landsignalApi } from "@/lib/api";

type WatchItem = {
  parcel_id: string;
  title: string;
  location: string;
  current: {
    opportunity?: number | null;
    risk?: number | null;
    confidence?: number | null;
    ask?: number | null;
    status?: string | null;
  };
  baseline: Record<string, unknown>;
  changes: Array<{ metric: string; from: unknown; to: unknown }>;
};

export default function WatchlistPage() {
  const { data: session, status: authStatus } = useSession();
  const signedIn = Boolean(session?.user?.id);
  const [items, setItems] = useState<WatchItem[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    setError("");
    try {
      const data = await landsignalApi.watchlist();
      setItems((data.items as WatchItem[]) || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load watchlist");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="display text-3xl font-semibold">Watchlist</h1>
          <p className="mt-1 max-w-2xl text-sm text-[var(--muted)]">
            Properties you pinned. Opportunity score, risk, how complete the file is, price, and status
            update here.
          </p>
        </div>
        <button type="button" className="btn btn-ghost" onClick={() => void load()}>
          Refresh metrics
        </button>
      </div>

      {authStatus !== "loading" && !signedIn ? (
        <div className="panel p-5 space-y-3">
          <div className="display text-lg font-semibold">Sign in to keep a personal watchlist</div>
          <p className="text-sm text-[var(--muted)]">
            Create an account so watched parcels stay on your profile.
          </p>
          <div className="flex flex-wrap gap-2">
            <Link href="/login?mode=signup&callbackUrl=%2Fwatchlist" className="btn btn-dark">
              Create account
            </Link>
            <Link href="/login?callbackUrl=%2Fwatchlist" className="btn btn-ghost">
              Sign in
            </Link>
          </div>
        </div>
      ) : null}

      {error && <div className="panel p-4 text-[var(--danger)]">{error}</div>}
      {loading && <div className="text-[var(--muted)]">Loading watchlist…</div>}

      {!loading && !items.length && signedIn && (
        <div className="panel empty-state">
          <div className="display text-2xl">Nothing watched yet</div>
          <p className="mx-auto mt-2 max-w-lg">
            Open any result → tap the <strong>eye</strong> on the intelligence panel. We’ll keep the major
            metrics and listing status here.
          </p>
          <Link href="/" className="btn btn-dark mt-4 inline-flex">
            Back to search
          </Link>
        </div>
      )}
      <div className="grid gap-4">
        {items.map((item) => (
          <article key={item.parcel_id} className="panel p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <Link
                  href={`/parcels/${item.parcel_id}`}
                  className="display text-xl font-semibold hover:text-[var(--brand)]"
                >
                  {item.title}
                </Link>
                <div className="mt-1 text-sm text-[var(--muted)]">{item.location}</div>
                <div className="mt-1 text-xs text-[var(--muted)]">
                  Status: {String(item.current.status || "—")}
                  {item.current.ask != null ? ` · Ask $${Number(item.current.ask).toLocaleString()}` : ""}
                </div>
              </div>
              <button
                type="button"
                className="btn btn-ghost"
                onClick={async () => {
                  await landsignalApi.unwatch(item.parcel_id);
                  void load();
                }}
              >
                Remove
              </button>
            </div>
            <div className="mt-4 grid gap-3 md:grid-cols-2">
              <ScoreBar label="Opportunity score" value={Number(item.current.opportunity || 0)} />
              <ScoreBar label="Risk" value={Number(item.current.risk || 0)} invert />
            </div>
            <div className="mt-2 text-sm text-[var(--muted)]">
              File complete {Math.round(Number(item.current.confidence || 0))}/100
            </div>
            {!!item.changes?.length && (
              <ul className="mt-3 space-y-1 text-sm">
                {item.changes.map((c) => (
                  <li key={`${c.metric}-${String(c.to)}`}>
                    <strong>{c.metric}</strong> moved {String(c.from)} → {String(c.to)}
                  </li>
                ))}
              </ul>
            )}
            {!item.changes?.length && (
              <p className="mt-3 text-sm text-[var(--muted)]">No metric changes since you watched this.</p>
            )}
          </article>
        ))}
      </div>
    </div>
  );
}
