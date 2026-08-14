"""Nationwide geography metadata for search filters."""

from __future__ import annotations

# Canonical 50-state (+ DC) catalog. Search must never depend on a hand-picked subset.
US_STATES: list[dict[str, str]] = [
    {"code": "AL", "name": "Alabama", "fips": "01"},
    {"code": "AK", "name": "Alaska", "fips": "02"},
    {"code": "AZ", "name": "Arizona", "fips": "04"},
    {"code": "AR", "name": "Arkansas", "fips": "05"},
    {"code": "CA", "name": "California", "fips": "06"},
    {"code": "CO", "name": "Colorado", "fips": "08"},
    {"code": "CT", "name": "Connecticut", "fips": "09"},
    {"code": "DE", "name": "Delaware", "fips": "10"},
    {"code": "FL", "name": "Florida", "fips": "12"},
    {"code": "GA", "name": "Georgia", "fips": "13"},
    {"code": "HI", "name": "Hawaii", "fips": "15"},
    {"code": "ID", "name": "Idaho", "fips": "16"},
    {"code": "IL", "name": "Illinois", "fips": "17"},
    {"code": "IN", "name": "Indiana", "fips": "18"},
    {"code": "IA", "name": "Iowa", "fips": "19"},
    {"code": "KS", "name": "Kansas", "fips": "20"},
    {"code": "KY", "name": "Kentucky", "fips": "21"},
    {"code": "LA", "name": "Louisiana", "fips": "22"},
    {"code": "ME", "name": "Maine", "fips": "23"},
    {"code": "MD", "name": "Maryland", "fips": "24"},
    {"code": "MA", "name": "Massachusetts", "fips": "25"},
    {"code": "MI", "name": "Michigan", "fips": "26"},
    {"code": "MN", "name": "Minnesota", "fips": "27"},
    {"code": "MS", "name": "Mississippi", "fips": "28"},
    {"code": "MO", "name": "Missouri", "fips": "29"},
    {"code": "MT", "name": "Montana", "fips": "30"},
    {"code": "NE", "name": "Nebraska", "fips": "31"},
    {"code": "NV", "name": "Nevada", "fips": "32"},
    {"code": "NH", "name": "New Hampshire", "fips": "33"},
    {"code": "NJ", "name": "New Jersey", "fips": "34"},
    {"code": "NM", "name": "New Mexico", "fips": "35"},
    {"code": "NY", "name": "New York", "fips": "36"},
    {"code": "NC", "name": "North Carolina", "fips": "37"},
    {"code": "ND", "name": "North Dakota", "fips": "38"},
    {"code": "OH", "name": "Ohio", "fips": "39"},
    {"code": "OK", "name": "Oklahoma", "fips": "40"},
    {"code": "OR", "name": "Oregon", "fips": "41"},
    {"code": "PA", "name": "Pennsylvania", "fips": "42"},
    {"code": "RI", "name": "Rhode Island", "fips": "44"},
    {"code": "SC", "name": "South Carolina", "fips": "45"},
    {"code": "SD", "name": "South Dakota", "fips": "46"},
    {"code": "TN", "name": "Tennessee", "fips": "47"},
    {"code": "TX", "name": "Texas", "fips": "48"},
    {"code": "UT", "name": "Utah", "fips": "49"},
    {"code": "VT", "name": "Vermont", "fips": "50"},
    {"code": "VA", "name": "Virginia", "fips": "51"},
    {"code": "WA", "name": "Washington", "fips": "53"},
    {"code": "WV", "name": "West Virginia", "fips": "54"},
    {"code": "WI", "name": "Wisconsin", "fips": "55"},
    {"code": "WY", "name": "Wyoming", "fips": "56"},
    {"code": "DC", "name": "District of Columbia", "fips": "11"},
]

# Macro regions / metro corridors investors commonly underwrite
STATE_REGIONS: dict[str, list[str]] = {
    "AL": ["Any", "Birmingham metro", "Huntsville / North Alabama", "Mobile / Gulf Coast", "Montgomery", "Black Belt farmland", "Wiregrass"],
    "AK": ["Any", "Anchorage bowl", "Mat-Su", "Fairbanks / Interior", "Kenai Peninsula", "Southeast Alaska"],
    "AZ": ["Any", "Phoenix metro edge", "Tucson corridor", "Prescott / Central", "Flagstaff / North", "Yuma / Colorado River", "Mohave / Lake Havasu", "Cochise / Southeast"],
    "AR": ["Any", "Northwest Arkansas", "Central Arkansas", "Delta farmland", "Ozarks", "South Arkansas timber"],
    "CA": [
        "Any",
        "Northern California",
        "Central California",
        "Southern California",
        "Central Valley",
        "Inland Empire",
        "Sacramento Valley",
        "Bay Area fringe",
        "Southern California desert",
        "North Coast",
        "San Joaquin Valley",
        "Shasta / Far North",
    ],
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
    "northern california": [
        "shasta", "siskiyou", "humboldt", "mendocino", "sonoma", "napa", "marin",
        "san francisco", "alameda", "contra costa", "sacramento", "placer", "nevada",
        "butte", "tehama", "trinity", "del norte", "plumas", "lassen", "modoc",
        "lake", "colusa", "yolo", "solano", "santa clara", "san mateo",
    ],
    "central california": [
        "fresno", "kern", "tulare", "merced", "san joaquin", "stanislaus", "madera",
        "kings", "monterey", "san luis obispo", "santa cruz", "san benito",
    ],
    "southern california": [
        "los angeles", "orange", "san diego", "riverside", "san bernardino",
        "ventura", "imperial", "santa barbara",
    ],
    "inland empire": ["riverside", "san bernardino"],
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
        "price_presets": [
            {"label": "Any", "min": None, "max": None},
            {"label": "Under $10k", "min": None, "max": 10000},
            {"label": "Under $25k", "min": None, "max": 25000},
            {"label": "Under $50k", "min": None, "max": 50000},
            {"label": "$50k–$100k", "min": 50000, "max": 100000},
            {"label": "$100k–$250k", "min": 100000, "max": 250000},
            {"label": "$250k–$500k", "min": 250000, "max": 500000},
            {"label": "$500k–$1M", "min": 500000, "max": 1000000},
            {"label": "$1M–$2.5M", "min": 1000000, "max": 2500000},
            {"label": "$2.5M–$5M", "min": 2500000, "max": 5000000},
            {"label": "$5M–$10M", "min": 5000000, "max": 10000000},
            {"label": "$10M+", "min": 10000000, "max": None},
            {"label": "Custom range…", "min": None, "max": None},
        ],
        "acre_presets": [
            {"label": "Any", "min": None, "max": None},
            {"label": "Under 1 ac", "min": None, "max": 1},
            {"label": "1–5 ac", "min": 1, "max": 5},
            {"label": "5–20 ac", "min": 5, "max": 20},
            {"label": "20–40 ac", "min": 20, "max": 40},
            {"label": "40–100 ac", "min": 40, "max": 100},
            {"label": "100–250 ac", "min": 100, "max": 250},
            {"label": "250–500 ac", "min": 250, "max": 500},
            {"label": "500–1,000 ac", "min": 500, "max": 1000},
            {"label": "1,000+ ac", "min": 1000, "max": None},
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
