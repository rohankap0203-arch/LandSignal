"use client";

import { useEffect, useState } from "react";
import { landsignalApi } from "@/lib/api";

export default function ProfilePage() {
  const [profile, setProfile] = useState<Record<string, unknown> | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    landsignalApi.profile().then(setProfile).catch(() => setProfile(null));
  }, []);

  if (!profile) return <div className="text-[var(--muted)]">Loading profile…</div>;

  return (
    <div className="max-w-2xl space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">Investor Profile</h1>
        <p className="mt-1 text-sm text-[var(--muted)]">
          Drives Personalized Score only. Global LandSignal Score remains mandate-agnostic.
        </p>
      </div>
      <div className="panel grid gap-3 p-4 md:grid-cols-2">
        {(
          [
            ["capital_available_usd", "Capital available"],
            ["min_acres", "Minimum acres"],
            ["max_price_usd", "Maximum price"],
            ["min_target_irr", "Minimum target IRR"],
            ["risk_tolerance", "Risk tolerance"],
          ] as const
        ).map(([key, label]) => (
          <label key={key} className="text-xs uppercase tracking-wide text-[var(--muted)]">
            {label}
            <input
              className="mt-1 w-full border border-[var(--border)] bg-transparent px-2 py-1.5 text-sm normal-case text-[var(--text)]"
              value={String(profile[key] ?? "")}
              onChange={(e) => setProfile({ ...profile, [key]: e.target.value })}
            />
          </label>
        ))}
      </div>
      <button
        type="button"
        className="panel px-4 py-2 text-sm"
        onClick={async () => {
          const body = {
            ...profile,
            capital_available_usd: Number(profile.capital_available_usd),
            min_acres: Number(profile.min_acres),
            max_price_usd: Number(profile.max_price_usd),
            min_target_irr: Number(profile.min_target_irr),
          };
          await landsignalApi.updateProfile(body);
          setSaved(true);
        }}
      >
        Save profile
      </button>
      {saved && <div className="text-sm text-[var(--positive)]">Saved. Re-analyze parcels to refresh personalized scores.</div>}
    </div>
  );
}
