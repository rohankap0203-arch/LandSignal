const LABELS: Record<string, string> = {
  EXCEPTIONAL: "Top pick",
  STRONG: "Strong look",
  WATCH: "Worth watching",
  REJECT: "Pass for now",
  HIGH: "Strong interest",
  MEDIUM: "Moderate interest",
};

export function SignalBadge({ signal }: { signal: string }) {
  const key = (signal || "WATCH").toUpperCase();
  const cls =
    key === "EXCEPTIONAL" || key === "HIGH"
      ? "exceptional"
      : key === "STRONG" || key === "MEDIUM"
        ? "strong"
        : key === "REJECT"
          ? "reject"
          : "watch";
  return (
    <span className={`badge ${cls}`} title={`${key} · first-look rating for this listing`}>
      {LABELS[key] || signal}
    </span>
  );
}
