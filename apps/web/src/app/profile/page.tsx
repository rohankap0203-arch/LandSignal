"use client";

import { useEffect, useState } from "react";
import { landsignalApi } from "@/lib/api";

const STRATEGIES = ["FARMLAND", "DEVELOPMENT", "LAND_BANK", "RECREATIONAL", "ENERGY", "TIMBER"];

export default function ProfilePage() {
  const [profile, setProfile] = useState<Record<string, unknown> | null>(null);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    landsignalApi.profile().then(setProfile).catch(() => setProfile({}));
  }, []);

  if (!profile) return <div className="text-[var(--muted)]">Loading your criteria…</div>;

  const preferred = new Set(
    Array.isArray(profile.preferred_strategies)
      ? (profile.preferred_strategies as string[])
      : [],
  );

  function toggleStrategy(s: string) {
    const next = new Set(preferred);
    if (next.has(s)) next.delete(s);
    else next.add(s);
    setProfile({ ...profile, preferred_strategies: [...next] });
  }

  return (
    <div className="max-w-3xl space-y-5">
      <div>
        <h1 className="display text-3xl font-semibold">My criteria</h1>
        <p className="mt-1 text-sm text-[var(--muted)]">
          These toggles personalize the Fit score on Search. The global LandSignal score stays the same for
          everyone — Fit is “how well this matches you.”
        </p>
      </div>

      <section className="panel grid gap-4 p-5 md:grid-cols-2">
        {(
          [
            ["capital_available_usd", "Capital I can deploy ($)", "number"],
            ["min_acres", "Minimum acres", "number"],
            ["max_price_usd", "Maximum price ($)", "number"],
            ["min_target_irr", "Minimum target IRR (0.12 = 12%)", "number"],
            ["target_hold_years_min", "Hold years (min)", "number"],
            ["target_hold_years_max", "Hold years (max)", "number"],
            ["risk_tolerance", "Risk tolerance (0–100)", "number"],
          ] as const
        ).map(([key, label]) => (
          <label key={key} className="text-xs uppercase tracking-wide text-[var(--muted)]">
            {label}
            <input
              className="mt-1 w-full rounded-xl border border-[var(--line)] bg-transparent px-3 py-2 text-sm normal-case text-[var(--ink)]"
              value={String(profile[key] ?? "")}
              onChange={(e) => setProfile({ ...profile, [key]: e.target.value })}
            />
          </label>
        ))}
      </section>

      <section className="panel p-5">
        <h2 className="display text-xl font-semibold">Preferred strategies</h2>
        <p className="mt-1 text-sm text-[var(--muted)]">Tap to toggle. Leave all off for “any strategy.”</p>
        <div className="mt-3 flex flex-wrap gap-2">
          {STRATEGIES.map((s) => (
            <button
              key={s}
              type="button"
              className={`rounded-full px-3 py-1.5 text-sm border ${
                preferred.has(s)
                  ? "bg-[var(--brand)] text-white border-[var(--brand)]"
                  : "border-[var(--line)]"
              }`}
              onClick={() => toggleStrategy(s)}
            >
              {s.replaceAll("_", " ")}
            </button>
          ))}
        </div>
      </section>

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className="btn btn-dark"
          onClick={async () => {
            setError("");
            setSaved(false);
            try {
              const body = {
                ...profile,
                capital_available_usd: Number(profile.capital_available_usd),
                min_acres: Number(profile.min_acres),
                max_price_usd: Number(profile.max_price_usd),
                min_target_irr: Number(profile.min_target_irr),
                target_hold_years_min: Number(profile.target_hold_years_min || 0) || undefined,
                target_hold_years_max: Number(profile.target_hold_years_max || 0) || undefined,
                risk_tolerance: String(profile.risk_tolerance ?? "MODERATE"),
              };
              await landsignalApi.updateProfile(body);
              setSaved(true);
            } catch (e) {
              setError(e instanceof Error ? e.message : "Save failed");
            }
          }}
        >
          Save my criteria
        </button>
        <button
          type="button"
          className="btn btn-ghost"
          onClick={() =>
            setProfile({
              ...profile,
              capital_available_usd: 500000,
              min_acres: 20,
              max_price_usd: 1500000,
              min_target_irr: 0.12,
              target_hold_years_min: 5,
              target_hold_years_max: 15,
              risk_tolerance: 45,
              preferred_strategies: ["FARMLAND", "LAND_BANK"],
            })
          }
        >
          Load balanced investor preset
        </button>
      </div>
      {saved && (
        <div className="text-sm text-[var(--positive)]">
          Saved. Return to Search and click Show matches to re-rank Fit.
        </div>
      )}
      {error && <div className="text-sm text-[var(--danger)]">{error}</div>}
    </div>
  );
}
