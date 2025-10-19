-- Consolidated Personal Injury schema migration
BEGIN;

-- Extensions
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Utility trigger to update updated_at
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS trigger AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Optional: backup/drop old tables that conflict (rename to _bak_<ts>)
DO $$
DECLARE
  t text;
  ts text := to_char(now(), 'YYYYMMDDHH24MISS');
  tables text[] := ARRAY[
    'attorneys','attorney_table','law_firmpointing','pi_leads','pi_answers','pi_blocklist',
    'session_clock_ephemera','pi_questions','call_sessions','lead_information','lead_qa','lead_booking'
  ];
BEGIN
  FOREACH t IN ARRAY tables LOOP
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = t) THEN
      EXECUTE format('ALTER TABLE %I RENAME TO %I_bak_%s', t, t, ts);
    END IF;
  END LOOP;
END$$;

-- Tenant table (law firm pointer)
CREATE TABLE IF NOT EXISTS law_firmpointing (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_key TEXT UNIQUE NOT NULL,
  firm_name TEXT NOT NULL,
  metadata JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Attorneys table
CREATE TABLE IF NOT EXISTS attorney_table (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  firm_id UUID NOT NULL REFERENCES law_firmpointing(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  email TEXT,
  practice_area TEXT NOT NULL,
  attorney_calendar_type TEXT NOT NULL CHECK (attorney_calendar_type IN ('google','calcom','none')),
  calendar_id TEXT,               -- Google calendar id
  calcom_event_type_id TEXT,      -- Cal.com event type id
  calendar_account_credentials JSONB NOT NULL DEFAULT '{}'::jsonb, -- encrypted/JSON creds reference
  business_tz TEXT DEFAULT 'UTC',
  config JSONB DEFAULT '{}'::jsonb,
  is_active BOOLEAN DEFAULT true,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_attorney_firm ON attorney_table(firm_id);
CREATE INDEX IF NOT EXISTS idx_attorney_email ON attorney_table(email);

DROP TRIGGER IF EXISTS attorney_table_set_updated_at ON attorney_table;
CREATE TRIGGER attorney_table_set_updated_at
BEFORE UPDATE ON attorney_table
FOR EACH ROW EXECUTE PROCEDURE set_updated_at();

-- PI leads (one per caller/lead)
CREATE TABLE IF NOT EXISTS pi_leads (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  firm_id UUID NOT NULL REFERENCES law_firmpointing(id) ON DELETE CASCADE,
  unique_caller_id UUID UNIQUE,         -- created by create_or_get_caller_id
  phone TEXT,
  email TEXT,
  full_name TEXT,
  source_channel TEXT,
  current_practice_area TEXT DEFAULT 'personal_injury',
  status TEXT DEFAULT 'new',
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_pi_leads_email ON pi_leads(email);
DROP TRIGGER IF EXISTS pi_leads_set_updated_at ON pi_leads;
CREATE TRIGGER pi_leads_set_updated_at
BEFORE UPDATE ON pi_leads
FOR EACH ROW EXECUTE PROCEDURE set_updated_at();

-- PI questions (decision-tree)
CREATE TABLE IF NOT EXISTS pi_questions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  firm_id UUID NOT NULL REFERENCES law_firmpointing(id) ON DELETE CASCADE,
  practice_area TEXT NOT NULL DEFAULT 'personal_injury',
  path_id TEXT NOT NULL,           -- e.g., 'car_accident_v1'
  question_order INT NOT NULL,
  question_key TEXT NOT NULL,      -- canonical key used for answers
  question_text TEXT NOT NULL,
  answer_type TEXT NOT NULL CHECK (answer_type IN ('choice','yes_no','number','slider')),
  choices JSONB DEFAULT '[]'::jsonb,
  required BOOLEAN DEFAULT true,
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE (firm_id, path_id, question_key)
);
CREATE INDEX IF NOT EXISTS idx_pi_questions_path ON pi_questions(firm_id, path_id);

-- PI answers (saved structured Q/A)
CREATE TABLE IF NOT EXISTS pi_answers (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  lead_id UUID NOT NULL REFERENCES pi_leads(id) ON DELETE CASCADE,
  question_key TEXT NOT NULL,
  question_text TEXT,
  answer_text TEXT,
  answer_enum TEXT,
  answer_json JSONB,
  question_type TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_pi_answers_lead ON pi_answers(lead_id);
CREATE INDEX IF NOT EXISTS idx_pi_answers_qk ON pi_answers(question_key);

-- PI blocklist (deterministic regexs)
CREATE TABLE IF NOT EXISTS pi_blocklist (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  firm_id UUID NOT NULL REFERENCES law_firmpointing(id) ON DELETE CASCADE,
  practice_area TEXT NOT NULL DEFAULT 'personal_injury',
  block_key TEXT NOT NULL,
  phrase TEXT NOT NULL,
  regex_pattern TEXT NOT NULL,
  severity TEXT DEFAULT 'high',
  default_action TEXT DEFAULT 'redact',
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE (firm_id, block_key)
);
CREATE INDEX IF NOT EXISTS idx_pi_blocklist_practice ON pi_blocklist(practice_area);

-- Session clock and ephemeral artifacts (ephemeral storage; TTL managed externally)
CREATE TABLE IF NOT EXISTS session_clock_ephemera (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  firm_id UUID NOT NULL REFERENCES law_firmpointing(id) ON DELETE CASCADE,
  session_id TEXT UNIQUE NOT NULL,
  lead_id UUID NULL REFERENCES pi_leads(id),
  session_clock JSONB NOT NULL,            -- {utc_iso, pt_iso, pt_date, pt_year}
  high_risk_flags JSONB DEFAULT '[]'::jsonb,
  redactions_applied BOOLEAN DEFAULT false,
  ephemeral_logs JSONB DEFAULT '[]'::jsonb, -- anonymized events only
  expires_at TIMESTAMPTZ,                   -- set by application to now() + interval '7 seconds'
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_session_expires ON session_clock_ephemera(expires_at);

-- Call sessions (lightweight)
CREATE TABLE IF NOT EXISTS call_sessions (
  id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  unique_caller_id UUID NOT NULL,
  source_channel TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_call_sessions_unique_caller_id ON call_sessions(unique_caller_id);

-- Lead information (detailed)
CREATE TABLE IF NOT EXISTS lead_information (
  id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  unique_caller_id UUID NOT NULL UNIQUE,
  full_name TEXT,
  email TEXT,
  phone TEXT,
  practice_area TEXT NOT NULL DEFAULT 'personal_injury',
  assigned_attorney TEXT,
  summary TEXT,
  source_channel TEXT,
  caller_type TEXT,
  consent_timestamp TIMESTAMPTZ,
  locale TEXT,
  timezone TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_lead_information_email ON lead_information(email);
CREATE INDEX IF NOT EXISTS idx_lead_information_practice_area ON lead_information(practice_area);
DROP TRIGGER IF EXISTS trg_lead_information_updated_at ON lead_information;
CREATE TRIGGER trg_lead_information_updated_at
BEFORE UPDATE ON lead_information
FOR EACH ROW EXECUTE PROCEDURE set_updated_at();

-- Lead QA (serialized Q/A snapshot)
CREATE TABLE IF NOT EXISTS lead_qa (
  id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  unique_caller_id UUID NOT NULL,
  email TEXT,
  all_q_and_a JSONB NOT NULL, -- array of {question_key, question_text, answer_enum, answer_text, confidence, ts}
  practice_area_version TEXT,
  completion_status TEXT NOT NULL DEFAULT 'complete',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT lead_qa_all_q_and_a_is_ARRAY CHECK (jsonb_typeof(all_q_and_a) = 'array')
);
CREATE INDEX IF NOT EXISTS idx_lead_qa_unique_caller_id ON lead_qa(unique_caller_id);
CREATE INDEX IF NOT EXISTS idx_lead_qa_email ON lead_qa(email);
CREATE INDEX IF NOT EXISTS idx_lead_qa_completion_status ON lead_qa(completion_status);
DROP TRIGGER IF EXISTS trg_lead_qa_updated_at ON lead_qa;
CREATE TRIGGER trg_lead_qa_updated_at
BEFORE UPDATE ON lead_qa
FOR EACH ROW EXECUTE PROCEDURE set_updated_at();

-- Lead bookings
CREATE TABLE IF NOT EXISTS lead_booking (
  id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  unique_caller_id UUID NOT NULL,
  email TEXT,
  appointment_datetime TIMESTAMPTZ NOT NULL,
  timezone TEXT,
  platform TEXT NOT NULL,
  meeting_link TEXT,
  phone_number TEXT,
  booked_with TEXT,
  booking_notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_lead_booking_unique_caller_id ON lead_booking(unique_caller_id);
CREATE INDEX IF NOT EXISTS idx_lead_booking_email ON lead_booking(email);
CREATE INDEX IF NOT EXISTS idx_lead_booking_appointment ON lead_booking(appointment_datetime);
DROP TRIGGER IF EXISTS trg_lead_booking_updated_at ON lead_booking;
CREATE TRIGGER trg_lead_booking_updated_at
BEFORE UPDATE ON lead_booking
FOR EACH ROW EXECUTE PROCEDURE set_updated_at();

COMMIT;