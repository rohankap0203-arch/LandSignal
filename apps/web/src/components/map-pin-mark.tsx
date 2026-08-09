/** Brand map-pin logo from the provided asset. Color via currentColor + CSS mask. */
export function MapPinMark({ className }: { className?: string }) {
  return <span className={["map-pin-asset", className].filter(Boolean).join(" ")} aria-hidden />;
}
