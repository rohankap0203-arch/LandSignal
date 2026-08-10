"""Nationwide geography metadata for search filters."""

from __future__ import annotations

US_STATES: list[dict[str, str]] = [
    {"code": "AL", "name": "Alabama"},
    {"code": "AK", "name": "Alaska"},
    {"code": "AZ", "name": "Arizona"},
    {"code": "AR", "name": "Arkansas"},
    {"code": "CA", "name": "California"},
    {"code": "CO", "name": "Colorado"},
    {"code": "CT", "name": "Connecticut"},
    {"code": "DE", "name": "Delaware"},
    {"code": "FL", "name": "Florida"},
    {"code": "GA", "name": "Georgia"},
    {"code": "HI", "name": "Hawaii"},
    {"code": "ID", "name": "Idaho"},
    {"code": "IL", "name": "Illinois"},
    {"code": "IN", "name": "Indiana"},
    {"code": "IA", "name": "Iowa"},
    {"code": "KS", "name": "Kansas"},
    {"code": "KY", "name": "Kentucky"},
    {"code": "LA", "name": "Louisiana"},
    {"code": "ME", "name": "Maine"},
    {"code": "MD", "name": "Maryland"},
    {"code": "MA", "name": "Massachusetts"},
    {"code": "MI", "name": "Michigan"},
    {"code": "MN", "name": "Minnesota"},
    {"code": "MS", "name": "Mississippi"},
    {"code": "MO", "name": "Missouri"},
    {"code": "MT", "name": "Montana"},
    {"code": "NE", "name": "Nebraska"},
    {"code": "NV", "name": "Nevada"},
    {"code": "NH", "name": "New Hampshire"},
    {"code": "NJ", "name": "New Jersey"},
    {"code": "NM", "name": "New Mexico"},
    {"code": "NY", "name": "New York"},
    {"code": "NC", "name": "North Carolina"},
    {"code": "ND", "name": "North Dakota"},
    {"code": "OH", "name": "Ohio"},
    {"code": "OK", "name": "Oklahoma"},
    {"code": "OR", "name": "Oregon"},
    {"code": "PA", "name": "Pennsylvania"},
    {"code": "RI", "name": "Rhode Island"},
    {"code": "SC", "name": "South Carolina"},
    {"code": "SD", "name": "South Dakota"},
    {"code": "TN", "name": "Tennessee"},
    {"code": "TX", "name": "Texas"},
    {"code": "UT", "name": "Utah"},
    {"code": "VT", "name": "Vermont"},
    {"code": "VA", "name": "Virginia"},
    {"code": "WA", "name": "Washington"},
    {"code": "WV", "name": "West Virginia"},
    {"code": "WI", "name": "Wisconsin"},
    {"code": "WY", "name": "Wyoming"},
    {"code": "DC", "name": "District of Columbia"},
]

# Macro regions / metro corridors investors commonly underwrite
STATE_REGIONS: dict[str, list[str]] = {
    "AL": ["Any", "Birmingham metro", "Huntsville / North Alabama", "Mobile / Gulf Coast", "Montgomery", "Black Belt farmland", "Wiregrass"],
    "AK": ["Any", "Anchorage bowl", "Mat-Su", "Fairbanks / Interior", "Kenai Peninsula", "Southeast Alaska"],
    "AZ": ["Any", "Phoenix metro edge", "Tucson corridor", "Prescott / Central", "Flagstaff / North", "Yuma / Colorado River", "Mohave / Lake Havasu", "Cochise / Southeast"],
    "AR": ["Any", "Northwest Arkansas", "Central Arkansas", "Delta farmland", "Ozarks", "South Arkansas timber"],
    "CA": ["Any", "Central Valley", "Inland Empire", "Sacramento Valley", "Bay Area fringe", "Southern California desert", "North Coast", "San Joaquin Valley", "Shasta / Far North"],
    "CO": ["Any", "Front Range", "Denver metro edge", "Colorado Springs", "Western Slope", "Eastern Plains farmland", "I-70 mountain corridor"],
    "CT": ["Any", "Fairfield County", "Hartford metro", "New Haven", "Eastern Connecticut", "Litchfield Hills"],
    "DE": ["Any", "New Castle", "Kent", "Sussex / Beach corridor"],
    "FL": ["Any", "North Florida", "Central Florida", "Tampa Bay", "Orlando corridor", "South Florida", "Panhandle", "Treasure Coast", "Southwest Florida"],
    "GA": ["Any", "Atlanta metro edge", "North Georgia", "Coastal Georgia", "South Georgia farmland", "Augusta / CSRA", "Columbus"],
    "HI": ["Any", "Oahu", "Maui", "Big Island", "Kauai"],
    "ID": ["Any", "Treasure Valley", "Eastern Idaho", "North Idaho", "Magic Valley", "Idaho Falls corridor"],
    "IL": ["Any", "Chicago metro fringe", "Northern Illinois", "Central Illinois farmland", "Southern Illinois", "Quad Cities", "St. Louis Metro East"],
    "IN": ["Any", "Indianapolis metro", "Northern Indiana", "Southern Indiana", "Fort Wayne", "Evansville", "Farm belt counties"],
    "IA": ["Any", "Central Iowa", "Eastern Iowa", "Western Iowa", "Des Moines metro edge", "Siouxland"],
    "KS": ["Any", "Eastern Kansas", "Flint Hills", "Western High Plains", "Wichita metro", "Kansas City metro KS"],
    "KY": ["Any", "Bluegrass", "Louisville metro", "Northern Kentucky", "Western Kentucky", "Eastern Kentucky / Appalachia"],
    "LA": ["Any", "South Louisiana", "North Louisiana", "Baton Rouge corridor", "New Orleans metro edge", "Acadiana"],
    "ME": ["Any", "Southern Maine", "Midcoast", "Central Maine", "Northern Maine timber", "Portland metro edge"],
    "MD": ["Any", "Baltimore metro", "DC suburbs MD", "Eastern Shore", "Western Maryland", "Southern Maryland"],
    "MA": ["Any", "Greater Boston fringe", "Central Massachusetts", "Western Massachusetts", "Cape & Islands", "North Shore", "South Shore"],
    "MI": ["Any", "Southeast Michigan", "West Michigan", "Northern Lower Peninsula", "Upper Peninsula", "Grand Rapids corridor"],
    "MN": ["Any", "Twin Cities fringe", "Southern Minnesota farmland", "Central Minnesota", "Northern Minnesota", "Iron Range"],
    "MS": ["Any", "Delta farmland", "Jackson metro", "Gulf Coast", "Northeast Mississippi", "Pine Belt"],
    "MO": ["Any", "Kansas City metro MO", "St. Louis metro MO", "Ozarks", "Northern Missouri farmland", "Bootheel"],
    "MT": ["Any", "Western Montana", "Gallatin / Bozeman", "Billings / Yellowstone", "Hi-Line", "Missoula corridor"],
    "NE": ["Any", "Eastern Nebraska", "Sandhills", "Panhandle", "Omaha / Lincoln fringe", "Central Platte"],
    "NV": ["Any", "Las Vegas valley edge", "Reno / Sparks", "Northern Nevada", "Rural basins", "Southern Nevada public lands"],
    "NH": ["Any", "Seacoast", "Southern New Hampshire", "Lakes Region", "White Mountains", "Upper Valley"],
    "NJ": ["Any", "North Jersey", "Central Jersey", "South Jersey", "Shore counties", "Pinelands"],
    "NM": ["Any", "Albuquerque metro", "Santa Fe / North Central", "Southern New Mexico", "Eastern plains", "Farmington / NW"],
    "NY": ["Any", "Hudson Valley", "Upstate farmland", "Finger Lakes", "Capital Region", "Western New York", "North Country", "NYC metro fringe"],
    "NC": ["Any", "Research Triangle", "Charlotte metro", "Piedmont", "Coastal Plain", "Mountains / Asheville", "Wilmington corridor"],
    "ND": ["Any", "Red River Valley", "Missouri Slope", "Bakken / West", "Central Dakota", "Fargo metro edge"],
    "OH": ["Any", "Central Ohio", "Northeast Ohio", "Southwest Ohio", "Northwest Ohio farmland", "Appalachian Ohio"],
    "OK": ["Any", "Oklahoma City metro", "Tulsa metro", "Western Oklahoma", "Eastern Oklahoma", "Panhandle"],
    "OR": ["Any", "Willamette Valley", "Portland metro edge", "Central Oregon", "Eastern Oregon", "Southern Oregon", "Coast"],
    "PA": ["Any", "Southeast Pennsylvania", "Pittsburgh metro", "Central Pennsylvania", "Poconos", "Northern Tier", "Lehigh Valley"],
    "RI": ["Any", "Providence metro", "South County", "East Bay", "Northern Rhode Island"],
    "SC": ["Any", "Upstate", "Midlands", "Lowcountry", "Grand Strand", "Pee Dee"],
    "SD": ["Any", "Eastern South Dakota", "Black Hills", "Missouri River", "West River ranchland", "Sioux Falls metro edge"],
    "TN": ["Any", "Middle Tennessee", "East Tennessee", "West Tennessee", "Nashville metro edge", "Memphis metro", "Tri-Cities"],
    "TX": ["Any", "DFW metro edge", "Houston metro edge", "Austin / Central Texas", "San Antonio corridor", "Panhandle", "West Texas", "Rio Grande Valley", "East Texas timber", "Hill Country"],
    "UT": ["Any", "Wasatch Front", "Northern Utah", "Southern Utah", "Uintah Basin", "St. George corridor"],
    "VT": ["Any", "Champlain Valley", "Central Vermont", "Northeast Kingdom", "Southern Vermont"],
    "VA": ["Any", "Northern Virginia", "Richmond metro", "Hampton Roads", "Shenandoah Valley", "Southwest Virginia", "Southside"],
    "WA": ["Any", "Puget Sound", "Seattle metro edge", "Eastern Washington farmland", "Olympic Peninsula", "Southwest Washington", "Spokane corridor"],
    "WV": ["Any", "Northern Panhandle", "Eastern Panhandle", "Kanawha Valley", "Southern coalfields", "North Central"],
    "WI": ["Any", "Southern Wisconsin", "Driftless Area", "Central Sands", "Northwoods", "Milwaukee / Madison fringe", "Sauk / Baraboo"],
    "WY": ["Any", "Front Range WY", "Energy corridor", "Northwest Wyoming", "Central Wyoming", "Eastern plains"],
    "DC": ["Any", "District-wide"],
}


# Soft-match tokens so macro regions can still hit inventory counties/titles
REGION_MATCH_TOKENS: dict[str, list[str]] = {
    "sun belt growth corridors": ["fl", "tx", "az", "ga", "nc", "sc", "nv", "tn"],
    "midwest farmland belt": ["ia", "il", "in", "ne", "mn", "wi", "mo", "oh", "ks", "sd", "nd"],
    "intermountain west": ["co", "ut", "id", "mt", "wy", "nm", "nv"],
    "pacific northwest": ["wa", "or", "id"],
    "southeast timber & ag": ["ga", "al", "ms", "sc", "nc", "ar", "la", "tn"],
    "texas triangle fringe": ["tx", "dallas", "houston", "austin", "san antonio"],
    "california central valley": ["ca", "fresno", "kern", "tulare", "merced", "san joaquin", "shasta"],
    "desert southwest energy lands": ["az", "nm", "nv", "ut", "ca"],
    "great plains": ["ks", "ne", "ok", "sd", "nd", "mt", "wy", "co", "tx"],
    "northeast exurbs": ["ny", "pa", "nj", "ct", "ma", "nh", "vt", "me", "ri", "md"],
    "central valley": ["central", "san joaquin", "sacramento", "fresno", "kern", "tulare", "merced", "shasta"],
    "shasta / far north": ["shasta", "redding", "siskiyou", "tehama", "trinity"],
    "indianapolis metro": ["marion", "indianapolis", "hamilton", "hancock"],
    "southern wisconsin": ["sauk", "dane", "rock", "jefferson", "columbia"],
    "sauk / baraboo": ["sauk", "baraboo"],
    "driftless area": ["sauk", "vernon", "crawford", "grant", "la crosse"],
    "research triangle": ["wake", "durham", "orange", "brunswick"],
    "coastal plain": ["brunswick", "new hanover", "pender", "onslow"],
}


def regions_for_state(state_code: str | None) -> list[str]:
    if not state_code or state_code.upper() in ("ANY", ""):
        # National macro regions
        return [
            "Any",
            "Sun Belt growth corridors",
            "Midwest farmland belt",
            "Intermountain West",
            "Pacific Northwest",
            "Southeast timber & ag",
            "Texas triangle fringe",
            "California Central Valley",
            "Desert Southwest energy lands",
            "Great Plains",
            "Northeast exurbs",
        ]
    return STATE_REGIONS.get(
        state_code.upper(),
        ["Any", "Statewide", "Metro edge", "Rural counties", "Coastal", "Mountain / highland"],
    )


def region_matches(
    *,
    region: str | None,
    state: str | None,
    county: str | None,
    title: str | None,
) -> bool:
    if not region or region.lower() in ("any", ""):
        return True
    needle = region.lower().strip()
    hay = f"{county or ''} {state or ''} {title or ''}".lower()
    if needle in hay:
        return True
    token = needle.replace(" county", "").strip()
    if token and token in hay:
        return True
    # Macro alias tokens
    aliases = REGION_MATCH_TOKENS.get(needle, [])
    for a in aliases:
        if a in hay or a == (state or "").lower():
            return True
    # Word overlap (e.g. "Phoenix metro edge" vs county names later)
    words = [w for w in needle.replace("/", " ").replace("-", " ").split() if len(w) > 3 and w not in ("metro", "edge", "fringe", "corridor", "region", "area", "county")]
    return any(w in hay for w in words)


def search_meta_payload(inventory_regions: list[str] | None = None) -> dict:
    """Canonical filter catalog — not limited to current inventory."""
    states = ["Any", *[f"{s['code']} — {s['name']}" for s in US_STATES]]
    regions_by_state = {s["code"]: regions_for_state(s["code"]) for s in US_STATES}
    regions_by_state["Any"] = regions_for_state(None)
    live_regions = ["Any", *(inventory_regions or [])]
    return {
        "states": states,
        "state_codes": ["Any", *[s["code"] for s in US_STATES]],
        "regions": live_regions,
        "regions_by_state": regions_by_state,
        "strategies": [
            "Any",
            "FARMLAND",
            "DEVELOPMENT",
            "LAND_BANK",
            "RECREATIONAL",
            "ENERGY",
            "TIMBER",
            "CUSTOM",
        ],
        "hold_years": ["Any", 1, 3, 5, 10, 15, 25, 40, 60, 80, 100],
        "max_risk": ["Any", 20, 30, 40, 45, 50, 60, 70, 80],
        "min_confidence": ["Any", 25, 35, 40, 50, 55, 65, 70, 80],
        # Open-ended bands ("Up to" / "N+") keep the search engine flexible —
        # closed ranges were too brittle and dropped near-miss inventory.
        "price_presets": [
            {"label": "Any", "min": None, "max": None},
            {"label": "≤ $10k", "min": None, "max": 10000},
            {"label": "≤ $25k", "min": None, "max": 25000},
            {"label": "≤ $50k", "min": None, "max": 50000},
            {"label": "≤ $100k", "min": None, "max": 100000},
            {"label": "≤ $150k", "min": None, "max": 150000},
            {"label": "≤ $250k", "min": None, "max": 250000},
            {"label": "≤ $500k", "min": None, "max": 500000},
            {"label": "≤ $1M", "min": None, "max": 1000000},
            {"label": "≤ $2.5M", "min": None, "max": 2500000},
            {"label": "≤ $5M", "min": None, "max": 5000000},
            {"label": "$5M+", "min": 5000000, "max": None},
            {"label": "Custom…", "min": None, "max": None},
        ],
        "acre_presets": [
            {"label": "Any", "min": None, "max": None},
            {"label": "1+ ac", "min": 1, "max": None},
            {"label": "5+ ac", "min": 5, "max": None},
            {"label": "10+ ac", "min": 10, "max": None},
            {"label": "20+ ac", "min": 20, "max": None},
            {"label": "40+ ac", "min": 40, "max": None},
            {"label": "80+ ac", "min": 80, "max": None},
            {"label": "160+ ac", "min": 160, "max": None},
            {"label": "320+ ac", "min": 320, "max": None},
            {"label": "640+ ac", "min": 640, "max": None},
            {"label": "Custom range…", "min": None, "max": None},
        ],
        "market_channels": [
            {"value": "Any", "label": "Any market channel"},
            {"value": "blm_lpad", "label": "Federal BLM disposal"},
            {"value": "public_tax_sale", "label": "County tax sale"},
            {"value": "public_surplus", "label": "Public surplus"},
            {"value": "manual", "label": "Manual / private entry"},
            {"value": "priced_only", "label": "Priced listings only"},
        ],
        "unpriced_options": [
            {"value": "include", "label": "Include unpriced federal / surplus"},
            {"value": "priced", "label": "Priced / bids only"},
            {"value": "unpriced_only", "label": "Unpriced process parcels only"},
        ],
        "sort_options": [
            {"value": "fit_desc", "label": "Best match for my filters"},
            {"value": "score_desc", "label": "Highest opportunity score (0–100)"},
            {"value": "risk_asc", "label": "Lowest risk score first"},
            {"value": "confidence_desc", "label": "Most complete files first"},
            {"value": "price_asc", "label": "Lowest price / starting bid"},
            {"value": "price_desc", "label": "Highest price / starting bid"},
            {"value": "acres_desc", "label": "Largest acreage first"},
            {"value": "discount_asc", "label": "Biggest gap under our estimated value"},
        ],
        "tooltips": {
            "max_risk": {
                "title": "What is Max risk?",
                "body": "Risk is 0–100 from map checks (flood, wetlands, missing data, access). 0 is calm; 100 is rough. Cap it if you want safer-looking deals.",
            },
            "min_confidence": {
                "title": "What is Min confidence?",
                "body": "How complete the file is (maps, soils, flood, listing facts), 0–100. Higher means we verified more. Missing data lowers this on purpose — it does not invent a good score.",
            },
            "include_unpriced": {
                "title": "Unpriced federal / surplus?",
                "body": "Some public lands have no retail asking price. Include them if you want those process deals. Choose priced-only if you need a number today.",
            },
            "market_channel": {
                "title": "Market channel",
                "body": "Where the listing comes from: federal BLM land, county tax sale, government surplus, or a parcel you added yourself.",
            },
        },
        "allows_custom": [
            "price",
            "acres",
            "strategy",
            "hold_years",
            "max_risk",
            "min_confidence",
            "region",
            "state",
        ],
    }
