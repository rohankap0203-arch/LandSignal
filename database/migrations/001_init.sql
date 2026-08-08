-- LandSignal Phase 1 schema (PostgreSQL + PostGIS)
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE organizations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID REFERENCES organizations(id),
  email TEXT NOT NULL UNIQUE,
  display_name TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE investor_profiles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  capital_available_usd NUMERIC(18,2),
  min_acres NUMERIC(12,4),
  max_price_usd NUMERIC(18,2),
  target_hold_years_min INT,
  target_hold_years_max INT,
  min_target_irr NUMERIC(8,4),
  preferred_strategies TEXT[] NOT NULL DEFAULT '{}',
  risk_tolerance TEXT NOT NULL DEFAULT 'MODERATE',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE data_sources (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL, -- LISTING | ENRICHMENT | MARKET
  name TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'NOT_CONFIGURED',
  config JSONB NOT NULL DEFAULT '{}',
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE parcels (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID REFERENCES organizations(id),
  parcel_id TEXT, -- external/canonical
  apn TEXT,
  address TEXT,
  county TEXT,
  state CHAR(2),
  centroid GEOGRAPHY(POINT, 4326),
  boundary GEOGRAPHY(MULTIPOLYGON, 4326),
  acreage NUMERIC(14,4),
  geometry_confidence NUMERIC(5,2),
  land_use TEXT,
  zoning TEXT,
  future_land_use TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX parcels_boundary_gix ON parcels USING GIST (boundary);
CREATE INDEX parcels_centroid_gix ON parcels USING GIST (centroid);
CREATE INDEX parcels_state_county_idx ON parcels (state, county);

CREATE TABLE listings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  parcel_id UUID REFERENCES parcels(id) ON DELETE SET NULL,
  provider_id TEXT REFERENCES data_sources(id),
  external_id TEXT,
  status TEXT NOT NULL DEFAULT 'ACTIVE',
  asking_price_usd NUMERIC(18,2),
  price_per_acre_usd NUMERIC(18,2),
  listed_at TIMESTAMPTZ,
  last_seen_at TIMESTAMPTZ,
  days_on_market INT,
  title TEXT,
  description TEXT,
  source_url TEXT,
  raw JSONB NOT NULL DEFAULT '{}',
  is_demo BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (provider_id, external_id)
);

CREATE TABLE listing_history (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  listing_id UUID NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
  event_type TEXT NOT NULL,
  old_value JSONB,
  new_value JSONB,
  observed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE owners (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  parcel_id UUID NOT NULL REFERENCES parcels(id) ON DELETE CASCADE,
  name TEXT,
  entity_type TEXT,
  mailing_address TEXT,
  ownership_start DATE,
  is_absentee BOOLEAN,
  source TEXT,
  confidence NUMERIC(5,2),
  retrieved_at TIMESTAMPTZ,
  raw JSONB NOT NULL DEFAULT '{}'
);

CREATE TABLE transactions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  parcel_id UUID REFERENCES parcels(id),
  sale_date DATE,
  sale_price_usd NUMERIC(18,2),
  price_per_acre_usd NUMERIC(18,2),
  buyer TEXT,
  seller TEXT,
  arms_length_state TEXT NOT NULL DEFAULT 'UNKNOWN',
  source TEXT,
  confidence NUMERIC(5,2),
  retrieved_at TIMESTAMPTZ,
  geometry GEOGRAPHY(MULTIPOLYGON, 4326),
  raw JSONB NOT NULL DEFAULT '{}'
);

CREATE TABLE assessments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  parcel_id UUID NOT NULL REFERENCES parcels(id) ON DELETE CASCADE,
  tax_year INT,
  assessed_land_usd NUMERIC(18,2),
  assessed_total_usd NUMERIC(18,2),
  source TEXT,
  retrieved_at TIMESTAMPTZ,
  raw JSONB NOT NULL DEFAULT '{}'
);

CREATE TABLE tax_records (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  parcel_id UUID NOT NULL REFERENCES parcels(id) ON DELETE CASCADE,
  tax_year INT,
  amount_due_usd NUMERIC(18,2),
  amount_paid_usd NUMERIC(18,2),
  delinquent BOOLEAN,
  source TEXT,
  retrieved_at TIMESTAMPTZ,
  raw JSONB NOT NULL DEFAULT '{}'
);

CREATE TABLE zoning_records (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  parcel_id UUID NOT NULL REFERENCES parcels(id) ON DELETE CASCADE,
  zoning_code TEXT,
  zoning_description TEXT,
  min_lot_acres NUMERIC(12,4),
  allowable_density NUMERIC(12,4),
  future_land_use TEXT,
  knowledge_state TEXT NOT NULL DEFAULT 'UNKNOWN',
  source TEXT,
  confidence NUMERIC(5,2),
  retrieved_at TIMESTAMPTZ,
  raw JSONB NOT NULL DEFAULT '{}'
);

-- Provenanced metric tables share a pattern
CREATE TABLE soil_metrics (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  parcel_id UUID NOT NULL REFERENCES parcels(id) ON DELETE CASCADE,
  prime_farmland_pct NUMERIC(7,4),
  statewide_important_pct NUMERIC(7,4),
  nccpi NUMERIC(7,4),
  awc_mean NUMERIC(10,4),
  hydrologic_groups JSONB,
  soil_composition JSONB,
  farmland_classification TEXT,
  agricultural_quality_score NUMERIC(5,2),
  knowledge_state TEXT NOT NULL DEFAULT 'UNKNOWN',
  source TEXT,
  retrieved_at TIMESTAMPTZ,
  effective_date DATE,
  confidence NUMERIC(5,2),
  geographic_resolution TEXT,
  raw JSONB NOT NULL DEFAULT '{}',
  normalized JSONB NOT NULL DEFAULT '{}'
);

CREATE TABLE wetland_metrics (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  parcel_id UUID NOT NULL REFERENCES parcels(id) ON DELETE CASCADE,
  wetland_pct NUMERIC(7,4),
  wetland_acres NUMERIC(14,4),
  knowledge_state TEXT NOT NULL DEFAULT 'UNKNOWN',
  source TEXT,
  retrieved_at TIMESTAMPTZ,
  confidence NUMERIC(5,2),
  geographic_resolution TEXT,
  raw JSONB NOT NULL DEFAULT '{}',
  normalized JSONB NOT NULL DEFAULT '{}'
);

CREATE TABLE flood_metrics (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  parcel_id UUID NOT NULL REFERENCES parcels(id) ON DELETE CASCADE,
  flood_zone_pct NUMERIC(7,4),
  zone_breakdown JSONB,
  knowledge_state TEXT NOT NULL DEFAULT 'UNKNOWN',
  source TEXT,
  retrieved_at TIMESTAMPTZ,
  confidence NUMERIC(5,2),
  geographic_resolution TEXT,
  raw JSONB NOT NULL DEFAULT '{}',
  normalized JSONB NOT NULL DEFAULT '{}'
);

CREATE TABLE terrain_metrics (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  parcel_id UUID NOT NULL REFERENCES parcels(id) ON DELETE CASCADE,
  elevation_m NUMERIC(10,3),
  avg_slope_pct NUMERIC(8,4),
  max_slope_pct NUMERIC(8,4),
  slope_bands JSONB,
  knowledge_state TEXT NOT NULL DEFAULT 'UNKNOWN',
  source TEXT,
  retrieved_at TIMESTAMPTZ,
  confidence NUMERIC(5,2),
  geographic_resolution TEXT,
  raw JSONB NOT NULL DEFAULT '{}',
  normalized JSONB NOT NULL DEFAULT '{}'
);

CREATE TABLE utilities (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  parcel_id UUID NOT NULL REFERENCES parcels(id) ON DELETE CASCADE,
  electricity TEXT,
  water TEXT,
  sewer TEXT,
  gas TEXT,
  fiber TEXT,
  nearest_transmission_m NUMERIC(14,2),
  nearest_substation_m NUMERIC(14,2),
  knowledge_state TEXT NOT NULL DEFAULT 'UNKNOWN',
  source TEXT,
  retrieved_at TIMESTAMPTZ,
  confidence NUMERIC(5,2),
  raw JSONB NOT NULL DEFAULT '{}'
);

CREATE TABLE infrastructure (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  parcel_id UUID NOT NULL REFERENCES parcels(id) ON DELETE CASCADE,
  nearest_public_road_m NUMERIC(14,2),
  nearest_highway_m NUMERIC(14,2),
  nearest_interstate_m NUMERIC(14,2),
  nearest_rail_m NUMERIC(14,2),
  nearest_airport_m NUMERIC(14,2),
  road_frontage_m NUMERIC(14,2),
  legal_access_confidence NUMERIC(5,2),
  knowledge_state TEXT NOT NULL DEFAULT 'UNKNOWN',
  source TEXT,
  retrieved_at TIMESTAMPTZ,
  confidence NUMERIC(5,2),
  raw JSONB NOT NULL DEFAULT '{}'
);

CREATE TABLE crop_history (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  parcel_id UUID NOT NULL REFERENCES parcels(id) ON DELETE CASCADE,
  year INT NOT NULL,
  crop_code TEXT,
  crop_name TEXT,
  acres NUMERIC(14,4),
  source TEXT,
  confidence NUMERIC(5,2),
  retrieved_at TIMESTAMPTZ,
  raw JSONB NOT NULL DEFAULT '{}'
);

CREATE TABLE environmental_risks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  parcel_id UUID NOT NULL REFERENCES parcels(id) ON DELETE CASCADE,
  risk_type TEXT NOT NULL,
  severity TEXT,
  distance_m NUMERIC(14,2),
  knowledge_state TEXT NOT NULL DEFAULT 'UNKNOWN',
  source TEXT,
  confidence NUMERIC(5,2),
  retrieved_at TIMESTAMPTZ,
  raw JSONB NOT NULL DEFAULT '{}'
);

CREATE TABLE comparable_sales (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  subject_parcel_id UUID NOT NULL REFERENCES parcels(id) ON DELETE CASCADE,
  transaction_id UUID REFERENCES transactions(id),
  distance_m NUMERIC(14,2),
  similarity_score NUMERIC(5,2),
  adjusted_price_per_acre NUMERIC(18,2),
  adjustments JSONB NOT NULL DEFAULT '[]',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE scoring_weight_configs (
  id TEXT PRIMARY KEY,
  description TEXT,
  weights JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE scores (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  parcel_id UUID NOT NULL REFERENCES parcels(id) ON DELETE CASCADE,
  listing_id UUID REFERENCES listings(id),
  algorithm_version TEXT NOT NULL,
  weight_version TEXT NOT NULL,
  opportunity NUMERIC(5,2) NOT NULL,
  risk NUMERIC(5,2) NOT NULL,
  confidence NUMERIC(5,2) NOT NULL,
  asymmetry NUMERIC(5,2) NOT NULL,
  signal TEXT NOT NULL,
  best_strategy TEXT,
  secondary_strategy TEXT,
  personalized_opportunity NUMERIC(5,2),
  estimated_value_usd NUMERIC(18,2),
  asking_discount_pct NUMERIC(8,4),
  deal_readiness NUMERIC(5,2),
  input_hash TEXT NOT NULL,
  explanations JSONB NOT NULL DEFAULT '[]',
  strategy_screens JSONB NOT NULL DEFAULT '{}',
  strategy_scores JSONB NOT NULL DEFAULT '{}',
  computed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX scores_parcel_computed_idx ON scores (parcel_id, computed_at DESC);
CREATE INDEX scores_opportunity_idx ON scores (opportunity DESC);

CREATE TABLE score_components (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  score_id UUID NOT NULL REFERENCES scores(id) ON DELETE CASCADE,
  category TEXT NOT NULL,
  label TEXT NOT NULL,
  value NUMERIC(10,4),
  weight NUMERIC(8,4),
  contribution NUMERIC(10,4),
  knowledge_state TEXT,
  evidence JSONB NOT NULL DEFAULT '[]'
);

CREATE TABLE score_audit_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  score_id UUID NOT NULL REFERENCES scores(id) ON DELETE CASCADE,
  input_snapshot JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE catalysts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  parcel_id UUID REFERENCES parcels(id) ON DELETE CASCADE,
  type TEXT NOT NULL,
  source TEXT,
  distance_m NUMERIC(14,2),
  status TEXT,
  announcement_date DATE,
  estimated_completion DATE,
  confidence NUMERIC(5,2),
  raw JSONB NOT NULL DEFAULT '{}'
);

CREATE TABLE watchlists (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  parcel_id UUID NOT NULL REFERENCES parcels(id) ON DELETE CASCADE,
  watch_price BOOLEAN NOT NULL DEFAULT TRUE,
  watch_listing_status BOOLEAN NOT NULL DEFAULT TRUE,
  watch_zoning BOOLEAN NOT NULL DEFAULT FALSE,
  watch_nearby_development BOOLEAN NOT NULL DEFAULT FALSE,
  watch_adjacent BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id, parcel_id)
);

CREATE TABLE alert_rules (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  predicate JSONB NOT NULL,
  channels TEXT[] NOT NULL DEFAULT '{IN_APP}',
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE alerts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  rule_id UUID REFERENCES alert_rules(id) ON DELETE SET NULL,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  parcel_id UUID NOT NULL REFERENCES parcels(id) ON DELETE CASCADE,
  severity TEXT NOT NULL,
  title TEXT NOT NULL,
  body JSONB NOT NULL,
  delivered_channels TEXT[] NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE investment_scenarios (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  parcel_id UUID NOT NULL REFERENCES parcels(id) ON DELETE CASCADE,
  strategy TEXT NOT NULL,
  case_type TEXT NOT NULL, -- BASE | BULL | BEAR
  assumptions JSONB NOT NULL DEFAULT '{}',
  noi_usd NUMERIC(18,2),
  irr NUMERIC(8,4),
  npv_usd NUMERIC(18,2),
  cap_rate NUMERIC(8,4),
  cash_on_cash NUMERIC(8,4),
  breakeven_land_value_usd NUMERIC(18,2),
  knowledge_state TEXT NOT NULL DEFAULT 'ESTIMATED',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE data_quality (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  parcel_id UUID NOT NULL REFERENCES parcels(id) ON DELETE CASCADE,
  attribute_key TEXT NOT NULL,
  knowledge_state TEXT NOT NULL,
  source TEXT,
  retrieved_at TIMESTAMPTZ,
  confidence NUMERIC(5,2),
  notes TEXT,
  UNIQUE (parcel_id, attribute_key)
);

CREATE TABLE analysis_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  parcel_id UUID NOT NULL REFERENCES parcels(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'QUEUED',
  stage TEXT,
  error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ
);

CREATE TABLE due_diligence_items (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  parcel_id UUID NOT NULL REFERENCES parcels(id) ON DELETE CASCADE,
  label TEXT NOT NULL,
  completed BOOLEAN NOT NULL DEFAULT FALSE,
  sort_order INT NOT NULL DEFAULT 0
);

-- Seed system data sources
INSERT INTO data_sources (id, kind, name, status) VALUES
  ('manual', 'LISTING', 'Manual Entry', 'CONFIGURED'),
  ('csv', 'LISTING', 'CSV Import', 'CONFIGURED'),
  ('demo', 'LISTING', 'Demo Fixtures', 'CONFIGURED'),
  ('mls_reso', 'LISTING', 'MLS / RESO', 'NOT_CONFIGURED'),
  ('land_com', 'LISTING', 'Land.com Family', 'NOT_CONFIGURED'),
  ('crexi', 'LISTING', 'Crexi', 'NOT_CONFIGURED'),
  ('regrid', 'ENRICHMENT', 'Regrid Parcel Data', 'NOT_CONFIGURED'),
  ('ssurgo', 'ENRICHMENT', 'USDA SSURGO / SDA', 'CONFIGURED'),
  ('fema_nfhl', 'ENRICHMENT', 'FEMA NFHL', 'CONFIGURED'),
  ('nwi', 'ENRICHMENT', 'USFWS NWI', 'CONFIGURED'),
  ('usgs_3dep', 'ENRICHMENT', 'USGS 3DEP Elevation', 'CONFIGURED'),
  ('mapbox', 'ENRICHMENT', 'Mapbox', 'NOT_CONFIGURED'),
  ('twilio', 'ENRICHMENT', 'Twilio SMS', 'NOT_CONFIGURED'),
  ('smtp', 'ENRICHMENT', 'Email Delivery', 'NOT_CONFIGURED');

INSERT INTO scoring_weight_configs (id, description, weights) VALUES
  ('weights_default_v1', 'Phase 1 default institutional weights', '{
    "valuation_mispricing": 0.20,
    "intrinsic_land_quality": 0.10,
    "hbu_optionality": 0.15,
    "growth_appreciation": 0.15,
    "infrastructure": 0.10,
    "liquidity": 0.08,
    "scarcity": 0.07,
    "catalysts": 0.05,
    "seller_dynamics": 0.05,
    "risk": 0.05
  }'::jsonb);

INSERT INTO organizations (id, name) VALUES
  ('00000000-0000-4000-8000-000000000001', 'LandSignal Local');

INSERT INTO users (id, org_id, email, display_name) VALUES
  ('00000000-0000-4000-8000-000000000002',
   '00000000-0000-4000-8000-000000000001',
   'analyst@landsignal.local',
   'Local Analyst');
