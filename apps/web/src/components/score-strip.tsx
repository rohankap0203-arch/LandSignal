function Meter({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: number | null | undefined;
  tone?: "default" | "danger" | "accent";
}) {
  const color =
    tone === "danger" ? "var(--danger)" : tone === "accent" ? "var(--accent)" : "var(--positive)";
  const v = value ?? 0;
  return (
    <div className="panel p-3 min-w-[140px]">
      <div className="text-[11px] uppercase tracking-wide text-[var(--muted)]">{label}</div>
      <div className="mono mt-1 text-2xl" style={{ color }}>
        {value == null ? "—" : value.toFixed(0)}
        <span className="text-sm text-[var(--muted)]">/100</span>
      </div>
      <div className="mt-2 h-1 bg-[var(--border)]">
        <div className="h-1" style={{ width: `${Math.min(100, v)}%`, background: color }} />
      </div>
    </div>
  );
}

export function ScoreStrip({
  opportunity,
  risk,
  confidence,
  asymmetry,
  dealReadiness,
}: {
  opportunity?: number | null;
  risk?: number | null;
  confidence?: number | null;
  asymmetry?: number | null;
  dealReadiness?: number | null;
}) {
  return (
    <div className="flex flex-wrap gap-3">
      <Meter label="Opportunity" value={opportunity} tone="accent" />
      <Meter label="Risk" value={risk} tone="danger" />
      <Meter label="File complete" value={confidence} />
      <Meter label="Upside vs price" value={asymmetry} tone="accent" />
      <Meter label="Ready to pursue" value={dealReadiness} />
    </div>
  );
}
