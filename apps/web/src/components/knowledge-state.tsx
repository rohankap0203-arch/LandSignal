export function KnowledgeStateBadge({ state }: { state?: string | null }) {
  if (!state) return null;
  return <span className="ks">{state}</span>;
}

export function ProvenanceHint({
  source,
  retrievedAt,
  confidence,
}: {
  source?: string | null;
  retrievedAt?: string | null;
  confidence?: number | null;
}) {
  return (
    <span
      className="mono text-[10px] text-[var(--muted)]"
      title={`Source: ${source || "—"}\nRetrieved: ${retrievedAt || "—"}\nConfidence: ${confidence ?? "—"}`}
    >
      src:{source || "—"}
      {confidence != null ? ` · c${confidence}` : ""}
    </span>
  );
}
