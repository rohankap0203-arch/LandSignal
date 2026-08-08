export function SignalBadge({ signal }: { signal: string }) {
  const cls =
    signal === "EXCEPTIONAL"
      ? "exceptional"
      : signal === "STRONG"
        ? "strong"
        : signal === "REJECT"
          ? "reject"
          : "watch";
  const mark =
    signal === "EXCEPTIONAL"
      ? "◆"
      : signal === "STRONG"
        ? "●"
        : signal === "REJECT"
          ? "■"
          : "○";
  return (
    <span className={`badge ${cls}`}>
      <span aria-hidden>{mark}</span>
      {signal}
    </span>
  );
}
