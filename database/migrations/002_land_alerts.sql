-- Land Alerts: preference-driven acquisition profiles, matches, notification prefs
-- Designed for multiple profiles per user without schema rebuild.

CREATE TABLE IF NOT EXISTS land_alert_profiles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL DEFAULT 'My Land Alert',
  paused BOOLEAN NOT NULL DEFAULT FALSE,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  preferences JSONB NOT NULL DEFAULT '{}',
  notify JSONB NOT NULL DEFAULT '{"email":true,"sms":false,"in_app":true,"push":false,"sensitivity":"strong","frequency":"immediate"}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS land_alert_profiles_user_idx ON land_alert_profiles (user_id);
CREATE INDEX IF NOT EXISTS land_alert_profiles_active_idx ON land_alert_profiles (user_id, paused, active);

-- Soft index helpers extracted from preferences for scalable candidate filtering
CREATE TABLE IF NOT EXISTS land_alert_profile_states (
  profile_id UUID NOT NULL REFERENCES land_alert_profiles(id) ON DELETE CASCADE,
  state CHAR(2) NOT NULL,
  PRIMARY KEY (profile_id, state)
);

CREATE INDEX IF NOT EXISTS land_alert_profile_states_state_idx ON land_alert_profile_states (state);

CREATE TABLE IF NOT EXISTS land_alert_matches (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  profile_id UUID NOT NULL REFERENCES land_alert_profiles(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  parcel_id UUID NOT NULL REFERENCES parcels(id) ON DELETE CASCADE,
  preference_match_pct NUMERIC(6,2) NOT NULL,
  landsignal_score NUMERIC(6,2) NOT NULL,
  why_matched JSONB NOT NULL DEFAULT '[]',
  watch_flags JSONB NOT NULL DEFAULT '[]',
  status TEXT NOT NULL DEFAULT 'unseen', -- new | unseen | viewed
  origin TEXT NOT NULL DEFAULT 'existing_inventory',
  is_new_discovery BOOLEAN NOT NULL DEFAULT FALSE,
  update_kind TEXT,
  viewed_at TIMESTAMPTZ,
  qualified_for_alert BOOLEAN NOT NULL DEFAULT TRUE,
  notified BOOLEAN NOT NULL DEFAULT FALSE,
  notified_at TIMESTAMPTZ,
  notification_channels TEXT[] NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (profile_id, parcel_id)
);

CREATE INDEX IF NOT EXISTS land_alert_matches_user_status_idx
  ON land_alert_matches (user_id, status, preference_match_pct DESC);
CREATE INDEX IF NOT EXISTS land_alert_matches_parcel_idx ON land_alert_matches (parcel_id);

CREATE TABLE IF NOT EXISTS land_alert_notifications (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  profile_id UUID REFERENCES land_alert_profiles(id) ON DELETE SET NULL,
  match_id UUID REFERENCES land_alert_matches(id) ON DELETE SET NULL,
  parcel_id UUID NOT NULL REFERENCES parcels(id) ON DELETE CASCADE,
  channel TEXT NOT NULL, -- IN_APP | EMAIL | SMS | PUSH | DIGEST
  title TEXT NOT NULL,
  body JSONB NOT NULL DEFAULT '{}',
  delivery_status TEXT NOT NULL DEFAULT 'queued', -- queued | delivered | pending_provider | failed | skipped
  idempotency_key TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  delivered_at TIMESTAMPTZ,
  UNIQUE (idempotency_key)
);

CREATE INDEX IF NOT EXISTS land_alert_notifications_user_idx
  ON land_alert_notifications (user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS ingestion_job_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_kind TEXT NOT NULL, -- discover | land_alerts_monitor | rescore
  status TEXT NOT NULL, -- started | succeeded | failed
  detail JSONB NOT NULL DEFAULT '{}',
  error TEXT,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ
);
