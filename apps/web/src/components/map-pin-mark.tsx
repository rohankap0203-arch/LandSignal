/** Brand map-pin logo from the provided asset file. */
export function MapPinMark({
  className,
  tone = "brand",
}: {
  className?: string;
  /** brand = tinted via currentColor mask; light = white PNG for dark surfaces */
  tone?: "brand" | "light";
}) {
  if (tone === "light") {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src="/brand/map-pin-logo-white.png"
        alt=""
        className={className}
        aria-hidden
        draggable={false}
      />
    );
  }
  return <span className={["map-pin-asset", className].filter(Boolean).join(" ")} aria-hidden />;
}
