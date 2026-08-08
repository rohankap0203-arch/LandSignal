import type { ProviderInfo } from "@/lib/api";

export function ProviderStrip({ providers }: { providers: ProviderInfo[] }) {
  return (
    <div className="panel flex flex-wrap gap-2 p-3">
      <span className="mr-2 text-[11px] uppercase tracking-wide text-[var(--muted)]">
        Integrations
      </span>
      {providers.map((p) => (
        <span
          key={p.id}
          className="mono text-[11px] border border-[var(--border)] px-2 py-1"
          title={p.detail || p.status}
          style={{
            color:
              p.status === "CONFIGURED"
                ? "var(--positive)"
                : p.status === "DEGRADED"
                  ? "var(--warning)"
                  : "var(--muted)",
          }}
        >
          {p.name}: {p.status}
        </span>
      ))}
    </div>
  );
}
