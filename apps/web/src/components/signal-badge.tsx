export function SignalBadge({ signal }: { signal: string }) {
  const cls =
    signal === "EXCEPTIONAL"
      ? "exceptional"
      : signal === "STRONG"
        ? "strong"
        : signal === "REJECT"
          ? "reject"
          : "watch";
  return <span className={`badge ${cls}`}>{signal}</span>;
}
