"""Where each parcel came from + how a buyer actually reaches the seller/office."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote_plus

# Concrete offices for feeds we ingest. Phones/URLs are public agency contacts.
# Keys: (provider_id, STATE, county_normalized) — county matched case-insensitive contains.
OFFICES: list[dict[str, Any]] = [
    {
        "provider_id": "public_tax_sale",
        "state": "IN",
        "county": "marion",
        "source_name": "Indianapolis / Marion County tax sale (public GIS)",
        "office": "Marion County Treasurer — Tax Sale",
        "website": "https://www.indy.gov/activity/property-tax-sale",
        "phone": "317-327-4040",
        "parcel_lookup": "https://maps.indy.gov/AssessorPropertyViewer/",
        "how": "Register for the county tax sale; bids start at the published minimum, not a retail ask.",
    },
    {
        "provider_id": "public_tax_sale",
        "state": "CA",
        "county": "shasta",
        "source_name": "Shasta County CA tax auction GIS",
        "office": "Shasta County Treasurer-Tax Collector",
        "website": "https://www.shastacounty.gov/treasurer-tax-collector",
        "phone": "530-225-5511",
        "parcel_lookup": "https://gis.shastacounty.gov/",
        "how": "Watch the Treasurer tax-auction calendar; minimum bid is on the county layer.",
    },
    {
        "provider_id": "public_tax_sale",
        "state": "WI",
        "county": "sauk",
        "source_name": "Sauk County WI parcels for sale GIS",
        "office": "Sauk County Land Records / Treasurer",
        "website": "https://lrs.co.sauk.wi.us/AscentLandRecords/",
        "phone": "608-355-3286",
        "parcel_lookup": "https://lrs.co.sauk.wi.us/AscentLandRecords/",
        "how": "County land-records GIS marks parcels offered for sale — contact Treasurer to bid/buy.",
    },
    {
        "provider_id": "public_tax_sale",
        "state": "KS",
        "county": "wyandotte",
        "source_name": "Wyandotte County / UG tax-sale eligible GIS",
        "office": "Unified Government of Wyandotte County Treasurer",
        "website": "https://www.wycokck.org/Departments/Treasury",
        "phone": "913-573-2821",
        "parcel_lookup": "https://gisweb.wycokck.org/",
        "how": "Tax-sale eligible layer — confirm current sale status with the Treasurer before bidding.",
    },
    {
        "provider_id": "public_tax_sale",
        "state": "OH",
        "county": "mahoning",
        "source_name": "Mahoning County OH delinquent / land-bank GIS",
        "office": "Mahoning County Treasurer / Land Bank",
        "website": "https://www.mahoningcountyoh.gov/",
        "phone": "330-740-2460",
        "parcel_lookup": "https://gisapp.mahoningcountyoh.gov/",
        "how": "Delinquent / land-bank inventory — call Treasurer or land bank for acquisition path.",
    },
    {
        "provider_id": "public_tax_sale",
        "state": "AZ",
        "county": "cochise",
        "source_name": "Cochise County AZ tax-lien parcel GIS",
        "office": "Cochise County Treasurer",
        "website": "https://www.cochise.az.gov/205/Treasurer",
        "phone": "520-432-8400",
        "parcel_lookup": "https://www.cochise.az.gov/",
        "how": "Tax-lien parcel layer — Treasurer runs lien/deed sales; verify year and status.",
    },
    {
        "provider_id": "public_tax_sale",
        "state": "GA",
        "county": "dekalb",
        "source_name": "DeKalb County GA delinquent parcel GIS",
        "office": "DeKalb County Tax Commissioner",
        "website": "https://www.dekalbtax.org/",
        "phone": "404-298-4000",
        "parcel_lookup": "https://www.dekalbtax.org/",
        "how": "Delinquent inventory — Tax Commissioner / tax sale calendar is the buy path.",
    },
    {
        "provider_id": "public_tax_sale",
        "state": "PA",
        "county": "allegheny",
        "source_name": "Allegheny County PA public parcel GIS",
        "office": "Allegheny County Real Estate / Treasurer",
        "website": "https://www.alleghenycounty.us/treasurer/index.aspx",
        "phone": "412-350-4100",
        "parcel_lookup": "https://www.alleghenycounty.us/real-estate/index.aspx",
        "how": "Public parcel screen (≥2 ac). Confirm if on upset/tax sale with Treasurer.",
    },
    {
        "provider_id": "public_tax_sale",
        "state": "MD",
        "county": "baltimore city",
        "source_name": "Baltimore City MD tax sale",
        "office": "Baltimore City Bureau of Revenue Collections — Tax Sale",
        "website": "https://www.baltimorecity.gov/tax-sale",
        "phone": "410-396-3000",
        "parcel_lookup": "https://taxsale.baltimorecity.gov/",
        "posting_url": "https://taxsale.baltimorecity.gov/",
        "how": "City tax-sale auction / lien certificates — Bureau of Revenue Collections runs the sale calendar.",
    },
    {
        "provider_id": "public_tax_sale",
        "state": "MD",
        "county": "baltimore",
        "source_name": "Baltimore City MD tax sale",
        "office": "Baltimore City Bureau of Revenue Collections — Tax Sale",
        "website": "https://www.baltimorecity.gov/tax-sale",
        "phone": "410-396-3000",
        "parcel_lookup": "https://taxsale.baltimorecity.gov/",
        "posting_url": "https://taxsale.baltimorecity.gov/",
        "how": "City tax-sale auction / lien certificates — Bureau of Revenue Collections runs the sale calendar.",
    },
    {
        "provider_id": "public_tax_sale",
        "state": "MN",
        "county": "ramsey",
        "source_name": "Ramsey County MN tax-forfeited public sales",
        "office": "Ramsey County Productive Properties — Tax-Forfeited Land",
        "website": "https://www.ramseycountymn.gov/residents/property-home/taxes-values/productive-properties/tax-forfeited-public-sales",
        "phone": "651-266-2080",
        "parcel_lookup": "https://www.ramseycountymn.gov/residents/property-home/taxes-values/productive-properties/tax-forfeited-public-sales",
        "how": "County tax-forfeited land auctions (often via MNBid) — call Productive Properties before you bid.",
    },
    {
        "provider_id": "public_tax_sale",
        "state": "MN",
        "county": "dakota",
        "source_name": "Dakota County MN tax-forfeited property",
        "office": "Dakota County Property Taxation / Tax-Forfeited Land",
        "website": "https://www.co.dakota.mn.us/HomeProperty/PropertyTaxes/Pages/default.aspx",
        "phone": "651-438-4576",
        "parcel_lookup": "https://gis.co.dakota.mn.us/",
        "how": "Tax-forfeited / delinquent inventory — Property Taxation confirms auction status and bid rules.",
    },
    {
        "provider_id": "public_vacant_gis",
        "state": "TX",
        "county": "dallas",
        "source_name": "Dallas CAD vacant tracts (public GIS)",
        "office": "Dallas Central Appraisal District",
        "website": "https://www.dallascad.org/",
        "phone": "214-631-0910",
        "parcel_lookup": "https://www.dallascad.org/",
        "how": "Vacant CAD map screen — look up the account for owner of record. Not a live tax-sale bid sheet.",
    },
    {
        "provider_id": "public_vacant_gis",
        "state": "TX",
        "county": "bexar",
        "source_name": "Bexar County CAD vacant land GIS",
        "office": "Bexar Appraisal District",
        "website": "https://www.bcad.org/",
        "phone": "210-242-2432",
        "parcel_lookup": "https://www.bcad.org/",
        "how": "Vacant CAD map screen — owner on account; confirm it’s actually obtainable before you chase.",
    },
    {
        "provider_id": "public_vacant_gis",
        "state": "WA",
        "county": "king",
        "source_name": "King County WA vacant property GIS",
        "office": "King County Department of Assessments",
        "website": "https://www.kingcounty.gov/depts/assessor.aspx",
        "phone": "206-296-7300",
        "parcel_lookup": "https://blue.kingcounty.com/Assessor/eRealProperty/default.aspx",
        "how": "Vacant map screen — look up PIN for owner/mailing. Don’t treat assessor GIS as a sale listing.",
    },
    {
        "provider_id": "public_vacant_gis",
        "state": "TN",
        "county": "davidson",
        "source_name": "Davidson County / Nashville vacant cadastral GIS",
        "office": "Metro Nashville Assessor of Property (PAD)",
        "website": "https://www.padctn.org/",
        "phone": "615-862-6080",
        "parcel_lookup": "https://www.padctn.org/",
        "posting_url": "https://www.padctn.org/",
        "how": (
            "Open PAD to look up this parcel ID / owner of record. This feed is vacant land on the "
            "public map — not a live tax-sale list. Ask whether it’s privately owned, metro-owned, "
            "or on a trustee sale calendar before you chase a bid."
        ),
    },
    {
        "provider_id": "public_vacant_gis",
        "state": "NJ",
        "county": "",
        "source_name": "New Jersey MOD-IV cadastral (NJOGIS)",
        "office": "New Jersey Office of GIS / local tax assessor",
        "website": "https://maps.nj.gov/",
        "phone": None,
        "parcel_lookup": "https://www.njparcels.com/",
        "how": (
            "Statewide MOD-IV vacant/farm map screen — look up the PIN with the municipal assessor. "
            "Not a live tax-sale calendar."
        ),
    },
    {
        "provider_id": "public_vacant_gis",
        "state": "NY",
        "county": "",
        "source_name": "NYS Tax Parcels Public (ORPTS / ITS Geospatial)",
        "office": "NYS Geospatial Services / local assessor",
        "website": "https://gis.ny.gov/parcels",
        "phone": "518-242-5029",
        "parcel_lookup": "https://gis.ny.gov/parcels",
        "how": (
            "Statewide ORPTS parcel screen for counties that authorize public share. "
            "Confirm owner of record with the local assessor — not a tax-sale list."
        ),
    },
    {
        "provider_id": "public_vacant_gis",
        "state": "AR",
        "county": "",
        "source_name": "Arkansas GeoStor CAMP parcels (AGISO)",
        "office": "Arkansas Geographic Information Office / county assessor",
        "website": "https://gis.arkansas.gov/",
        "phone": "501-682-2767",
        "parcel_lookup": "https://gis.arkansas.gov/",
        "how": (
            "Statewide CAMP cadastral polygons — coverage varies by county production block. "
            "Look up the parcel ID with the county assessor; not a confirmed sale."
        ),
    },
    {
        "provider_id": "public_vacant_gis",
        "state": "MA",
        "county": "",
        "source_name": "MassGIS Level-3 property tax parcels",
        "office": "MassGIS / local assessor",
        "website": "https://www.mass.gov/info-details/massgis-data-property-tax-parcels",
        "phone": None,
        "parcel_lookup": "https://www.mass.gov/info-details/massachusetts-interactive-property-map",
        "how": (
            "Statewide MassGIS assessor parcels (vacant / Chapter 61 screens). "
            "Confirm with the city/town assessor whether the owner will sell."
        ),
    },
    {
        "provider_id": "public_tax_sale",
        "state": "MI",
        "county": "wayne",
        "source_name": "Detroit Land Bank Authority inventory",
        "office": "Detroit Land Bank Authority",
        "website": "https://buildingdetroit.org/",
        "phone": "313-974-6869",
        "parcel_lookup": "https://buildingdetroit.org/properties/",
        "how": "DLBA for-sale / side-lot inventory — buy through buildingdetroit.org programs.",
    },
    {
        "provider_id": "public_tax_sale",
        "state": "UT",
        "county": "",
        "source_name": "Utah tax sale parcels (public ArcGIS)",
        "office": "County Treasurer (Utah tax sale)",
        "website": "https://tax.utah.gov/",
        "phone": "801-297-2200",
        "parcel_lookup": "https://www.utahcounty.gov/Dept/Assess/Index.asp",
        "posting_url": "https://tax.utah.gov/",
        "how": "Active tax-sale layer — call the county Treasurer on the parcel record for auction rules and deposit.",
    },
    {
        "provider_id": "public_tax_sale",
        "state": "IL",
        "county": "whiteside",
        "source_name": "Whiteside County IL tax foreclosure GIS",
        "office": "Whiteside County Treasurer",
        "website": "https://www.whiteside.org/treasurer/",
        "phone": "815-772-5196",
        "parcel_lookup": "https://www.whiteside.org/",
        "how": "Foreclosure / tax-parcel records — Treasurer for sale status and bidding.",
    },
    {
        "provider_id": "public_surplus",
        "state": "NC",
        "county": "brunswick",
        "source_name": "Brunswick County NC surplus property GIS",
        "office": "Brunswick County Surplus / Administration",
        "website": "https://www.brunswickcountync.gov/",
        "phone": "910-253-2000",
        "parcel_lookup": "https://www.brunswickcountync.gov/",
        "how": "County surplus layer — procurement / surplus office handles offers.",
    },
    {
        "provider_id": "public_surplus",
        "state": "FL",
        "county": "broward",
        "source_name": "Fort Lauderdale surplus property GIS",
        "office": "City of Fort Lauderdale Surplus Property",
        "website": "https://www.fortlauderdale.gov/",
        "phone": "954-828-5000",
        "parcel_lookup": "https://www.fortlauderdale.gov/",
        "how": "Municipal surplus — city real estate / surplus desk is the seller.",
    },
    {
        "provider_id": "public_surplus",
        "state": "VA",
        "county": "fairfax",
        "source_name": "Fairfax County VA large parcel GIS",
        "office": "Fairfax County Department of Tax Administration",
        "website": "https://www.fairfaxcounty.gov/taxes/",
        "phone": "703-222-8234",
        "parcel_lookup": "https://www.fairfaxcounty.gov/realestate/",
        "how": "Large-parcel screen from open data — look up PIN for owner; not a dedicated surplus sale.",
    },
    {
        "provider_id": "blm_lpad",
        "state": "",
        "county": "",
        "source_name": "BLM Lands Potentially Available for Disposal (LPAD)",
        "office": "Bureau of Land Management — Lands & Realty",
        "website": "https://www.blm.gov/programs/lands-and-realty/land-tenure",
        "phone": "202-208-3801",
        "parcel_lookup": "https://www.blm.gov/services/land-records",
        "how": "Federal disposal / sale-exchange under FLPMA — contact the BLM field office for the admin state.",
    },
]

BLM_STATE_OFFICES = {
    "AK": ("https://www.blm.gov/alaska", "907-271-5960"),
    "AZ": ("https://www.blm.gov/arizona", "602-417-9200"),
    "CA": ("https://www.blm.gov/california", "916-978-4400"),
    "CO": ("https://www.blm.gov/colorado", "303-239-3600"),
    "ID": ("https://www.blm.gov/idaho", "208-373-4000"),
    "MT": ("https://www.blm.gov/montana-dakotas", "406-896-5000"),
    "NM": ("https://www.blm.gov/new-mexico", "505-954-2000"),
    "NV": ("https://www.blm.gov/nevada", "775-861-6400"),
    "OR": ("https://www.blm.gov/oregon-washington", "503-808-6001"),
    "UT": ("https://www.blm.gov/utah", "801-539-4001"),
    "WY": ("https://www.blm.gov/wyoming", "307-775-6256"),
    "WA": ("https://www.blm.gov/oregon-washington", "503-808-6001"),
}

# State hubs used when a county-specific office isn't curated yet.
# Prefer real agency pages + public switchboard phones over Google search pages.
STATE_LAND_HUBS: dict[str, dict[str, str]] = {
    "MD": {
        "website": "https://dat.maryland.gov/pages/tax-sale-information.aspx",
        "phone": "410-767-4994",
        "office": "Maryland State Tax Sale Ombudsman / local collector",
        "parcel_lookup": "https://sdat.dat.maryland.gov/RealProperty/Pages/default.aspx",
    },
    "MN": {
        "website": "https://www.mnbid.mn.gov/",
        "phone": "651-201-2500",
        "office": "Minnesota tax-forfeited land (county + MNBid)",
        "parcel_lookup": "https://www.mnbid.mn.gov/",
    },
    "SC": {
        "website": "https://dor.sc.gov/",
        "phone": "803-898-5000",
        "office": "South Carolina Department of Revenue / county treasurer",
        "parcel_lookup": "https://dor.sc.gov/",
    },
    "NC": {
        "website": "https://www.ncdor.gov/",
        "phone": "877-252-3052",
        "office": "N.C. Department of Revenue / county tax office",
        "parcel_lookup": "https://www.ncdor.gov/",
    },
    "VA": {
        "website": "https://www.tax.virginia.gov/",
        "phone": "804-367-8031",
        "office": "Virginia Tax / local commissioner of the revenue",
        "parcel_lookup": "https://www.tax.virginia.gov/",
    },
    "GA": {
        "website": "https://dor.georgia.gov/",
        "phone": "877-423-6711",
        "office": "Georgia Department of Revenue / county tax commissioner",
        "parcel_lookup": "https://qpublic.schneidercorp.com/",
    },
    "FL": {
        "website": "https://floridarevenue.com/property/Pages/Home.aspx",
        "phone": "850-617-8600",
        "office": "Florida DOR Property Tax Oversight / county tax collector",
        "parcel_lookup": "https://floridarevenue.com/property/Pages/Home.aspx",
    },
    "TX": {
        "website": "https://comptroller.texas.gov/taxes/property-tax/",
        "phone": "800-252-9121",
        "office": "Texas Comptroller Property Tax Assistance / local CAD",
        "parcel_lookup": "https://comptroller.texas.gov/taxes/property-tax/",
    },
    "CA": {
        "website": "https://www.sco.ca.gov/ardtax_sale.html",
        "phone": "916-324-2829",
        "office": "California State Controller — Tax Sales / county tax collector",
        "parcel_lookup": "https://www.sco.ca.gov/ardtax_sale.html",
    },
    "NY": {
        "website": "https://www.tax.ny.gov/",
        "phone": "518-457-5431",
        "office": "NYS Tax / local assessor & county treasurer",
        "parcel_lookup": "https://gis.ny.gov/parcels",
    },
    "PA": {
        "website": "https://www.revenue.pa.gov/",
        "phone": "717-787-8201",
        "office": "Pennsylvania DOR / county treasurer tax sale",
        "parcel_lookup": "https://www.revenue.pa.gov/",
    },
    "OH": {
        "website": "https://tax.ohio.gov/",
        "phone": "800-282-1782",
        "office": "Ohio Department of Taxation / county auditor or treasurer",
        "parcel_lookup": "https://tax.ohio.gov/",
    },
    "IN": {
        "website": "https://www.in.gov/dlgf/",
        "phone": "317-232-3777",
        "office": "Indiana DLGF / county treasurer tax sale",
        "parcel_lookup": "https://www.in.gov/dlgf/",
    },
    "IL": {
        "website": "https://tax.illinois.gov/",
        "phone": "217-782-3336",
        "office": "Illinois Department of Revenue / county treasurer",
        "parcel_lookup": "https://tax.illinois.gov/",
    },
    "MI": {
        "website": "https://www.michigan.gov/taxes",
        "phone": "517-636-4486",
        "office": "Michigan Treasury / county treasurer or land bank",
        "parcel_lookup": "https://www.michigan.gov/taxes",
    },
    "WI": {
        "website": "https://www.revenue.wi.gov/",
        "phone": "608-266-2486",
        "office": "Wisconsin DOR / county treasurer",
        "parcel_lookup": "https://www.revenue.wi.gov/",
    },
    "NJ": {
        "website": "https://www.nj.gov/treasury/taxation/",
        "phone": "609-292-6400",
        "office": "NJ Division of Taxation / municipal tax collector",
        "parcel_lookup": "https://www.njparcels.com/",
    },
    "MA": {
        "website": "https://www.mass.gov/orgs/division-of-local-services",
        "phone": "617-626-2300",
        "office": "Mass. Division of Local Services / local assessor",
        "parcel_lookup": "https://www.mass.gov/info-details/massachusetts-interactive-property-map",
    },
    "AR": {
        "website": "https://www.dfa.arkansas.gov/",
        "phone": "501-682-7106",
        "office": "Arkansas DFA / county collector",
        "parcel_lookup": "https://gis.arkansas.gov/",
    },
    "TN": {
        "website": "https://www.tn.gov/revenue.html",
        "phone": "615-253-0600",
        "office": "Tennessee Department of Revenue / county trustee",
        "parcel_lookup": "https://www.padctn.org/",
    },
    "WA": {
        "website": "https://dor.wa.gov/",
        "phone": "360-705-6705",
        "office": "Washington DOR / county treasurer",
        "parcel_lookup": "https://dor.wa.gov/",
    },
    "UT": {
        "website": "https://tax.utah.gov/",
        "phone": "801-297-2200",
        "office": "Utah State Tax Commission / county treasurer",
        "parcel_lookup": "https://tax.utah.gov/",
    },
    "AZ": {
        "website": "https://azdor.gov/",
        "phone": "602-255-3381",
        "office": "Arizona DOR / county treasurer",
        "parcel_lookup": "https://azdor.gov/",
    },
    "CO": {
        "website": "https://tax.colorado.gov/",
        "phone": "303-238-7378",
        "office": "Colorado Department of Revenue / county treasurer",
        "parcel_lookup": "https://tax.colorado.gov/",
    },
    "OR": {
        "website": "https://www.oregon.gov/dor/",
        "phone": "503-378-4988",
        "office": "Oregon DOR / county tax collector",
        "parcel_lookup": "https://www.oregon.gov/dor/",
    },
    "NM": {
        "website": "https://www.tax.newmexico.gov/",
        "phone": "505-827-0700",
        "office": "New Mexico Taxation & Revenue / county treasurer",
        "parcel_lookup": "https://www.tax.newmexico.gov/",
    },
    "NV": {
        "website": "https://tax.nv.gov/",
        "phone": "775-684-2000",
        "office": "Nevada Department of Taxation / county treasurer",
        "parcel_lookup": "https://tax.nv.gov/",
    },
    "ID": {
        "website": "https://tax.idaho.gov/",
        "phone": "208-334-7660",
        "office": "Idaho State Tax Commission / county treasurer",
        "parcel_lookup": "https://tax.idaho.gov/",
    },
    "MT": {
        "website": "https://mtrevenue.gov/",
        "phone": "406-444-6900",
        "office": "Montana DOR / county treasurer",
        "parcel_lookup": "https://mtrevenue.gov/",
    },
    "WY": {
        "website": "https://www.wyoming.gov/agencies/department-of-revenue/",
        "phone": "307-777-7961",
        "office": "Wyoming Department of Revenue / county treasurer",
        "parcel_lookup": "https://wyo.gov/",
    },
    "AK": {
        "website": "https://tax.alaska.gov/",
        "phone": "907-269-6620",
        "office": "Alaska Tax Division / borough assessor",
        "parcel_lookup": "https://tax.alaska.gov/",
    },
    "AL": {
        "website": "https://www.revenue.alabama.gov/",
        "phone": "334-242-1170",
        "office": "Alabama DOR / county revenue commissioner",
        "parcel_lookup": "https://www.revenue.alabama.gov/",
    },
    "MS": {
        "website": "https://www.dor.ms.gov/",
        "phone": "601-923-7700",
        "office": "Mississippi DOR / county tax collector",
        "parcel_lookup": "https://www.dor.ms.gov/",
    },
    "LA": {
        "website": "https://www.revenue.louisiana.gov/",
        "phone": "855-307-3893",
        "office": "Louisiana Department of Revenue / parish sheriff tax sale",
        "parcel_lookup": "https://www.revenue.louisiana.gov/",
    },
    "MO": {
        "website": "https://dor.mo.gov/",
        "phone": "573-751-3505",
        "office": "Missouri DOR / county collector",
        "parcel_lookup": "https://dor.mo.gov/",
    },
    "KS": {
        "website": "https://www.ksrevenue.gov/",
        "phone": "785-368-8222",
        "office": "Kansas Department of Revenue / county treasurer",
        "parcel_lookup": "https://www.ksrevenue.gov/",
    },
    "NE": {
        "website": "https://revenue.nebraska.gov/",
        "phone": "402-471-5729",
        "office": "Nebraska Department of Revenue / county treasurer",
        "parcel_lookup": "https://revenue.nebraska.gov/",
    },
    "IA": {
        "website": "https://tax.iowa.gov/",
        "phone": "515-281-3114",
        "office": "Iowa Department of Revenue / county treasurer",
        "parcel_lookup": "https://tax.iowa.gov/",
    },
    "OK": {
        "website": "https://oklahoma.gov/tax.html",
        "phone": "405-521-3160",
        "office": "Oklahoma Tax Commission / county treasurer",
        "parcel_lookup": "https://oklahoma.gov/tax.html",
    },
    "CT": {
        "website": "https://portal.ct.gov/DRS",
        "phone": "860-297-5962",
        "office": "Connecticut DRS / municipal tax collector",
        "parcel_lookup": "https://portal.ct.gov/DRS",
    },
    "DE": {
        "website": "https://revenue.delaware.gov/",
        "phone": "302-577-8200",
        "office": "Delaware Division of Revenue / county tax office",
        "parcel_lookup": "https://revenue.delaware.gov/",
    },
    "WV": {
        "website": "https://tax.wv.gov/",
        "phone": "304-558-3333",
        "office": "West Virginia Tax Department / county sheriff",
        "parcel_lookup": "https://tax.wv.gov/",
    },
    "KY": {
        "website": "https://revenue.ky.gov/",
        "phone": "502-564-4581",
        "office": "Kentucky Department of Revenue / county PVA / sheriff",
        "parcel_lookup": "https://revenue.ky.gov/",
    },
    "ND": {
        "website": "https://www.tax.nd.gov/",
        "phone": "701-328-3127",
        "office": "North Dakota Tax Commissioner / county treasurer",
        "parcel_lookup": "https://www.tax.nd.gov/",
    },
    "SD": {
        "website": "https://dor.sd.gov/",
        "phone": "605-773-3311",
        "office": "South Dakota DOR / county treasurer",
        "parcel_lookup": "https://dor.sd.gov/",
    },
    "VT": {
        "website": "https://tax.vermont.gov/",
        "phone": "802-828-2865",
        "office": "Vermont Department of Taxes / town clerk / treasurer",
        "parcel_lookup": "https://tax.vermont.gov/",
    },
    "NH": {
        "website": "https://www.revenue.nh.gov/",
        "phone": "603-230-5000",
        "office": "New Hampshire DRA / municipal tax collector",
        "parcel_lookup": "https://www.revenue.nh.gov/",
    },
    "ME": {
        "website": "https://www.maine.gov/revenue/",
        "phone": "207-624-5600",
        "office": "Maine Revenue Services / municipal tax collector",
        "parcel_lookup": "https://www.maine.gov/revenue/",
    },
    "RI": {
        "website": "https://tax.ri.gov/",
        "phone": "401-574-8829",
        "office": "Rhode Island Division of Taxation / municipal collector",
        "parcel_lookup": "https://tax.ri.gov/",
    },
    "HI": {
        "website": "https://tax.hawaii.gov/",
        "phone": "808-587-4242",
        "office": "Hawaii Department of Taxation / county real property tax",
        "parcel_lookup": "https://tax.hawaii.gov/",
    },
    "DC": {
        "website": "https://otr.cfo.dc.gov/",
        "phone": "202-727-4829",
        "office": "DC Office of Tax and Revenue",
        "parcel_lookup": "https://otr.cfo.dc.gov/",
    },
}


def resolve_office(
    *,
    provider_id: str | None,
    state: str | None,
    county: str | None,
) -> dict[str, Any]:
    st = (state or "").upper()
    co = (county or "").lower()
    provider = provider_id or ""

    best = None
    for row in OFFICES:
        if row["provider_id"] != provider:
            continue
        if row["state"] and row["state"] != st:
            continue
        ckey = row.get("county") or ""
        if ckey and ckey not in co:
            continue
        best = row
        if ckey:
            break

    if best is None and provider == "blm_lpad":
        url, phone = BLM_STATE_OFFICES.get(st, ("https://www.blm.gov/programs/lands-and-realty/land-tenure", "202-208-3801"))
        best = {
            "provider_id": "blm_lpad",
            "state": st,
            "county": co,
            "source_name": f"BLM LPAD · {st or 'US'}",
            "office": f"BLM {st} State Office" if st else "BLM Lands & Realty",
            "website": url,
            "phone": phone,
            "parcel_lookup": "https://www.blm.gov/services/land-records",
            "how": "Federal disposal tract — field office confirms if/when it can be sold or exchanged.",
        }

    if best is None:
        hub = STATE_LAND_HUBS.get(st) if st else None
        if hub:
            place = f"{county.title()} County, {st}" if county else (st or "US")
            best = {
                "provider_id": provider,
                "state": st,
                "county": co,
                "source_name": f"Public land inventory · {place}",
                "office": (
                    f"{county.title()} County · {hub['office']}"
                    if county
                    else hub["office"]
                ),
                "website": hub["website"],
                "phone": hub.get("phone"),
                "parcel_lookup": hub.get("parcel_lookup") or hub["website"],
                "how": (
                    "Public inventory screen — confirm current sale / owner status with the "
                    "county treasurer, tax collector, or assessor before you bid."
                ),
            }
        else:
            q = quote_plus(f"{county or ''} {state or ''} property tax sale treasurer assessor".strip())
            best = {
                "provider_id": provider,
                "state": st,
                "county": co,
                "source_name": f"Public land inventory · {county or 'County'}, {st or 'US'}",
                "office": f"{county or 'County'} {st} Treasurer / Assessor".strip(),
                "website": f"https://www.google.com/search?q={q}",
                "phone": None,
                "parcel_lookup": (
                    "https://www.google.com/search?q="
                    + quote_plus((county or "") + " " + (st or "") + " parcel viewer assessor")
                ),
                "how": "Public GIS inventory — confirm sale status with the county Treasurer or Assessor.",
            }
    # Fill missing phone/website from the state hub when a county row is incomplete.
    if best and st:
        hub = STATE_LAND_HUBS.get(st)
        if hub:
            if not best.get("phone"):
                best["phone"] = hub.get("phone")
            if not best.get("website") or "google.com/search" in str(best.get("website") or ""):
                best["website"] = hub["website"]
            if not best.get("parcel_lookup") or "google.com/search" in str(best.get("parcel_lookup") or ""):
                best["parcel_lookup"] = hub.get("parcel_lookup") or hub["website"]
    return best


def _url_path_depth(url: str | None) -> int:
    if not url:
        return -1
    try:
        from urllib.parse import urlparse

        path = (urlparse(url).path or "").strip("/")
        if not path:
            return 0
        return path.count("/") + 1
    except Exception:
        return 0


_DEAD_PATH_MARKERS = (
    "/departments/assessor-property",
    "/real-property",  # utah tax.utah.gov/real-property 404
)


def _pick_posting_url(source_url: str | None, office: dict[str, Any]) -> str | None:
    """Prefer a concrete sale/office page over a bare or known-dead URL."""
    site = office.get("website")
    curated = office.get("posting_url") or site
    src = (source_url or "").strip() or None
    if not src:
        return curated
    low = src.lower()
    if any(m in low for m in _DEAD_PATH_MARKERS) and curated:
        return curated
    # Bare homepage on a GIS/tax-sale feed → curated office/PAD page is more useful
    if curated and _url_path_depth(src) <= 0 and office.get("provider_id") in (
        "public_tax_sale",
        "public_surplus",
        "blm_lpad",
        "public_vacant_gis",
    ):
        return curated
    if curated and _url_path_depth(src) <= 1 and _url_path_depth(curated) > _url_path_depth(src):
        return curated
    return src


def build_sourcing_bundle(
    *,
    provider_id: str | None,
    source_url: str | None,
    title: str,
    apn: str | None,
    state: str | None,
    county: str | None,
    latitude: float | None,
    longitude: float | None,
    raw: dict | None = None,
) -> dict[str, Any]:
    """Actionable links + office card for every parcel."""
    office = resolve_office(provider_id=provider_id, state=state, county=county)
    raw = raw or {}
    links: list[dict[str, Any]] = []

    # 1) Direct posting — ALWAYS a working http(s) destination for every parcel
    posting = _pick_posting_url(source_url, office)
    if not posting:
        posting = office.get("website") or (
            "https://www.google.com/search?q="
            + quote_plus(f"{county or ''} {state or ''} {office.get('office') or 'treasurer'} land sale".strip())
        )
    links.append(
        {
            "label": "Open posting",
            "url": posting,
            "kind": "primary",
            "guaranteed": True,
        }
    )

    # 2) Find this exact parcel (APN search is more useful than a bare GIS homepage)
    lookup = office.get("parcel_lookup")
    if apn:
        apn_q = (
            "https://www.google.com/search?q="
            + quote_plus(f"{apn} {county or ''} {state or ''} parcel assessor".strip())
        )
        links.append({"label": f"Find parcel {apn}", "url": apn_q, "kind": "lookup"})
        if lookup and lookup not in {posting, apn_q}:
            links.append({"label": "County parcel viewer", "url": lookup, "kind": "lookup"})
    elif lookup and lookup != posting:
        links.append({"label": "Parcel / assessor lookup", "url": lookup, "kind": "lookup"})

    # 3) Contact office (phone first — most useful)
    contact_url = office.get("website") or (
        f"https://www.google.com/search?q={quote_plus(office.get('office') or title)}"
    )
    phone = office.get("phone")
    if phone:
        links.append(
            {
                "label": phone,
                "url": f"tel:{phone.replace('-', '').replace(' ', '').replace('(', '').replace(')', '')}",
                "kind": "contact",
                "phone": phone,
            }
        )
    if contact_url and contact_url != posting:
        links.append(
            {
                "label": f"Office site · {office.get('office')}",
                "url": contact_url,
                "kind": "contact_web",
            }
        )
    elif not phone:
        links.append(
            {
                "label": f"Office site · {office.get('office')}",
                "url": contact_url,
                "kind": "contact",
            }
        )

    # 4) Map
    if latitude is not None and longitude is not None:
        links.append(
            {
                "label": "Map pin",
                "url": f"https://www.google.com/maps?q={latitude},{longitude}",
                "kind": "map",
            }
        )

    # Dedupe by URL, keep order, allow up to 6
    seen: set[str] = set()
    out_links = []
    for link in links:
        u = link["url"]
        if u in seen:
            continue
        seen.add(u)
        out_links.append(link)

    website = office.get("website") or posting
    # Hard guarantee: website is always a clickable http(s) URL
    if not website or not str(website).startswith("http"):
        website = (
            "https://www.google.com/search?q="
            + quote_plus(f"{county or ''} {state or ''} assessor treasurer tax sale".strip())
        )
        # Ensure primary also points somewhere real
        for link in out_links:
            if link.get("kind") == "primary":
                link["url"] = website
                break

    return {
        "source_name": office.get("source_name"),
        "office": office.get("office"),
        "website": website,
        "phone": phone,
        "how_to_buy": office.get("how"),
        "provider_id": provider_id,
        "links": out_links[:6],
        "contactable": True,
    }
