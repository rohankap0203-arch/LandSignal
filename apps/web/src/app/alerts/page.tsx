"use client";

import { useEffect, useState } from "react";
import { landsignalApi } from "@/lib/api";

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<Record<string, unknown>[]>([]);
  const [msg, setMsg] = useState("");

  async function refresh() {
    setAlerts(await landsignalApi.alerts());
  }

  useEffect(() => {
    refresh().catch(() => setAlerts([]));
  }, []);

  async function createDefault() {
    await landsignalApi.createAlertRule({
      name: "High-conviction land signal",
      predicate: {
        opportunity_gt: 90,
        risk_lt: 30,
        confidence_gt: 80,
        asymmetry_gt: 85,
      },
      channels: ["IN_APP", "EMAIL", "SMS"],
    });
    setMsg("Rule created. EMAIL/SMS deliver as NOT_CONFIGURED without SMTP/Twilio secrets.");
    await refresh();
  }

  return (
    <div className="space-y-4">
      <div className="flex items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Alerts</h1>
          <p className="mt-1 text-sm text-[var(--muted)]">
            Signal rules evaluate after each analysis. Push/email/SMS require configured providers.
          </p>
        </div>
        <button type="button" className="panel px-3 py-2 text-sm" onClick={createDefault}>
          Create high-conviction rule
        </button>
      </div>
      {msg && <div className="panel p-3 text-sm text-[var(--warning)]">{msg}</div>}
      <div className="space-y-2">
        {alerts.map((a) => (
          <div key={String(a.id)} className="panel p-3 text-sm">
            <div className="flex justify-between gap-3">
              <strong>{String(a.title)}</strong>
              <span className="mono text-[var(--muted)]">{String(a.severity)}</span>
            </div>
            <pre className="mono mt-2 overflow-auto text-[11px] text-[var(--muted)]">
              {JSON.stringify(a.body, null, 2)}
            </pre>
            <div className="mt-2 text-xs text-[var(--muted)]">
              Channels: {((a.delivered_channels as string[]) || []).join(", ") || "—"}
            </div>
          </div>
        ))}
        {!alerts.length && <div className="text-sm text-[var(--muted)]">No alerts yet.</div>}
      </div>
    </div>
  );
}
