/** Shared LandSignal contracts (keep in sync with OpenAPI / Pydantic models). */

export type KnowledgeState =
  | "KNOWN"
  | "UNKNOWN"
  | "ESTIMATED"
  | "NOT_APPLICABLE"
  | "TEMPORARILY_UNAVAILABLE";

export type ProviderStatus =
  | "CONFIGURED"
  | "NOT_CONFIGURED"
  | "DEGRADED"
  | "ERROR";

export type Signal = "EXCEPTIONAL" | "STRONG" | "WATCH" | "REJECT";
