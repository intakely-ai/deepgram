-- SQL to create an `attorneys` table for appointment/calendar configuration
-- Adjust schema names and types to match your Postgres/Supabase conventions if needed.

CREATE TABLE IF NOT EXISTS attorneys (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL,
    email text UNIQUE NOT NULL,

    -- Calendar provider for this attorney. Expected values: 'google', 'cal.com'
    calendar_type text DEFAULT 'google' NOT NULL,

    -- For Google: calendar_id is the calendar to add events into
    calendar_id text,

    -- For Cal.com: event_type_id used to create bookings
    calcom_event_type_id text,

    -- Optional per-attorney API key or token reference (store secrets securely, not in DB in production)
    calendar_api_key text,

    -- Business timezone for this attorney (IANA tz string)
    business_tz text DEFAULT 'UTC',

    -- Availability or configuration JSON: e.g. business hours, days off, custom slot rules
    config jsonb DEFAULT '{}'::jsonb,

    tenant_id uuid,

    created_at timestamptz DEFAULT now() NOT NULL,
    updated_at timestamptz DEFAULT now() NOT NULL
);

-- Optional index for lookups by tenant
CREATE INDEX IF NOT EXISTS attorneys_tenant_idx ON attorneys (tenant_id);
CREATE INDEX IF NOT EXISTS attorneys_email_idx ON attorneys (email);

-- Trigger to keep updated_at current
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ language 'plpgsql';

DROP TRIGGER IF EXISTS attorneys_updated_at_trigger ON attorneys;
CREATE TRIGGER attorneys_updated_at_trigger
BEFORE UPDATE ON attorneys
FOR EACH ROW
EXECUTE PROCEDURE update_updated_at_column();

-- Grant minimal privileges if needed (adjust role names for Supabase)
-- GRANT SELECT, INSERT, UPDATE, DELETE ON attorneys TO authenticated;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON attorneys TO service_role;