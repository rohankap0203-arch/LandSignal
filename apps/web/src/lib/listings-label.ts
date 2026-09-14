/**
 * Inventory caption under Show matches.
 * - Unknown / still loading → empty string (UI shows a quiet ellipsis, not an error dash)
 * - Live count → plain localized number
 * - 500k+ → compact floor label ("500k+", "520k+", …)
 */
export const LISTINGS_DISPLAY_FLOOR = 500_000;

export function formatListingsLabel(count?: number | null): string {
  const n = Number(count);
  if (!Number.isFinite(n) || n <= 0) return "";
  if (n >= LISTINGS_DISPLAY_FLOOR) {
    if (n >= 1_000_000) {
      const millions = Math.floor(n / 100_000) / 10;
      return `${millions}M+`.replace(/\.0M\+/, "M+");
    }
    const rounded = Math.floor(n / 10_000) * 10_000;
    return `${Math.round(rounded / 1000)}k+`;
  }
  return Math.round(n).toLocaleString("en-US");
}
