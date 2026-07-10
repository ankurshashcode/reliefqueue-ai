CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS product_workers (
  worker_id TEXT PRIMARY KEY,
  display_name_safe TEXT NOT NULL,
  authorized_zone_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
  skills JSONB NOT NULL DEFAULT '[]'::jsonb,
  current_status TEXT NOT NULL DEFAULT 'available',
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS product_cases (
  case_id TEXT PRIMARY KEY,
  source_report_id TEXT NOT NULL,
  title TEXT NOT NULL,
  safe_summary TEXT NOT NULL,
  urgency TEXT NOT NULL,
  need_type TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',
  operation_zone_id TEXT NOT NULL,
  location_clue TEXT NOT NULL DEFAULT '',
  people_count INTEGER,
  assigned_worker_id TEXT REFERENCES product_workers(worker_id),
  geom GEOMETRY(Point, 4326),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS product_assignments (
  assignment_id BIGSERIAL PRIMARY KEY,
  case_id TEXT NOT NULL REFERENCES product_cases(case_id),
  worker_id TEXT NOT NULL REFERENCES product_workers(worker_id),
  assignment_status TEXT NOT NULL DEFAULT 'active',
  assigned_by TEXT NOT NULL DEFAULT 'command-center',
  idempotency_key TEXT UNIQUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS product_status_history (
  history_id BIGSERIAL PRIMARY KEY,
  case_id TEXT NOT NULL REFERENCES product_cases(case_id),
  actor_id TEXT NOT NULL,
  status TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  idempotency_key TEXT UNIQUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS product_audit_events (
  event_id BIGSERIAL PRIMARY KEY,
  actor_id TEXT NOT NULL,
  action TEXT NOT NULL,
  case_id TEXT,
  detail JSONB NOT NULL DEFAULT '{}'::jsonb,
  idempotency_key TEXT UNIQUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS product_message_outbox (
  message_id BIGSERIAL PRIMARY KEY,
  case_id TEXT NOT NULL REFERENCES product_cases(case_id),
  channel TEXT NOT NULL,
  body TEXT NOT NULL,
  paid_integration_state TEXT NOT NULL DEFAULT 'disabled_demo_local_only',
  idempotency_key TEXT UNIQUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS product_evidence_metadata (
  evidence_id BIGSERIAL PRIMARY KEY,
  case_id TEXT NOT NULL REFERENCES product_cases(case_id),
  worker_id TEXT NOT NULL,
  media_type TEXT NOT NULL,
  file_name TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  redaction_state TEXT NOT NULL DEFAULT 'metadata_only_no_binary_upload',
  idempotency_key TEXT UNIQUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS product_drill_history (
  drill_id BIGSERIAL PRIMARY KEY,
  drill_type TEXT NOT NULL,
  result JSONB NOT NULL,
  idempotency_key TEXT UNIQUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS product_ai_advisory_jobs (
  job_id TEXT PRIMARY KEY,
  case_id TEXT REFERENCES product_cases(case_id),
  status TEXT NOT NULL,
  provider_mode TEXT NOT NULL,
  idempotency_key TEXT UNIQUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS product_ai_advisory_results (
  job_id TEXT PRIMARY KEY REFERENCES product_ai_advisory_jobs(job_id),
  summary TEXT NOT NULL,
  recommendation TEXT NOT NULL,
  human_review_required BOOLEAN NOT NULL DEFAULT true,
  model_detail TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
