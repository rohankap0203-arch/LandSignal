const LABELS: Record<string, string> = {
  EXCEPTIONAL: "Top pick",
  STRONG: "Strong look",
  WATCH: "Worth watching",
  "WORTH WATCHING": "Worth watching",
  REJECT: "Pass for now",
  "PASS FOR NOW": "Pass for now",
  HIGH: "Strong interest",
  MEDIUM: "Moderate interest",
  "LOOK CLOSELY NOW": "Look closely now",
  "INVESTIGATE IMMEDIATELY": "Look closely now",
  "HIGH PRIORITY": "High priority",
  PASS: "Keep on the list",
  "KEEP ON THE LIST": "Keep on the list",
};

export function SignalBadge({ signal }: { signal: string }) {
  const key = (signal || "WATCH").toUpperCase();
  const cls =
    key === "EXCEPTIONAL" || key === "HIGH" || key === "HIGH PRIORITY" || key.includes("LOOK CLOSELY")
      ? "exceptional"
      : key === "STRONG" || key === "MEDIUM"
        ? "strong"
        : key === "REJECT" || key.includes("PASS FOR NOW")
          ? "reject"
          : "watch";
  return (
    <span className={`badge ${cls}`} title={`${key} · first-look rating for this listing`}>
      {LABELS[key] || signal}
    </span>
  );
}
