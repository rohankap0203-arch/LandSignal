/** Marketing / product floor for the Show matches inventory caption. */
export const LISTINGS_DISPLAY_FLOOR = 500_000;

/**
 * Always show at least "500k+" under Show matches — never a smaller book size.
 * If live inventory climbs past the floor, round down to the nearest 10k with a k+ suffix.
 */
export function formatListingsLabel(count?: number | null): string {
  const n = Math.max(LISTINGS_DISPLAY_FLOOR, Number(count) || 0);
  if (n >= 1_000_000) {
    const millions = Math.floor(n / 100_000) / 10;
    return `${millions}M+`.replace(/\.0M\+/, "M+");
  }
  const rounded = Math.floor(n / 10_000) * 10_000;
  return `${Math.round(rounded / 1000)}k+`;
}
