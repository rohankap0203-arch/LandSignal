export type NearbyKind =
  | "flood"
  | "wetland"
  | "water"
  | "road"
  | "highway"
  | "airport"
  | "railroad"
  | "power"
  | "electric"
  | "transmission"
  | "public_water"
  | "water_main"
  | "sewer"
  | "gas"
  | "fiber"
  | "substation"
  | "cell"
  | "wildfire"
  | "conservation"
  | "town"
  | "hospital"
  | "school"
  | "grocery"
  | "fire"
  | "police"
  | "park"
  | "employer"
  | "landfill"
  | "mine"
  | "prison"
  | "hazmat";

export type FilterCategoryId = "access" | "utilities" | "environment" | "services";

export type LandViewChip = {
  kind: NearbyKind;
  label: string;
  color: string;
  maxMiles: number;
  category: FilterCategoryId;
  measurementHint: string;
};

export type LandViewCategory = {
  id: FilterCategoryId;
  label: string;
  chips: LandViewChip[];
};

/** Categories default: Access + Environment expanded; Utilities + Services collapsed. */
export const LAND_VIEW_CATEGORY_DEFAULT_OPEN: Record<FilterCategoryId, boolean> = {
  access: true,
  environment: true,
  utilities: false,
  services: false,
};

const ACCESS_CHIPS: LandViewChip[] = [
  {
    kind: "road",
    label: "Paved road",
    color: "#a16207",
    maxMiles: 12,
    category: "access",
    measurementHint: "Nearest paved public road",
  },
  {
    kind: "highway",
    label: "Highway",
    color: "#92400e",
    maxMiles: 35,
    category: "access",
    measurementHint: "Nearest numbered highway / freeway",
  },
  {
    kind: "airport",
    label: "Airport",
    color: "#57534e",
    maxMiles: 60,
    category: "access",
    measurementHint: "Nearest public airport",
  },
  {
    kind: "railroad",
    label: "Railroad",
    color: "#44403c",
    maxMiles: 25,
    category: "access",
    measurementHint: "Nearest rail line",
  },
];

const UTILITIES_CHIPS: LandViewChip[] = [
  {
    kind: "electric",
    label: "Electric service",
    color: "#eab308",
    maxMiles: 18,
    category: "utilities",
    measurementHint: "Nearest distribution / service indication",
  },
  {
    kind: "transmission",
    label: "Transmission lines",
    color: "#ca8a04",
    maxMiles: 18,
    category: "utilities",
    measurementHint: "Nearest high-voltage transmission",
  },
  {
    kind: "water_main",
    label: "Public water",
    color: "#0284c7",
    maxMiles: 20,
    category: "utilities",
    measurementHint: "Nearest public water utility feature",
  },
  {
    kind: "sewer",
    label: "Public sewer",
    color: "#0f766e",
    maxMiles: 20,
    category: "utilities",
    measurementHint: "Nearest public sewer / treatment feature",
  },
  {
    kind: "gas",
    label: "Natural gas",
    color: "#c2410c",
    maxMiles: 20,
    category: "utilities",
    measurementHint: "Nearest gas infrastructure",
  },
  {
    kind: "fiber",
    label: "Internet / fiber",
    color: "#0369a1",
    maxMiles: 20,
    category: "utilities",
    measurementHint: "Nearest fiber / broadband node",
  },
  {
    kind: "substation",
    label: "Substation",
    color: "#a16207",
    maxMiles: 25,
    category: "utilities",
    measurementHint: "Nearest electrical substation",
  },
  {
    kind: "cell",
    label: "Cell tower",
    color: "#64748b",
    maxMiles: 25,
    category: "utilities",
    measurementHint: "Nearest cell / telecom tower",
  },
];

const ENVIRONMENT_CHIPS: LandViewChip[] = [
  {
    kind: "flood",
    label: "Flood zone",
    color: "#3b82f6",
    maxMiles: 15,
    category: "environment",
    measurementHint: "Nearest flood-prone / waterway screen",
  },
  {
    kind: "wetland",
    label: "Wetland",
    color: "#14b8a6",
    maxMiles: 18,
    category: "environment",
    measurementHint: "Nearest wetland feature",
  },
  {
    kind: "water",
    label: "Water body",
    color: "#0ea5e9",
    maxMiles: 18,
    category: "environment",
    measurementHint: "Nearest lake, pond, or reservoir",
  },
  {
    kind: "wildfire",
    label: "Wildfire risk",
    color: "#ea580c",
    maxMiles: 30,
    category: "environment",
    measurementHint: "Nearest wildfire hazard screen",
  },
  {
    kind: "conservation",
    label: "Conservation",
    color: "#15803d",
    maxMiles: 35,
    category: "environment",
    measurementHint: "Nearest conserved / protected land",
  },
];

const SERVICES_CHIPS: LandViewChip[] = [
  {
    kind: "town",
    label: "Town/services",
    color: "#b45309",
    maxMiles: 35,
    category: "services",
    measurementHint: "Nearest town or village center",
  },
  {
    kind: "hospital",
    label: "Hospital",
    color: "#dc2626",
    maxMiles: 50,
    category: "services",
    measurementHint: "Nearest hospital",
  },
  {
    kind: "school",
    label: "School",
    color: "#7c3aed",
    maxMiles: 25,
    category: "services",
    measurementHint: "Nearest school",
  },
  {
    kind: "grocery",
    label: "Grocery",
    color: "#65a30d",
    maxMiles: 30,
    category: "services",
    measurementHint: "Nearest grocery / supermarket",
  },
  {
    kind: "fire",
    label: "Fire station",
    color: "#b91c1c",
    maxMiles: 30,
    category: "services",
    measurementHint: "Nearest fire station",
  },
  {
    kind: "police",
    label: "Police",
    color: "#1e3a5f",
    maxMiles: 35,
    category: "services",
    measurementHint: "Nearest police station",
  },
  {
    kind: "park",
    label: "Park",
    color: "#16a34a",
    maxMiles: 25,
    category: "services",
    measurementHint: "Nearest park or recreation area",
  },
  {
    kind: "employer",
    label: "Employer",
    color: "#78716c",
    maxMiles: 40,
    category: "services",
    measurementHint: "Nearest major employment site",
  },
  {
    kind: "landfill",
    label: "Landfill",
    color: "#57534e",
    maxMiles: 40,
    category: "services",
    measurementHint: "Nearest landfill / waste site",
  },
  {
    kind: "mine",
    label: "Mine",
    color: "#854d0e",
    maxMiles: 40,
    category: "services",
    measurementHint: "Nearest mine or quarry",
  },
  {
    kind: "prison",
    label: "Prison",
    color: "#3f3f46",
    maxMiles: 50,
    category: "services",
    measurementHint: "Nearest prison / detention facility",
  },
  {
    kind: "hazmat",
    label: "Hazmat",
    color: "#b45309",
    maxMiles: 30,
    category: "services",
    measurementHint: "Nearest hazardous materials site",
  },
];

export const LAND_VIEW_CATEGORIES: LandViewCategory[] = [
  { id: "access", label: "Access", chips: ACCESS_CHIPS },
  { id: "utilities", label: "Utilities", chips: UTILITIES_CHIPS },
  { id: "environment", label: "Environment", chips: ENVIRONMENT_CHIPS },
  { id: "services", label: "Services & risks", chips: SERVICES_CHIPS },
];

export const LAND_VIEW_CHIPS: LandViewChip[] = LAND_VIEW_CATEGORIES.flatMap((c) => c.chips);

export function chipByKind(kind: NearbyKind): LandViewChip | undefined {
  return LAND_VIEW_CHIPS.find((c) => c.kind === kind);
}
