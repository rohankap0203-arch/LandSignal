import type { ProvenancedNumber, ScreenResult, ScoreInput, Strategy } from "./types.js";

function num(p: ProvenancedNumber): number | null {
  if (p.knowledge_state === "UNKNOWN" || p.knowledge_state === "TEMPORARILY_UNAVAILABLE") {
    return null;
  }
  return p.value;
}

export function screenStrategies(
  input: ScoreInput,
): Record<Strategy, ScreenResult> {
  const wetland = num(input.wetland_pct);
  const flood = num(input.flood_zone_pct);
  const maxSlope = num(input.max_slope_pct);
  const access = num(input.legal_access_confidence);
  const contamination = num(input.environmental_contamination);
  const acreage = input.acreage;

  const landlocked =
    access != null && access < 15
      ? "FAIL"
      : access != null && access < 40
        ? "MANUAL_REVIEW"
        : "PASS";

  const farmland: ScreenResult =
    wetland != null && wetland > 60
      ? "FAIL"
      : maxSlope != null && maxSlope > 25
        ? "FAIL"
        : landlocked === "FAIL"
          ? "MANUAL_REVIEW"
          : "PASS";

  const development: ScreenResult =
    landlocked === "FAIL"
      ? "FAIL"
      : wetland != null && wetland > 40
        ? "FAIL"
        : flood != null && flood > 50
          ? "FAIL"
          : contamination != null && contamination >= 70
            ? "FAIL"
            : acreage != null && acreage < 2
              ? "FAIL"
              : wetland != null && wetland > 20
                ? "MANUAL_REVIEW"
                : landlocked === "MANUAL_REVIEW"
                  ? "MANUAL_REVIEW"
                  : "PASS";

  const recreational: ScreenResult =
    landlocked === "FAIL"
      ? "MANUAL_REVIEW"
      : contamination != null && contamination >= 80
        ? "FAIL"
        : "PASS";

  const energy: ScreenResult =
    acreage != null && acreage < 10
      ? "FAIL"
      : maxSlope != null && maxSlope > 20
        ? "FAIL"
        : wetland != null && wetland > 35
          ? "FAIL"
          : flood != null && flood > 40
            ? "MANUAL_REVIEW"
            : "PASS";

  const timber: ScreenResult =
    maxSlope != null && maxSlope > 45
      ? "MANUAL_REVIEW"
      : contamination != null && contamination >= 80
        ? "FAIL"
        : "PASS";

  const landBank: ScreenResult =
    landlocked === "FAIL"
      ? "FAIL"
      : contamination != null && contamination >= 85
        ? "FAIL"
        : landlocked === "MANUAL_REVIEW"
          ? "MANUAL_REVIEW"
          : "PASS";

  return {
    FARMLAND: farmland,
    DEVELOPMENT: development,
    LAND_BANK: landBank,
    RECREATIONAL: recreational,
    ENERGY: energy,
    TIMBER: timber,
  };
}
