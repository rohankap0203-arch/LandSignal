"use client";

import { useState } from "react";
import { landsignalApi } from "@/lib/api";

export default function IngestPage() {
  const [result, setResult] = useState<string>("");
  const [form, setForm] = useState({
    title: "",
    state: "IA",
    county: "",
    apn: "",
    acreage: "40",
    asking_price_usd: "250000",
    latitude: "41.5",
    longitude: "-93.5",
    description: "",
  });

  async function submitManual() {
    const body = {
      ...form,
      acreage: Number(form.acreage),
      asking_price_usd: Number(form.asking_price_usd),
      latitude: Number(form.latitude),
      longitude: Number(form.longitude),
    };
    const res = await landsignalApi.ingestManual(body);
    setResult(JSON.stringify(res, null, 2));
  }

  return (
    <div className="space-y-4 max-w-3xl">
      <div>
        <h1 className="text-2xl font-semibold">Ingest</h1>
        <p className="mt-1 text-sm text-[var(--muted)]">
          Manual parcel entry and CSV import. Licensed listing providers remain NOT_CONFIGURED until credentials
          and contracts are present.
        </p>
      </div>
      <div className="panel grid gap-3 p-4 md:grid-cols-2">
        {Object.entries(form).map(([key, value]) => (
          <label key={key} className="text-xs uppercase tracking-wide text-[var(--muted)]">
            {key}
            <input
              className="mt-1 w-full border border-[var(--border)] bg-transparent px-2 py-1.5 text-sm text-[var(--text)] normal-case"
              value={value}
              onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
            />
          </label>
        ))}
      </div>
      <button type="button" className="panel px-4 py-2 text-sm" onClick={submitManual}>
        Ingest & analyze
      </button>
      {result && <pre className="panel p-3 text-xs overflow-auto">{result}</pre>}
    </div>
  );
}
