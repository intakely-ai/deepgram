database.sql
create table public.addresses (
  address_id uuid not null default gen_random_uuid (),
  address_line1 character varying(255) not null,
  address_line2 character varying(255) null,
  city character varying(100) not null,
  state_province character varying(2) not null,
  postal_code character varying(10) not null,
  country_code character varying(2) null default 'US'::character varying,
  address_type character varying(50) not null,
  latitude numeric(10, 8) null,
  longitude numeric(11, 8) null,
  entity_type character varying(50) not null,
  entity_id uuid not null,
  created_by uuid null,
  modified_by uuid null,
  created_at timestamp without time zone null default CURRENT_TIMESTAMP,
  updated_at timestamp without time zone null default CURRENT_TIMESTAMP,
  apartment_unit character varying(100) null,
  is_primary boolean null default false,
  is_verified boolean null,
  is_active boolean null,
  is_deleted boolean null default false,
  deleted_at timestamp with time zone null,
  deleted_by uuid null,
  deletion_reason text null,
  is_archived boolean null default false,
  archive_reason character varying(100) null,
  archive_date timestamp with time zone null,
  archive_review_date date null,
  law_firm_id uuid null,
  constraint addresses_pkey primary key (address_id),
  constraint fk_addresses_tenant_id foreign KEY (law_firm_id) references tenants (tenant_id),
  constraint chk_address_type check (
    (
      (address_type)::text = any (
        (
          array[
            'Home'::character varying,
            'Work'::character varying,
            'Mailing'::character varying,
            'Billing'::character varying,
            'Legal Service'::character varying,
            'Temporary'::character varying,
            'Emergency'::character varying,
            'Other'::character varying
          ]
        )::text[]
      )
    )
  ),
  constraint valid_address_type check (
    (
      (address_type)::text = any (
        (
          array[
            'business'::character varying,
            'billing'::character varying,
            'mailing'::character varying,
            'home'::character varying,
            'incident'::character varying
          ]
        )::text[]
      )
    )
  ),
  constraint valid_entity_type check (
    (
      (entity_type)::text = any (
        (
          array[
            'tenant'::character varying,
            'contact'::character varying,
            'lead'::character varying
          ]
        )::text[]
      )
    )
  )
) TABLESPACE pg_default;

create index IF not exists idx_addresses_entity on public.addresses using btree (entity_type, entity_id) TABLESPACE pg_default;

create index IF not exists idx_addresses_state on public.addresses using btree (state_province) TABLESPACE pg_default;

create index IF not exists idx_addresses_postal on public.addresses using btree (postal_code) TABLESPACE pg_default;

create index IF not exists idx_addresses_is_primary on public.addresses using btree (is_primary) TABLESPACE pg_default;

create index IF not exists idx_addresses_tenant_id on public.addresses using btree (law_firm_id) TABLESPACE pg_default;

create trigger update_addresses_updated_at BEFORE
update on addresses for EACH row
execute FUNCTION update_updated_at_column ();create table public.api_keys (
  key_id uuid not null default gen_random_uuid (),
  tenant_id uuid not null,
  key_name character varying(255) not null,
  key_value character varying(255) not null,
  key_type character varying(100) not null,
  permissions jsonb null,
  is_active boolean null default true,
  expires_at timestamp with time zone null,
  last_used_at timestamp with time zone null,
  created_by uuid null,
  modified_by uuid null,
  created_at timestamp with time zone null default now(),
  updated_at timestamp with time zone null default now(),
  constraint api_keys_pkey primary key (key_id)
) TABLESPACE pg_default;

create index IF not exists idx_api_keys_tenant_id on public.api_keys using btree (tenant_id) TABLESPACE pg_default;

create trigger update_api_keys_updated_at BEFORE
update on api_keys for EACH row
execute FUNCTION update_updated_at_column ();create table public.appointment_reminders (
  reminder_id uuid not null default gen_random_uuid (),
  appointment_id uuid not null,
  reminder_type character varying(100) not null,
  reminder_time timestamp with time zone not null,
  reminder_method character varying(50) not null,
  reminder_status character varying(50) null default 'pending'::character varying,
  sent_at timestamp with time zone null,
  created_by uuid null,
  modified_by uuid null,
  created_at timestamp with time zone null default now(),
  updated_at timestamp with time zone null default now(),
  constraint appointment_reminders_pkey primary key (reminder_id)
) TABLESPACE pg_default;

create trigger update_appointment_reminders_updated_at BEFORE
update on appointment_reminders for EACH row
execute FUNCTION update_updated_at_column ();create table public.appointments (
  appointment_id uuid not null default gen_random_uuid (),
  tenant_id uuid not null,
  attorney_id uuid not null,
  client_name character varying(255) not null,
  client_phone character varying(50) null,
  client_email character varying(255) null,
  appointment_type character varying(100) null default 'consultation'::character varying,
  start_time timestamp with time zone not null,
  end_time timestamp with time zone not null,
  timezone character varying(50) null default 'America/Los_Angeles'::character varying,
  location character varying(255) null,
  status character varying(50) null default 'scheduled'::character varying,
  notes text null,
  lead_id uuid null,
  intake_session_id uuid null,
  created_by uuid null,
  modified_by uuid null,
  created_at timestamp with time zone null default now(),
  updated_at timestamp with time zone null default now(),
  is_deleted boolean null default false,
  deleted_at timestamp with time zone null,
  deleted_by uuid null,
  deletion_reason text null,
  is_archived boolean null default false,
  archive_reason character varying(100) null,
  archive_date timestamp with time zone null,
  archive_review_date date null,
  confirmation_status character varying(50) null default 'pending'::character varying,
  confirmation_sent_at timestamp with time zone null,
  attendance_concern text null,
  documents_to_bring text[] null,
  reminder_preferences jsonb null,
  cancellation_reason text null,
  rescheduled_from_appointment_id uuid null,
  social_media_invite_sent boolean null default false,
  social_media_invite_sent_at timestamp with time zone null,
  reschedule_requested boolean null default false,
  reschedule_requested_at timestamp with time zone null,
  reschedule_reason text null,
  original_start_time timestamp with time zone null,
  original_end_time timestamp with time zone null,
  reschedule_count integer null default 0,
  last_rescheduled_at timestamp with time zone null,
  constraint appointments_pkey primary key (appointment_id),
  constraint chk_appointments_confirmation_status check (
    (
      (confirmation_status)::text = any (
        (
          array[
            'pending'::character varying,
            'confirmed'::character varying,
            'declined'::character varying,
            'rescheduled'::character varying,
            'cancelled'::character varying
          ]
        )::text[]
      )
    )
  )
) TABLESPACE pg_default;

create index IF not exists idx_appointments_tenant_id on public.appointments using btree (tenant_id) TABLESPACE pg_default;

create index IF not exists idx_appointments_start_time on public.appointments using btree (start_time) TABLESPACE pg_default;

create index IF not exists idx_appointments_status on public.appointments using btree (status) TABLESPACE pg_default;

create index IF not exists idx_appointments_appointment_type on public.appointments using btree (appointment_type) TABLESPACE pg_default;

create index IF not exists idx_appointments_confirmation_status on public.appointments using btree (confirmation_status) TABLESPACE pg_default;

create index IF not exists idx_appointments_confirmation_sent_at on public.appointments using btree (confirmation_sent_at) TABLESPACE pg_default;

create index IF not exists idx_appointments_rescheduled_from on public.appointments using btree (rescheduled_from_appointment_id) TABLESPACE pg_default;

create index IF not exists idx_appointments_social_media_invite_sent on public.appointments using btree (social_media_invite_sent) TABLESPACE pg_default;

create index IF not exists idx_appointments_reschedule_requested on public.appointments using btree (reschedule_requested) TABLESPACE pg_default;

create index IF not exists idx_appointments_reschedule_count on public.appointments using btree (reschedule_count) TABLESPACE pg_default;

create index IF not exists idx_appointments_last_rescheduled_at on public.appointments using btree (last_rescheduled_at) TABLESPACE pg_default;

create trigger update_appointments_updated_at BEFORE
update on appointments for EACH row
execute FUNCTION update_updated_at_column ();create table public.audit_logs (
  audit_id uuid not null default gen_random_uuid (),
  tenant_id uuid null,
  user_id uuid null,
  action character varying(100) not null,
  entity_type character varying(100) null,
  entity_id uuid null,
  old_values jsonb null,
  new_values jsonb null,
  ip_address inet null,
  user_agent text null,
  timestamp timestamp with time zone null default now(),
  created_by uuid null,
  modified_by uuid null,
  created_at timestamp with time zone null default now(),
  updated_at timestamp with time zone null default now(),
  constraint audit_logs_pkey primary key (audit_id)
) TABLESPACE pg_default;

create index IF not exists idx_audit_logs_tenant_id on public.audit_logs using btree (tenant_id) TABLESPACE pg_default;

create index IF not exists idx_audit_logs_timestamp on public.audit_logs using btree ("timestamp") TABLESPACE pg_default;

create trigger update_audit_logs_updated_at BEFORE
update on audit_logs for EACH row
execute FUNCTION update_updated_at_column ();create table public.calendar_appointment_confirmation_logs (
  confirmation_log_id uuid not null default gen_random_uuid (),
  calendar_event_id uuid not null,
  confirmation_type character varying(50) not null,
  confirmation_status character varying(50) not null,
  recipient_type character varying(50) not null,
  recipient_contact_id uuid null,
  recipient_user_id uuid null,
  recipient_email character varying(255) null,
  recipient_phone character varying(20) null,
  message_subject character varying(255) null,
  message_content text null,
  confirmation_link character varying(500) null,
  confirmation_code character varying(50) null,
  sent_at timestamp with time zone null,
  delivered_at timestamp with time zone null,
  read_at timestamp with time zone null,
  responded_at timestamp with time zone null,
  response_content text null,
  response_metadata jsonb null,
  retry_count integer null default 0,
  max_retries integer null default 3,
  next_retry_at timestamp with time zone null,
  provider_message_id character varying(255) null,
  provider_status character varying(100) null,
  provider_error_message text null,
  communication_channel character varying(50) null,
  template_used character varying(100) null,
  template_variables jsonb null,
  tenant_id uuid null,
  is_active boolean null default true,
  created_by uuid null,
  modified_by uuid null,
  created_at timestamp with time zone null default now(),
  updated_at timestamp with time zone null default now(),
  constraint calendar_appointment_confirmation_logs_pkey primary key (confirmation_log_id),
  constraint fk_calendar_appointment_confirmation_logs_contact_id foreign KEY (recipient_contact_id) references contacts (contact_id),
  constraint fk_calendar_appointment_confirmation_logs_event_id foreign KEY (calendar_event_id) references calendar_events (event_id),
  constraint fk_calendar_appointment_confirmation_logs_tenant_id foreign KEY (tenant_id) references tenants (tenant_id),
  constraint chk_communication_channel check (
    (
      (communication_channel)::text = any (
        (
          array[
            'email'::character varying,
            'sms'::character varying,
            'voice'::character varying,
            'push'::character varying,
            'webhook'::character varying,
            'in_app'::character varying
          ]
        )::text[]
      )
    )
  ),
  constraint chk_confirmation_status check (
    (
      (confirmation_status)::text = any (
        (
          array[
            'sent'::character varying,
            'delivered'::character varying,
            'read'::character varying,
            'confirmed'::character varying,
            'declined'::character varying,
            'failed'::character varying,
            'pending'::character varying
          ]
        )::text[]
      )
    )
  )
) TABLESPACE pg_default;

create index IF not exists idx_calendar_appointment_confirmation_logs_event_id on public.calendar_appointment_confirmation_logs using btree (calendar_event_id) TABLESPACE pg_default;

create index IF not exists idx_calendar_appointment_confirmation_logs_recipient_email on public.calendar_appointment_confirmation_logs using btree (recipient_email) TABLESPACE pg_default;

create index IF not exists idx_calendar_appointment_confirmation_logs_status on public.calendar_appointment_confirmation_logs using btree (confirmation_status) TABLESPACE pg_default;

create index IF not exists idx_calendar_appointment_confirmation_logs_sent_at on public.calendar_appointment_confirmation_logs using btree (sent_at) TABLESPACE pg_default;create table public.calendar_appointment_reminders_enhanced (
  reminder_id uuid not null default gen_random_uuid (),
  appointment_id uuid not null,
  reminder_type character varying(50) not null,
  reminder_timing_minutes integer not null,
  reminder_message text null,
  reminder_status character varying(50) null default 'scheduled'::character varying,
  scheduled_send_time timestamp with time zone not null,
  actual_send_time timestamp with time zone null,
  delivery_confirmation jsonb null,
  recipient_contact_info character varying(255) null,
  recipient_type character varying(50) null default 'attendee'::character varying,
  notification_provider character varying(50) null,
  retry_count integer null default 0,
  max_retries integer null default 3,
  last_error_message text null,
  is_active boolean null default true,
  created_by uuid null,
  modified_by uuid null,
  created_at timestamp with time zone null default now(),
  updated_at timestamp with time zone null default now(),
  constraint calendar_appointment_reminders_enhanced_pkey primary key (reminder_id),
  constraint fk_calendar_appointment_reminders_appointment_id foreign KEY (appointment_id) references appointments (appointment_id),
  constraint chk_reminder_status check (
    (
      (reminder_status)::text = any (
        (
          array[
            'scheduled'::character varying,
            'sent'::character varying,
            'delivered'::character varying,
            'failed'::character varying,
            'cancelled'::character varying
          ]
        )::text[]
      )
    )
  ),
  constraint chk_reminder_type check (
    (
      (reminder_type)::text = any (
        (
          array[
            'email'::character varying,
            'sms'::character varying,
            'push'::character varying,
            'in_app'::character varying,
            'voice'::character varying
          ]
        )::text[]
      )
    )
  )
) TABLESPACE pg_default;

create index IF not exists idx_calendar_appointment_reminders_appointment_id on public.calendar_appointment_reminders_enhanced using btree (appointment_id) TABLESPACE pg_default;

create index IF not exists idx_calendar_appointment_reminders_scheduled_send_time on public.calendar_appointment_reminders_enhanced using btree (scheduled_send_time) TABLESPACE pg_default;

create index IF not exists idx_calendar_appointment_reminders_status on public.calendar_appointment_reminders_enhanced using btree (reminder_status) TABLESPACE pg_default;

create index IF not exists idx_calendar_appointment_reminders_type on public.calendar_appointment_reminders_enhanced using btree (reminder_type) TABLESPACE pg_default;create table public.calendar_appointment_reschedules (
  reschedule_id uuid not null default gen_random_uuid (),
  calendar_event_id uuid not null,
  original_start_time timestamp with time zone not null,
  original_end_time timestamp with time zone not null,
  new_start_time timestamp with time zone not null,
  new_end_time timestamp with time zone not null,
  reschedule_reason character varying(255) null,
  reschedule_status character varying(50) null default 'pending'::character varying,
  requested_by uuid not null,
  approved_by uuid null,
  approved_at timestamp with time zone null,
  rejection_reason text null,
  notification_sent boolean null default false,
  notification_sent_at timestamp with time zone null,
  is_active boolean null default true,
  created_by uuid null,
  modified_by uuid null,
  created_at timestamp with time zone null default now(),
  updated_at timestamp with time zone null default now(),
  constraint calendar_appointment_reschedules_pkey primary key (reschedule_id),
  constraint fk_calendar_appointment_reschedules_event_id foreign KEY (calendar_event_id) references calendar_events (event_id),
  constraint chk_reschedule_status check (
    (
      (reschedule_status)::text = any (
        (
          array[
            'pending'::character varying,
            'approved'::character varying,
            'rejected'::character varying,
            'cancelled'::character varying
          ]
        )::text[]
      )
    )
  )
) TABLESPACE pg_default;

create index IF not exists idx_calendar_appointment_reschedules_event_id on public.calendar_appointment_reschedules using btree (calendar_event_id) TABLESPACE pg_default;

create index IF not exists idx_calendar_appointment_reschedules_new_start_time on public.calendar_appointment_reschedules using btree (new_start_time) TABLESPACE pg_default;

create index IF not exists idx_calendar_appointment_reschedules_status on public.calendar_appointment_reschedules using btree (reschedule_status) TABLESPACE pg_default;

create index IF not exists idx_calendar_appointment_reschedules_requested_by on public.calendar_appointment_reschedules using btree (requested_by) TABLESPACE pg_default;create table public.calendar_attorney_availability_patterns (
  pattern_id uuid not null default gen_random_uuid (),
  user_profile_id uuid not null,
  pattern_type character varying(30) not null,
  days_of_week integer[] not null,
  start_time time without time zone not null,
  end_time time without time zone not null,
  effective_start_date date not null,
  effective_end_date date null,
  is_active boolean null default true,
  notes text null,
  created_by uuid null,
  modified_by uuid null,
  created_at timestamp with time zone null default now(),
  updated_at timestamp with time zone null default now(),
  constraint calendar_attorney_availability_patterns_pkey primary key (pattern_id),
  constraint fk_calendar_attorney_availability_patterns_user_profile_id foreign KEY (user_profile_id) references user_profiles (user_profile_id)
) TABLESPACE pg_default;

create index IF not exists idx_calendar_attorney_availability_patterns_user_profile_id on public.calendar_attorney_availability_patterns using btree (user_profile_id) TABLESPACE pg_default;

create index IF not exists idx_calendar_attorney_availability_patterns_pattern_type on public.calendar_attorney_availability_patterns using btree (pattern_type) TABLESPACE pg_default;

create index IF not exists idx_calendar_attorney_availability_patterns_effective_dates on public.calendar_attorney_availability_patterns using btree (effective_start_date, effective_end_date) TABLESPACE pg_default;create table public.calendar_attorney_booking_rules (
  rule_id uuid not null default gen_random_uuid (),
  user_profile_id uuid not null,
  min_notice_minutes integer null default 60,
  max_advance_days integer null default 90,
  buffer_between_appointments integer null default 15,
  allow_double_booking boolean null default false,
  allowed_event_type_ids uuid[] null,
  notes text null,
  is_active boolean null default true,
  created_by uuid null,
  modified_by uuid null,
  created_at timestamp with time zone null default now(),
  updated_at timestamp with time zone null default now(),
  constraint calendar_attorney_booking_rules_pkey primary key (rule_id),
  constraint fk_calendar_attorney_booking_rules_user_profile_id foreign KEY (user_profile_id) references user_profiles (user_profile_id)
) TABLESPACE pg_default;

create index IF not exists idx_calendar_attorney_booking_rules_user_profile_id on public.calendar_attorney_booking_rules using btree (user_profile_id) TABLESPACE pg_default;

create index IF not exists idx_calendar_attorney_booking_rules_is_active on public.calendar_attorney_booking_rules using btree (is_active) TABLESPACE pg_default;create table public.calendar_attorney_preferences (
  preference_id uuid not null default gen_random_uuid (),
  user_profile_id uuid not null,
  default_calendar_account_id uuid null,
  working_hours jsonb null,
  timezone character varying(100) null,
  notification_preferences jsonb null,
  is_active boolean null default true,
  created_by uuid null,
  modified_by uuid null,
  created_at timestamp with time zone null default now(),
  updated_at timestamp with time zone null default now(),
  constraint calendar_attorney_preferences_pkey primary key (preference_id),
  constraint fk_calendar_attorney_preferences_user_profile_id foreign KEY (user_profile_id) references user_profiles (user_profile_id)
) TABLESPACE pg_default;

create index IF not exists idx_calendar_attorney_preferences_user_profile_id on public.calendar_attorney_preferences using btree (user_profile_id) TABLESPACE pg_default;

create index IF not exists idx_calendar_attorney_preferences_is_active on public.calendar_attorney_preferences using btree (is_active) TABLESPACE pg_default;create table public.calendar_availability_slots (
  calendar_availability_slot_id uuid not null default gen_random_uuid (),
  calendar_account_id uuid not null,
  calendar_event_type_id uuid null,
  slot_start_time timestamp with time zone not null,
  slot_end_time timestamp with time zone not null,
  slot_duration_minutes integer not null,
  slot_status character varying(50) null default 'available'::character varying,
  slot_recurrence_rule text null,
  slot_max_bookings integer null default 1,
  slot_current_bookings integer null default 0,
  slot_notes text null,
  slot_tags character varying(255) [] null,
  is_active boolean null default true,
  created_by uuid null,
  modified_by uuid null,
  created_at timestamp with time zone null default now(),
  updated_at timestamp with time zone null default now(),
  constraint calendar_availability_slots_pkey primary key (calendar_availability_slot_id),
  constraint fk_calendar_availability_slots_account_id foreign KEY (calendar_account_id) references calendar_providers (calendar_provider_id),
  constraint fk_calendar_availability_slots_event_type_id foreign KEY (calendar_event_type_id) references calendar_event_types (calendar_event_type_id),
  constraint chk_slot_status check (
    (
      (slot_status)::text = any (
        (
          array[
            'available'::character varying,
            'booked'::character varying,
            'blocked'::character varying,
            'tentative'::character varying
          ]
        )::text[]
      )
    )
  )
) TABLESPACE pg_default;

create index IF not exists idx_calendar_availability_slots_account_id on public.calendar_availability_slots using btree (calendar_account_id) TABLESPACE pg_default;

create index IF not exists idx_calendar_availability_slots_start_time on public.calendar_availability_slots using btree (slot_start_time) TABLESPACE pg_default;

create index IF not exists idx_calendar_availability_slots_end_time on public.calendar_availability_slots using btree (slot_end_time) TABLESPACE pg_default;

create index IF not exists idx_calendar_availability_slots_status on public.calendar_availability_slots using btree (slot_status) TABLESPACE pg_default;

create index IF not exists idx_calendar_availability_slots_event_type_id on public.calendar_availability_slots using btree (calendar_event_type_id) TABLESPACE pg_default;create table public.calendar_event_attendees (
  attendee_id uuid not null default gen_random_uuid (),
  event_id uuid not null,
  user_profile_id uuid null,
  email character varying(255) not null,
  name character varying(255) null,
  status character varying(50) null default 'pending'::character varying,
  role character varying(50) null default 'required'::character varying,
  response_notes text null,
  response_time timestamp with time zone null,
  is_organizer boolean null default false,
  external_attendee_id character varying(255) null,
  contact_id uuid null,
  created_by uuid null,
  modified_by uuid null,
  created_at timestamp with time zone null default now(),
  updated_at timestamp with time zone null default now(),
  constraint calendar_event_attendees_pkey primary key (attendee_id),
  constraint fk_calendar_event_attendees_contact_id foreign KEY (contact_id) references contacts (contact_id),
  constraint fk_calendar_event_attendees_event_id foreign KEY (event_id) references calendar_events (event_id),
  constraint chk_attendee_role check (
    (
      (role)::text = any (
        (
          array[
            'required'::character varying,
            'optional'::character varying
          ]
        )::text[]
      )
    )
  ),
  constraint chk_attendee_status check (
    (
      (status)::text = any (
        (
          array[
            'pending'::character varying,
            'confirmed'::character varying,
            'declined'::character varying,
            'tentative'::character varying
          ]
        )::text[]
      )
    )
  )
) TABLESPACE pg_default;

create index IF not exists idx_calendar_event_attendees_event_id on public.calendar_event_attendees using btree (event_id) TABLESPACE pg_default;

create index IF not exists idx_calendar_event_attendees_email on public.calendar_event_attendees using btree (email) TABLESPACE pg_default;

create index IF not exists idx_calendar_event_attendees_status on public.calendar_event_attendees using btree (status) TABLESPACE pg_default;

create index IF not exists idx_calendar_event_attendees_contact_id on public.calendar_event_attendees using btree (contact_id) TABLESPACE pg_default;create table public.calendar_event_types (
  calendar_event_type_id uuid not null default gen_random_uuid (),
  event_type_name character varying(100) not null,
  event_type_code character varying(50) not null,
  event_type_category character varying(50) not null,
  event_type_description text null,
  default_duration_minutes integer null default 60,
  is_active boolean null default true,
  event_type_metadata jsonb null,
  tenant_id uuid null,
  created_by uuid null,
  modified_by uuid null,
  created_at timestamp with time zone null default now(),
  updated_at timestamp with time zone null default now(),
  constraint calendar_event_types_pkey primary key (calendar_event_type_id),
  constraint calendar_event_types_event_type_code_key unique (event_type_code),
  constraint fk_calendar_event_types_tenant_id foreign KEY (tenant_id) references tenants (tenant_id)
) TABLESPACE pg_default;

create index IF not exists idx_calendar_event_types_event_type_code on public.calendar_event_types using btree (event_type_code) TABLESPACE pg_default;

create index IF not exists idx_calendar_event_types_event_type_category on public.calendar_event_types using btree (event_type_category) TABLESPACE pg_default;

create index IF not exists idx_calendar_event_types_tenant_id on public.calendar_event_types using btree (tenant_id) TABLESPACE pg_default;

create index IF not exists idx_calendar_event_types_is_active on public.calendar_event_types using btree (is_active) TABLESPACE pg_default;create table public.calendar_events (
  event_id uuid not null default gen_random_uuid (),
  appointment_id uuid not null,
  provider_type character varying(100) not null,
  external_event_id character varying(255) null,
  external_calendar_id character varying(255) null,
  sync_status character varying(50) null default 'pending'::character varying,
  sync_attempts integer null default 0,
  last_sync_at timestamp with time zone null,
  sync_error text null,
  created_by uuid null,
  modified_by uuid null,
  created_at timestamp with time zone null default now(),
  updated_at timestamp with time zone null default now(),
  event_title character varying(255) null,
  event_description text null,
  event_location character varying(500) null,
  event_duration_minutes integer null,
  event_visibility character varying(50) null default 'default'::character varying,
  event_recurrence_rule text null,
  event_url character varying(500) null,
  event_attendees jsonb null,
  event_organizer jsonb null,
  event_metadata jsonb null,
  is_deleted boolean null default false,
  deleted_at timestamp with time zone null,
  deleted_by uuid null,
  deletion_reason text null,
  is_archived boolean null default false,
  archive_reason character varying(100) null,
  archive_date timestamp with time zone null,
  archive_review_date date null,
  law_firm_id uuid null,
  event_status character varying(50) null default 'confirmed'::character varying,
  constraint calendar_events_pkey primary key (event_id),
  constraint fk_calendar_events_tenant_id foreign KEY (law_firm_id) references tenants (tenant_id),
  constraint chk_event_status check (
    (
      (event_status)::text = any (
        (
          array[
            'tentative'::character varying,
            'confirmed'::character varying,
            'cancelled'::character varying,
            'declined'::character varying
          ]
        )::text[]
      )
    )
  ),
  constraint chk_event_visibility check (
    (
      (event_visibility)::text = any (
        (
          array[
            'default'::character varying,
            'public'::character varying,
            'private'::character varying,
            'confidential'::character varying
          ]
        )::text[]
      )
    )
  )
) TABLESPACE pg_default;

create index IF not exists idx_calendar_events_appointment_id on public.calendar_events using btree (appointment_id) TABLESPACE pg_default;

create index IF not exists idx_calendar_events_provider_type on public.calendar_events using btree (provider_type) TABLESPACE pg_default;

create index IF not exists idx_calendar_events_event_title on public.calendar_events using btree (event_title) TABLESPACE pg_default;

create index IF not exists idx_calendar_events_event_visibility on public.calendar_events using btree (event_visibility) TABLESPACE pg_default;

create index IF not exists idx_calendar_events_tenant_id on public.calendar_events using btree (law_firm_id) TABLESPACE pg_default;

create index IF not exists idx_calendar_events_event_status on public.calendar_events using btree (event_status) TABLESPACE pg_default;

create trigger update_calendar_events_updated_at BEFORE
update on calendar_events for EACH row
execute FUNCTION update_updated_at_column ();create table public.calendar_providers (
  calendar_provider_id uuid not null default gen_random_uuid (),
  law_firm_id uuid null,
  staff_id uuid null,
  provider_type character varying(50) not null,
  provider_name character varying(100) not null,
  access_token text null,
  refresh_token text null,
  token_expires_at timestamp without time zone null,
  settings jsonb null,
  is_active boolean null default true,
  is_default boolean null default false,
  created_by uuid null,
  modified_by uuid null,
  created_at timestamp without time zone null default CURRENT_TIMESTAMP,
  updated_at timestamp without time zone null default CURRENT_TIMESTAMP,
  access_token_encrypted text null,
  refresh_token_encrypted text null,
  last_sync_at timestamp with time zone null,
  sync_status character varying(50) null default 'pending'::character varying,
  provider_metadata jsonb null,
  is_deleted boolean null default false,
  deleted_at timestamp with time zone null,
  deleted_by uuid null,
  deletion_reason text null,
  is_archived boolean null default false,
  archive_reason character varying(100) null,
  archive_date timestamp with time zone null,
  archive_review_date date null,
  constraint calendar_providers_pkey primary key (calendar_provider_id),
  constraint valid_provider_type check (
    (
      (provider_type)::text = any (
        (
          array[
            'google'::character varying,
            'outlook'::character varying,
            'calendly'::character varying,
            'calcom'::character varying,
            'clio'::character varying,
            'truthline_internal'::character varying
          ]
        )::text[]
      )
    )
  )
) TABLESPACE pg_default;

create index IF not exists idx_calendar_providers_firm on public.calendar_providers using btree (law_firm_id) TABLESPACE pg_default;

create index IF not exists idx_calendar_providers_staff on public.calendar_providers using btree (staff_id) TABLESPACE pg_default;

create index IF not exists idx_calendar_providers_type on public.calendar_providers using btree (provider_type) TABLESPACE pg_default;

create index IF not exists idx_calendar_providers_sync_status on public.calendar_providers using btree (sync_status) TABLESPACE pg_default;

create index IF not exists idx_calendar_providers_is_default on public.calendar_providers using btree (is_default) TABLESPACE pg_default;

create trigger update_calendar_providers_updated_at BEFORE
update on calendar_providers for EACH row
execute FUNCTION update_updated_at_column ();create table public.client_intake_pipeline (
  intake_stage_id uuid not null default gen_random_uuid (),
  tenant_id uuid not null,
  stage_name character varying(100) not null,
  stage_code character varying(50) not null,
  display_order integer null default 0,
  is_default boolean null default false,
  is_terminal boolean null default false,
  color_code character varying(7) null,
  icon_name character varying(50) null,
  auto_followup_days integer null,
  trigger_webhook_url character varying(255) null,
  notes text null,
  is_active boolean null default true,
  is_deleted boolean null default false,
  is_archived boolean null default false,
  archive_reason character varying(100) null,
  archive_date timestamp with time zone null,
  archive_review_date date null,
  deleted_at timestamp with time zone null,
  deleted_by uuid null,
  deletion_reason text null,
  deletion_approval_required boolean null default true,
  deletion_approval_status character varying(20) null default 'pending'::character varying,
  deletion_approval_by uuid null,
  deletion_approval_at timestamp with time zone null,
  created_by uuid null,
  modified_by uuid null,
  created_at timestamp with time zone null default now(),
  updated_at timestamp with time zone null default now(),
  constraint client_intake_pipeline_pkey primary key (intake_stage_id),
  constraint fk_client_intake_pipeline_tenant_id foreign KEY (tenant_id) references tenants (tenant_id)
) TABLESPACE pg_default;

create index IF not exists idx_client_intake_pipeline_tenant on public.client_intake_pipeline using btree (tenant_id) TABLESPACE pg_default;

create index IF not exists idx_client_intake_pipeline_stage_code on public.client_intake_pipeline using btree (stage_code) TABLESPACE pg_default;

create index IF not exists idx_client_intake_pipeline_display_order on public.client_intake_pipeline using btree (display_order) TABLESPACE pg_default;

create index IF not exists idx_client_intake_pipeline_is_default on public.client_intake_pipeline using btree (is_default) TABLESPACE pg_default;

create index IF not exists idx_client_intake_pipeline_is_terminal on public.client_intake_pipeline using btree (is_terminal) TABLESPACE pg_default;

create index IF not exists idx_client_intake_pipeline_created on public.client_intake_pipeline using btree (created_at) TABLESPACE pg_default;

create index IF not exists idx_client_intake_pipeline_updated on public.client_intake_pipeline using btree (updated_at) TABLESPACE pg_default;

create index IF not exists idx_client_intake_pipeline_is_active on public.client_intake_pipeline using btree (is_active) TABLESPACE pg_default;

create index IF not exists idx_client_intake_pipeline_is_deleted on public.client_intake_pipeline using btree (is_deleted) TABLESPACE pg_default;create table public.communication_logs (
  log_id uuid not null default gen_random_uuid (),
  tenant_id uuid not null,
  entity_type character varying(100) not null,
  entity_id uuid not null,
  communication_type character varying(100) not null,
  communication_method character varying(50) not null,
  communication_content text null,
  communication_status character varying(50) null,
  timestamp timestamp with time zone null default now(),
  created_by uuid null,
  modified_by uuid null,
  created_at timestamp with time zone null default now(),
  updated_at timestamp with time zone null default now(),
  constraint communication_logs_pkey primary key (log_id)
) TABLESPACE pg_default;

create index IF not exists idx_communication_logs_tenant_id on public.communication_logs using btree (tenant_id) TABLESPACE pg_default;

create trigger update_communication_logs_updated_at BEFORE
update on communication_logs for EACH row
execute FUNCTION update_updated_at_column ();create table public.compliance_reports (
  report_id uuid not null default gen_random_uuid (),
  tenant_id uuid not null,
  report_type character varying(100) not null,
  report_period_start timestamp with time zone not null,
  report_period_end timestamp with time zone not null,
  report_data jsonb not null,
  report_status character varying(50) null default 'generated'::character varying,
  generated_at timestamp with time zone null default now(),
  created_by uuid null,
  modified_by uuid null,
  created_at timestamp with time zone null default now(),
  updated_at timestamp with time zone null default now(),
  constraint compliance_reports_pkey primary key (report_id)
) TABLESPACE pg_default;

create index IF not exists idx_compliance_reports_tenant_id on public.compliance_reports using btree (tenant_id) TABLESPACE pg_default;

create trigger update_compliance_reports_updated_at BEFORE
update on compliance_reports for EACH row
execute FUNCTION update_updated_at_column ();create table public.consent_records (
  consent_id uuid not null default gen_random_uuid (),
  tenant_id uuid not null,
  entity_type character varying(100) not null,
  entity_id uuid not null,
  consent_type character varying(100) not null,
  consent_status character varying(50) not null,
  consent_method character varying(100) null,
  consent_timestamp timestamp with time zone null default now(),
  consent_withdrawal_at timestamp with time zone null,
  consent_text text null,
  created_by uuid null,
  modified_by uuid null,
  created_at timestamp with time zone null default now(),
  updated_at timestamp with time zone null default now(),
  constraint consent_records_pkey primary key (consent_id)
) TABLESPACE pg_default;

create index IF not exists idx_consent_records_tenant_id on public.consent_records using btree (tenant_id) TABLESPACE pg_default;

create trigger update_consent_records_updated_at BEFORE
update on consent_records for EACH row
execute FUNCTION update_updated_at_column ();create table public.contacts (
  contact_id uuid not null default gen_random_uuid (),
  prefix character varying(20) null,
  first_name character varying(255) not null,
  middle_initials character varying(10) null,
  last_name character varying(255) not null,
  primary_email character varying(255) null,
  work_email character varying(255) null,
  cell_phone_number character varying(20) null,
  work_phone_number character varying(20) null,
  linkedin_url character varying(500) null,
  contact_type character varying(50) not null,
  law_firm_id uuid null,
  is_primary boolean null default false,
  is_archived boolean null default false,
  communication_preferences jsonb null,
  preferred_language character varying(10) null default 'en'::character varying,
  created_by uuid null,
  modified_by uuid null,
  created_at timestamp without time zone null default CURRENT_TIMESTAMP,
  updated_at timestamp without time zone null default CURRENT_TIMESTAMP,
  is_deleted boolean null default false,
  deleted_at timestamp with time zone null,
  deleted_by uuid null,
  deletion_reason text null,
  preferred_name character varying(255) null,
  date_of_birth date null,
  gender character varying(20) null,
  marital_status character varying(50) null,
  occupation character varying(100) null,
  nationality character varying(100) null,
  accessibility_needs text null,
  tags text[] null,
  status character varying(50) null default 'Active'::character varying,
  assigned_to uuid null,
  constraint contacts_pkey primary key (contact_id),
  constraint fk_contacts_tenant_id foreign KEY (law_firm_id) references tenants (tenant_id),
  constraint chk_contacts_marital_status check (
    (
      (marital_status)::text = any (
        (
          array[
            'Single'::character varying,
            'Married'::character varying,
            'Divorced'::character varying,
            'Widowed'::character varying,
            'Separated'::character varying,
            'Domestic Partnership'::character varying
          ]
        )::text[]
      )
    )
  ),
  constraint chk_contact_type check (
    (
      (contact_type)::text = any (
        (
          array[
            'lead'::character varying,
            'client'::character varying,
            'attorney'::character varying,
            'paralegal'::character varying,
            'staff'::character varying,
            'opposing_counsel'::character varying,
            'witness'::character varying,
            'vendor'::character varying,
            'referral'::character varying
          ]
        )::text[]
      )
    )
  ),
  constraint valid_contact_type check (
    (
      (contact_type)::text = any (
        (
          array[
            'lead'::character varying,
            'client'::character varying,
            'attorney'::character varying,
            'paralegal'::character varying,
            'staff'::character varying,
            'opposing_counsel'::character varying,
            'witness'::character varying,
            'vendor'::character varying,
            'referral'::character varying
          ]
        )::text[]
      )
    )
  ),
  constraint chk_contacts_status check (
    (
      (status)::text = any (
        (
          array[
            'Active'::character varying,
            'Inactive'::character varying,
            'Prospective'::character varying,
            'Former'::character varying,
            'Deceased'::character varying
          ]
        )::text[]
      )
    )
  ),
  constraint chk_contacts_gender check (
    (
      (gender)::text = any (
        (
          array[
            'Male'::character varying,
            'Female'::character varying,
            'Non-binary'::character varying,
            'Prefer not to say'::character varying,
            'Other'::character varying
          ]
        )::text[]
      )
    )
  )
) TABLESPACE pg_default;

create index IF not exists idx_contacts_law_firm on public.contacts using btree (law_firm_id) TABLESPACE pg_default;

create index IF not exists idx_contacts_type on public.contacts using btree (contact_type) TABLESPACE pg_default;

create index IF not exists idx_contacts_primary_email on public.contacts using btree (primary_email) TABLESPACE pg_default;

create index IF not exists idx_contacts_cell_phone on public.contacts using btree (cell_phone_number) TABLESPACE pg_default;

create index IF not exists idx_contacts_archived on public.contacts using btree (is_archived) TABLESPACE pg_default;

create index IF not exists idx_contacts_law_firm_id on public.contacts using btree (law_firm_id) TABLESPACE pg_default;

create index IF not exists idx_contacts_contact_type on public.contacts using btree (contact_type) TABLESPACE pg_default;

create index IF not exists idx_contacts_tenant_id on public.contacts using btree (law_firm_id) TABLESPACE pg_default;

create index IF not exists idx_contacts_is_primary on public.contacts using btree (is_primary) TABLESPACE pg_default;

create index IF not exists idx_contacts_status on public.contacts using btree (status) TABLESPACE pg_default;

create index IF not exists idx_contacts_assigned_to on public.contacts using btree (assigned_to) TABLESPACE pg_default;

create index IF not exists idx_contacts_date_of_birth on public.contacts using btree (date_of_birth) TABLESPACE pg_default;

create trigger update_contacts_updated_at BEFORE
update on contacts for EACH row
execute FUNCTION update_updated_at_column ();create table public.data_retention_policies (
  policy_id uuid not null default gen_random_uuid (),
  tenant_id uuid not null,
  data_type character varying(100) not null,
  retention_period_days integer not null,
  retention_action character varying(100) not null,
  is_active boolean null default true,
  last_executed_at timestamp with time zone null,
  created_by uuid null,
  modified_by uuid null,
  created_at timestamp with time zone null default now(),
  updated_at timestamp with time zone null default now(),
  constraint data_retention_policies_pkey primary key (policy_id)
) TABLESPACE pg_default;

create index IF not exists idx_data_retention_policies_tenant_id on public.data_retention_policies using btree (tenant_id) TABLESPACE pg_default;

create trigger update_data_retention_policies_updated_at BEFORE
update on data_retention_policies for EACH row
execute FUNCTION update_updated_at_column ();create table public.email_messages (
  email_id uuid not null default gen_random_uuid (),
  tenant_id uuid not null,
  recipient_email character varying(255) not null,
  sender_email character varying(255) null,
  subject character varying(255) not null,
  email_content text not null,
  email_type character varying(100) null,
  email_status character varying(50) null default 'pending'::character varying,
  sent_at timestamp with time zone null,
  delivered_at timestamp with time zone null,
  error_message text null,
  session_id uuid null,
  appointment_id uuid null,
  created_by uuid null,
  modified_by uuid null,
  created_at timestamp with time zone null default now(),
  updated_at timestamp with time zone null default now(),
  constraint email_messages_pkey primary key (email_id)
) TABLESPACE pg_default;

create index IF not exists idx_email_messages_tenant_id on public.email_messages using btree (tenant_id) TABLESPACE pg_default;

create trigger update_email_messages_updated_at BEFORE
update on email_messages for EACH row
execute FUNCTION update_updated_at_column ();create table public.engagement_letter_templates (
  template_id uuid not null default gen_random_uuid (),
  tenant_id uuid not null,
  template_name character varying(255) not null,
  template_type character varying(50) not null,
  template_content text not null,
  template_variables jsonb null,
  practice_area_id uuid null,
  include_booking_link boolean null default false,
  booking_link_text character varying(255) null,
  is_active boolean null default true,
  version integer null default 1,
  previous_version_id uuid null,
  is_deleted boolean null default false,
  is_archived boolean null default false,
  archive_reason character varying(100) null,
  archive_date timestamp with time zone null,
  deleted_at timestamp with time zone null,
  deleted_by uuid null,
  created_by uuid null,
  modified_by uuid null,
  created_at timestamp with time zone null default now(),
  updated_at timestamp with time zone null default now(),
  constraint engagement_letter_templates_pkey primary key (template_id),
  constraint fk_engagement_letter_templates_practice_area_id foreign KEY (practice_area_id) references practice_areas (practice_area_id),
  constraint fk_engagement_letter_templates_tenant_id foreign KEY (tenant_id) references tenants (tenant_id),
  constraint chk_engagement_letter_templates_template_type check (
    (
      (template_type)::text = any (
        (
          array[
            'engagement_letter'::character varying,
            'retainer_agreement'::character varying,
            'fee_agreement'::character varying,
            'terms_of_service'::character varying,
            'consent_form'::character varying
          ]
        )::text[]
      )
    )
  )
) TABLESPACE pg_default;

create index IF not exists idx_engagement_letter_templates_tenant on public.engagement_letter_templates using btree (tenant_id) TABLESPACE pg_default;

create index IF not exists idx_engagement_letter_templates_practice_area on public.engagement_letter_templates using btree (practice_area_id) TABLESPACE pg_default;

create index IF not exists idx_engagement_letter_templates_template_type on public.engagement_letter_templates using btree (template_type) TABLESPACE pg_default;

create index IF not exists idx_engagement_letter_templates_is_active on public.engagement_letter_templates using btree (is_active) TABLESPACE pg_default;

create index IF not exists idx_engagement_letter_templates_created on public.engagement_letter_templates using btree (created_at) TABLESPACE pg_default;create table public.engagement_letter_tracking (
  tracking_id uuid not null default gen_random_uuid (),
  tenant_id uuid not null,
  lead_id uuid not null,
  session_id uuid null,
  template_id uuid not null,
  delivery_method character varying(50) not null,
  recipient_email character varying(255) null,
  recipient_phone character varying(50) null,
  document_link character varying(500) not null,
  link_expiry_date timestamp with time zone null,
  sent_at timestamp with time zone null default now(),
  viewed_at timestamp with time zone null,
  signed_at timestamp with time zone null,
  returned_at timestamp with time zone null,
  booking_clicked_at timestamp with time zone null,
  status character varying(50) null default 'sent'::character varying,
  reminder_count integer null default 0,
  last_reminder_at timestamp with time zone null,
  notes text null,
  is_deleted boolean null default false,
  deleted_at timestamp with time zone null,
  deleted_by uuid null,
  created_by uuid null,
  modified_by uuid null,
  created_at timestamp with time zone null default now(),
  updated_at timestamp with time zone null default now(),
  constraint engagement_letter_tracking_pkey primary key (tracking_id),
  constraint fk_engagement_letter_tracking_lead_id foreign KEY (lead_id) references intake_leads (lead_id),
  constraint fk_engagement_letter_tracking_template_id foreign KEY (template_id) references engagement_letter_templates (template_id),
  constraint fk_engagement_letter_tracking_tenant_id foreign KEY (tenant_id) references tenants (tenant_id),
  constraint fk_engagement_letter_tracking_session_id foreign KEY (session_id) references intake_sessions (session_id),
  constraint chk_engagement_letter_tracking_status check (
    (
      (status)::text = any (
        (
          array[
            'sent'::character varying,
            'viewed'::character varying,
            'signed'::character varying,
            'returned'::character varying,
            'expired'::character varying,
            'cancelled'::character varying
          ]
        )::text[]
      )
    )
  ),
  constraint chk_engagement_letter_tracking_delivery_method check (
    (
      (delivery_method)::text = any (
        (
          array[
            'email'::character varying,
            'sms'::character varying,
            'both'::character varying
          ]
        )::text[]
      )
    )
  )
) TABLESPACE pg_default;

create index IF not exists idx_engagement_letter_tracking_tenant on public.engagement_letter_tracking using btree (tenant_id) TABLESPACE pg_default;

create index IF not exists idx_engagement_letter_tracking_lead on public.engagement_letter_tracking using btree (lead_id) TABLESPACE pg_default;

create index IF not exists idx_engagement_letter_tracking_session on public.engagement_letter_tracking using btree (session_id) TABLESPACE pg_default;

create index IF not exists idx_engagement_letter_tracking_template on public.engagement_letter_tracking using btree (template_id) TABLESPACE pg_default;

create index IF not exists idx_engagement_letter_tracking_status on public.engagement_letter_tracking using btree (status) TABLESPACE pg_default;

create index IF not exists idx_engagement_letter_tracking_sent_at on public.engagement_letter_tracking using btree (sent_at) TABLESPACE pg_default;

create index IF not exists idx_engagement_letter_tracking_viewed_at on public.engagement_letter_tracking using btree (viewed_at) TABLESPACE pg_default;

create index IF not exists idx_engagement_letter_tracking_signed_at on public.engagement_letter_tracking using btree (signed_at) TABLESPACE pg_default;create table public.intake_follow_up_actions (
  follow_up_action_id uuid not null default gen_random_uuid (),
  lead_id uuid not null,
  tenant_id uuid not null,
  assigned_to_user_id uuid null,
  action_type character varying(50) not null,
  action_description text null,
  due_date timestamp with time zone null,
  completed_at timestamp with time zone null,
  completion_status character varying(20) null default 'Pending'::character varying,
  completion_notes text null,
  priority_level integer null default 3,
  is_deleted boolean null default false,
  is_archived boolean null default false,
  archive_reason character varying(100) null,
  archive_date timestamp with time zone null,
  archive_review_date date null,
  deleted_at timestamp with time zone null,
  deleted_by uuid null,
  deletion_reason text null,
  created_by uuid null,
  modified_by uuid null,
  created_at timestamp with time zone null default now(),
  updated_at timestamp with time zone null default now(),
  constraint intake_follow_up_actions_pkey primary key (follow_up_action_id),
  constraint fk_intake_follow_up_actions_lead_id foreign KEY (lead_id) references intake_leads (lead_id),
  constraint fk_intake_follow_up_actions_tenant_id foreign KEY (tenant_id) references tenants (tenant_id),
  constraint chk_follow_up_actions_action_type check (
    (
      (action_type)::text = any (
        (
          array[
            'call'::character varying,
            'email'::character varying,
            'sms'::character varying,
            'meeting'::character varying,
            'document_review'::character varying,
            'follow_up'::character varying,
            'other'::character varying
          ]
        )::text[]
      )
    )
  ),
  constraint chk_follow_up_actions_completion_status check (
    (
      (completion_status)::text = any (
        (
          array[
            'Pending'::character varying,
            'In Progress'::character varying,
            'Completed'::character varying,
            'Cancelled'::character varying
          ]
        )::text[]
      )
    )
  ),
  constraint chk_follow_up_actions_priority_level check (
    (
      (priority_level >= 1)
      and (priority_level <= 5)
    )
  )
) TABLESPACE pg_default;

create index IF not exists idx_follow_up_actions_tenant on public.intake_follow_up_actions using btree (tenant_id) TABLESPACE pg_default;

create index IF not exists idx_follow_up_actions_lead on public.intake_follow_up_actions using btree (lead_id) TABLESPACE pg_default;

create index IF not exists idx_follow_up_actions_assigned_to on public.intake_follow_up_actions using btree (assigned_to_user_id) TABLESPACE pg_default;

create index IF not exists idx_follow_up_actions_action_type on public.intake_follow_up_actions using btree (action_type) TABLESPACE pg_default;

create index IF not exists idx_follow_up_actions_due_date on public.intake_follow_up_actions using btree (due_date) TABLESPACE pg_default;

create index IF not exists idx_follow_up_actions_completion_status on public.intake_follow_up_actions using btree (completion_status) TABLESPACE pg_default;

create index IF not exists idx_follow_up_actions_priority_level on public.intake_follow_up_actions using btree (priority_level) TABLESPACE pg_default;

create index IF not exists idx_follow_up_actions_created on public.intake_follow_up_actions using btree (created_at) TABLESPACE pg_default;

create index IF not exists idx_follow_up_actions_updated on public.intake_follow_up_actions using btree (updated_at) TABLESPACE pg_default;

create index IF not exists idx_follow_up_actions_is_deleted on public.intake_follow_up_actions using btree (is_deleted) TABLESPACE pg_default;create table public.intake_leads (
  lead_id uuid not null default gen_random_uuid (),
  tenant_id uuid not null,
  session_id uuid not null,
  lead_source_id uuid null,
  practice_area character varying(100) null,
  lead_status character varying(50) null default 'new'::character varying,
  priority_level integer null default 3,
  caller_name character varying(255) null,
  caller_phone character varying(50) null,
  caller_email character varying(255) null,
  case_summary text null,
  estimated_value numeric(12, 2) null,
  assigned_attorney_id uuid null,
  notes text null,
  created_by uuid null,
  modified_by uuid null,
  created_at timestamp with time zone null default now(),
  updated_at timestamp with time zone null default now(),
  client_stage character varying(50) null default 'prospect'::character varying,
  follow_up_required boolean null default false,
  follow_up_date date null,
  follow_up_notes text null,
  constraint intake_leads_pkey primary key (lead_id),
  constraint chk_intake_leads_client_stage check (
    (
      (client_stage)::text = any (
        (
          array[
            'prospect'::character varying,
            'contacted'::character varying,
            'qualified'::character varying,
            'consultation_scheduled'::character varying,
            'retained'::character varying,
            'declined'::character varying,
            'lost'::character varying
          ]
        )::text[]
      )
    )
  )
) TABLESPACE pg_default;

create index IF not exists idx_intake_leads_tenant_id on public.intake_leads using btree (tenant_id) TABLESPACE pg_default;

create index IF not exists idx_intake_leads_status on public.intake_leads using btree (lead_status) TABLESPACE pg_default;

create index IF not exists idx_intake_leads_client_stage on public.intake_leads using btree (client_stage) TABLESPACE pg_default;

create index IF not exists idx_intake_leads_follow_up_required on public.intake_leads using btree (follow_up_required) TABLESPACE pg_default;

create index IF not exists idx_intake_leads_follow_up_date on public.intake_leads using btree (follow_up_date) TABLESPACE pg_default;

create trigger update_intake_leads_updated_at BEFORE
update on intake_leads for EACH row
execute FUNCTION update_updated_at_column ();create table public.intake_questions (
  question_id uuid not null default gen_random_uuid (),
  tenant_id uuid null,
  state_name character varying(100) not null,
  question_text text not null,
  options jsonb null,
  validation_rules jsonb null,
  display_order integer null,
  is_active boolean null default true,
  practice_area character varying(100) null,
  created_by uuid null,
  modified_by uuid null,
  created_at timestamp with time zone null default now(),
  updated_at timestamp with time zone null default now(),
  constraint intake_questions_pkey primary key (question_id)
) TABLESPACE pg_default;

create index IF not exists idx_intake_questions_tenant_id on public.intake_questions using btree (tenant_id) TABLESPACE pg_default;

create index IF not exists idx_intake_questions_state_name on public.intake_questions using btree (state_name) TABLESPACE pg_default;

create trigger update_intake_questions_updated_at BEFORE
update on intake_questions for EACH row
execute FUNCTION update_updated_at_column ();create table public.intake_responses (
  response_id uuid not null default gen_random_uuid (),
  session_id uuid not null,
  question_id uuid null,
  state_name character varying(100) not null,
  response_value character varying(255) null,
  response_text text null,
  response_timestamp timestamp with time zone null default now(),
  created_by uuid null,
  modified_by uuid null,
  created_at timestamp with time zone null default now(),
  updated_at timestamp with time zone null default now(),
  constraint intake_responses_pkey primary key (response_id)
) TABLESPACE pg_default;

create index IF not exists idx_intake_responses_session_id on public.intake_responses using btree (session_id) TABLESPACE pg_default;

create trigger update_intake_responses_updated_at BEFORE
update on intake_responses for EACH row
execute FUNCTION update_updated_at_column ();create table public.intake_sessions (
  session_id uuid not null default gen_random_uuid (),
  tenant_id uuid not null,
  caller_phone character varying(50) null,
  caller_name character varying(255) null,
  session_status character varying(50) null default 'active'::character varying,
  current_state character varying(100) null,
  practice_area character varying(100) null,
  session_data jsonb null,
  started_at timestamp with time zone null default now(),
  ended_at timestamp with time zone null,
  duration_seconds integer null,
  created_by uuid null,
  modified_by uuid null,
  created_at timestamp with time zone null default now(),
  updated_at timestamp with time zone null default now(),
  engagement_letter_sent boolean null default false,
  engagement_letter_sent_at timestamp with time zone null,
  engagement_letter_viewed boolean null default false,
  engagement_letter_signed boolean null default false,
  booking_preference character varying(50) null,
  next_steps_confirmed boolean null default false,
  next_steps_confirmed_at timestamp with time zone null,
  attendance_concern_noted boolean null default false,
  social_media_invite_offered boolean null default false,
  documents_reminder_sent boolean null default false,
  is_returning_caller boolean null default false,
  contact_lookup_attempted boolean null default false,
  contact_found boolean null default false,
  returning_caller_request_type character varying(100) null,
  reschedule_requested boolean null default false,
  reschedule_completed boolean null default false,
  reschedule_reason text null,
  original_appointment_id uuid null,
  new_appointment_id uuid null,
  constraint intake_sessions_pkey primary key (session_id),
  constraint fk_intake_sessions_new_appointment_id foreign KEY (new_appointment_id) references appointments (appointment_id),
  constraint fk_intake_sessions_original_appointment_id foreign KEY (original_appointment_id) references appointments (appointment_id),
  constraint chk_intake_sessions_booking_preference check (
    (
      (booking_preference)::text = any (
        (
          array[
            'direct_booking'::character varying,
            'engagement_letter_first'::character varying,
            'engagement_letter_with_link'::character varying,
            'call_back_later'::character varying
          ]
        )::text[]
      )
    )
  )
) TABLESPACE pg_default;

create index IF not exists idx_intake_sessions_tenant_id on public.intake_sessions using btree (tenant_id) TABLESPACE pg_default;

create index IF not exists idx_intake_sessions_status on public.intake_sessions using btree (session_status) TABLESPACE pg_default;

create index IF not exists idx_intake_sessions_engagement_letter_sent on public.intake_sessions using btree (engagement_letter_sent) TABLESPACE pg_default;

create index IF not exists idx_intake_sessions_engagement_letter_viewed on public.intake_sessions using btree (engagement_letter_viewed) TABLESPACE pg_default;

create index IF not exists idx_intake_sessions_engagement_letter_signed on public.intake_sessions using btree (engagement_letter_signed) TABLESPACE pg_default;

create index IF not exists idx_intake_sessions_booking_preference on public.intake_sessions using btree (booking_preference) TABLESPACE pg_default;

create index IF not exists idx_intake_sessions_next_steps_confirmed on public.intake_sessions using btree (next_steps_confirmed) TABLESPACE pg_default;

create index IF not exists idx_intake_sessions_attendance_concern_noted on public.intake_sessions using btree (attendance_concern_noted) TABLESPACE pg_default;

create index IF not exists idx_intake_sessions_social_media_invite_offered on public.intake_sessions using btree (social_media_invite_offered) TABLESPACE pg_default;

create index IF not exists idx_intake_sessions_is_returning_caller on public.intake_sessions using btree (is_returning_caller) TABLESPACE pg_default;

create index IF not exists idx_intake_sessions_contact_lookup_attempted on public.intake_sessions using btree (contact_lookup_attempted) TABLESPACE pg_default;

create index IF not exists idx_intake_sessions_contact_found on public.intake_sessions using btree (contact_found) TABLESPACE pg_default;

create index IF not exists idx_intake_sessions_returning_caller_request_type on public.intake_sessions using btree (returning_caller_request_type) TABLESPACE pg_default;

create index IF not exists idx_intake_sessions_reschedule_requested on public.intake_sessions using btree (reschedule_requested) TABLESPACE pg_default;

create index IF not exists idx_intake_sessions_reschedule_completed on public.intake_sessions using btree (reschedule_completed) TABLESPACE pg_default;

create index IF not exists idx_intake_sessions_original_appointment_id on public.intake_sessions using btree (original_appointment_id) TABLESPACE pg_default;

create index IF not exists idx_intake_sessions_new_appointment_id on public.intake_sessions using btree (new_appointment_id) TABLESPACE pg_default;

create trigger update_intake_sessions_updated_at BEFORE
update on intake_sessions for EACH row
execute FUNCTION update_updated_at_column ();create table public.law_firm_practice_areas (
  law_firm_practice_area_id uuid not null default gen_random_uuid (),
  law_firm_id uuid null,
  practice_area_id uuid null,
  is_primary boolean null default false,
  internal_priority_level integer null default 5,
  custom_greeting_override text null,
  assigned_attorney_name character varying(255) null,
  notes text null,
  created_by uuid null,
  modified_by uuid null,
  created_at timestamp without time zone null default CURRENT_TIMESTAMP,
  updated_at timestamp without time zone null default CURRENT_TIMESTAMP,
  constraint law_firm_practice_areas_pkey primary key (law_firm_practice_area_id),
  constraint law_firm_practice_areas_practice_area_id_fkey foreign KEY (practice_area_id) references practice_areas (practice_area_id)
) TABLESPACE pg_default;

create index IF not exists idx_law_firm_practice_areas_firm on public.law_firm_practice_areas using btree (law_firm_id) TABLESPACE pg_default;

create index IF not exists idx_law_firm_practice_areas_area on public.law_firm_practice_areas using btree (practice_area_id) TABLESPACE pg_default;

create trigger update_law_firm_practice_areas_updated_at BEFORE
update on law_firm_practice_areas for EACH row
execute FUNCTION update_updated_at_column ();create table public.lead_analytics (
  analytics_id uuid not null default gen_random_uuid (),
  tenant_id uuid not null,
  lead_id uuid not null,
  lead_source character varying(100) null,
  practice_area character varying(100) null,
  estimated_value numeric(12, 2) null,
  conversion_time integer null,
  appointment_scheduled boolean null default false,
  appointment_attended boolean null default false,
  case_value numeric(12, 2) null,
  created_at timestamp with time zone null default now(),
  constraint lead_analytics_pkey primary key (analytics_id)
) TABLESPACE pg_default;

create index IF not exists idx_lead_analytics_tenant_id on public.lead_analytics using btree (tenant_id) TABLESPACE pg_default;create table public.lead_sources (
  lead_source_id uuid not null default gen_random_uuid (),
  source_name character varying(255) not null,
  source_type character varying(100) not null,
  source_description text null,
  is_active boolean null default true,
  tracking_code character varying(100) null,
  created_by uuid null,
  modified_by uuid null,
  created_at timestamp with time zone null default now(),
  updated_at timestamp with time zone null default now(),
  constraint lead_sources_pkey primary key (lead_source_id)
) TABLESPACE pg_default;

create trigger update_lead_sources_updated_at BEFORE
update on lead_sources for EACH row
execute FUNCTION update_updated_at_column ();create table public.performance_metrics (
  metric_id uuid not null default gen_random_uuid (),
  tenant_id uuid null,
  metric_name character varying(255) not null,
  metric_value numeric(15, 4) not null,
  metric_unit character varying(50) null,
  metric_category character varying(100) null,
  recorded_at timestamp with time zone null default now(),
  created_by uuid null,
  modified_by uuid null,
  created_at timestamp with time zone null default now(),
  updated_at timestamp with time zone null default now(),
  constraint performance_metrics_pkey primary key (metric_id)
) TABLESPACE pg_default;

create index IF not exists idx_performance_metrics_tenant_id on public.performance_metrics using btree (tenant_id) TABLESPACE pg_default;

create trigger update_performance_metrics_updated_at BEFORE
update on performance_metrics for EACH row
execute FUNCTION update_updated_at_column ();create table public.practice_area_hierarchy (
  practice_area_hierarchy_id uuid not null default gen_random_uuid (),
  practice_area_hierarchy_name character varying(255) not null,
  parent_hierarchy_name character varying(255) null,
  description text null,
  area_code character varying(50) null,
  category character varying(100) null,
  jurisdiction_level character varying(50) null,
  specialization_level character varying(20) null,
  required_qualifications text[] null,
  typical_case_types text[] null,
  ai_tagging_keywords text[] null,
  ai_use_case_notes text null,
  law_firm_id uuid null,
  is_active boolean null default true,
  is_deleted boolean null default false,
  is_archived boolean null default false,
  archive_reason character varying(100) null,
  archive_date timestamp with time zone null,
  archive_review_date date null,
  deleted_at timestamp with time zone null,
  deleted_by uuid null,
  deletion_reason text null,
  deletion_approval_required boolean null default true,
  deletion_approval_status character varying(20) null default 'pending'::character varying,
  deletion_approval_by uuid null,
  deletion_approval_at timestamp with time zone null,
  created_by uuid null,
  modified_by uuid null,
  created_at timestamp with time zone null default now(),
  updated_at timestamp with time zone null default now(),
  constraint practice_area_hierarchy_pkey primary key (practice_area_hierarchy_id),
  constraint practice_area_hierarchy_practice_area_hierarchy_name_key unique (practice_area_hierarchy_name),
  constraint fk_practice_area_hierarchy_law_firm_id foreign KEY (law_firm_id) references tenants (tenant_id)
) TABLESPACE pg_default;

create index IF not exists idx_practice_area_hierarchy_parent on public.practice_area_hierarchy using btree (parent_hierarchy_name) TABLESPACE pg_default;

create index IF not exists idx_practice_area_hierarchy_category on public.practice_area_hierarchy using btree (category) TABLESPACE pg_default;

create index IF not exists idx_practice_area_hierarchy_law_firm on public.practice_area_hierarchy using btree (law_firm_id) TABLESPACE pg_default;

create index IF not exists idx_practice_area_hierarchy_specialization on public.practice_area_hierarchy using btree (specialization_level) TABLESPACE pg_default;

create index IF not exists idx_practice_area_hierarchy_created on public.practice_area_hierarchy using btree (created_at) TABLESPACE pg_default;

create index IF not exists idx_practice_area_hierarchy_updated on public.practice_area_hierarchy using btree (updated_at) TABLESPACE pg_default;

create index IF not exists idx_practice_area_hierarchy_is_active on public.practice_area_hierarchy using btree (is_active) TABLESPACE pg_default;

create index IF not exists idx_practice_area_hierarchy_is_deleted on public.practice_area_hierarchy using btree (is_deleted) TABLESPACE pg_default;create table public.practice_area_specializations (
  specialization_id uuid not null default gen_random_uuid (),
  practice_area_hierarchy_id uuid not null,
  service_id uuid null,
  specialization_name character varying(255) not null,
  description text null,
  jurisdiction_level character varying(50) null,
  category character varying(100) null,
  internal_priority_level integer null,
  notes text null,
  ai_specialization_tags text[] null,
  ai_tagging_keywords text[] null,
  ai_use_case_notes text null,
  ai_custom_routing_json jsonb null,
  law_firm_id uuid null,
  is_active boolean null default true,
  is_public boolean null default true,
  is_deleted boolean null default false,
  is_archived boolean null default false,
  archive_reason character varying(100) null,
  archive_date timestamp with time zone null,
  archive_review_date date null,
  deleted_at timestamp with time zone null,
  deleted_by uuid null,
  deletion_reason text null,
  deletion_approval_required boolean null default true,
  deletion_approval_status character varying(20) null default 'pending'::character varying,
  deletion_approval_by uuid null,
  deletion_approval_at timestamp with time zone null,
  created_by uuid null,
  modified_by uuid null,
  created_at timestamp with time zone null default now(),
  updated_at timestamp with time zone null default now(),
  constraint practice_area_specializations_pkey primary key (specialization_id),
  constraint fk_practice_area_specializations_hierarchy_id foreign KEY (practice_area_hierarchy_id) references practice_area_hierarchy (practice_area_hierarchy_id),
  constraint fk_practice_area_specializations_law_firm_id foreign KEY (law_firm_id) references tenants (tenant_id),
  constraint chk_specializations_internal_priority_level check (
    (
      (internal_priority_level >= 1)
      and (internal_priority_level <= 10)
    )
  )
) TABLESPACE pg_default;

create index IF not exists idx_specializations_hierarchy on public.practice_area_specializations using btree (practice_area_hierarchy_id) TABLESPACE pg_default;

create index IF not exists idx_specializations_service on public.practice_area_specializations using btree (service_id) TABLESPACE pg_default;

create index IF not exists idx_specializations_law_firm on public.practice_area_specializations using btree (law_firm_id) TABLESPACE pg_default;

create index IF not exists idx_specializations_category on public.practice_area_specializations using btree (category) TABLESPACE pg_default;

create index IF not exists idx_specializations_priority on public.practice_area_specializations using btree (internal_priority_level) TABLESPACE pg_default;

create index IF not exists idx_specializations_created on public.practice_area_specializations using btree (created_at) TABLESPACE pg_default;

create index IF not exists idx_specializations_updated on public.practice_area_specializations using btree (updated_at) TABLESPACE pg_default;

create index IF not exists idx_specializations_is_active on public.practice_area_specializations using btree (is_active) TABLESPACE pg_default;

create index IF not exists idx_specializations_is_public on public.practice_area_specializations using btree (is_public) TABLESPACE pg_default;

create index IF not exists idx_specializations_is_deleted on public.practice_area_specializations using btree (is_deleted) TABLESPACE pg_default;create table public.practice_areas (
  practice_area_id uuid not null default gen_random_uuid (),
  name character varying(255) not null,
  area_code character varying(50) not null,
  description text null,
  category character varying(100) null,
  is_active boolean null default true,
  is_public boolean null default true,
  display_order integer null,
  created_by uuid null,
  modified_by uuid null,
  created_at timestamp without time zone null default CURRENT_TIMESTAMP,
  updated_at timestamp without time zone null default CURRENT_TIMESTAMP,
  jurisdiction_level character varying(50) null,
  parent_id uuid null,
  practice_type character varying(50) null,
  specialization_level character varying(20) null,
  required_qualifications text[] null,
  typical_case_types text[] null,
  color_code character varying(7) null,
  icon_name character varying(50) null,
  ai_tagging_keywords text[] null,
  ai_use_case_notes text null,
  constraint practice_areas_pkey primary key (practice_area_id),
  constraint practice_areas_area_code_key unique (area_code),
  constraint practice_areas_name_key unique (name),
  constraint fk_practice_areas_parent_id foreign KEY (parent_id) references practice_areas (practice_area_id),
  constraint chk_practice_areas_practice_type check (
    (
      (practice_type)::text = any (
        (
          array[
            'litigation'::character varying,
            'transactional'::character varying,
            'regulatory'::character varying,
            'advisory'::character varying,
            'compliance'::character varying,
            'other'::character varying
          ]
        )::text[]
      )
    )
  ),
  constraint chk_practice_areas_specialization_level check (
    (
      (specialization_level)::text = any (
        (
          array[
            'general'::character varying,
            'specialized'::character varying,
            'expert'::character varying
          ]
        )::text[]
      )
    )
  )
) TABLESPACE pg_default;

create index IF not exists idx_practice_areas_code on public.practice_areas using btree (area_code) TABLESPACE pg_default;

create index IF not exists idx_practice_areas_category on public.practice_areas using btree (category) TABLESPACE pg_default;

create index IF not exists idx_practice_areas_active on public.practice_areas using btree (is_active) TABLESPACE pg_default;

create index IF not exists idx_practice_areas_area_code on public.practice_areas using btree (area_code) TABLESPACE pg_default;

create index IF not exists idx_practice_areas_jurisdiction_level on public.practice_areas using btree (jurisdiction_level) TABLESPACE pg_default;

create index IF not exists idx_practice_areas_parent_id on public.practice_areas using btree (parent_id) TABLESPACE pg_default;

create index IF not exists idx_practice_areas_practice_type on public.practice_areas using btree (practice_type) TABLESPACE pg_default;

create index IF not exists idx_practice_areas_specialization_level on public.practice_areas using btree (specialization_level) TABLESPACE pg_default;

create trigger update_practice_areas_updated_at BEFORE
update on practice_areas for EACH row
execute FUNCTION update_updated_at_column ();create table public.providers (
  provider_id uuid not null default gen_random_uuid (),
  provider_name character varying(100) not null,
  provider_type character varying(50) not null,
  provider_domain character varying(255) null,
  api_endpoint character varying(500) null,
  api_version character varying(20) null,
  provider_description text null,
  provider_metadata jsonb null,
  is_active boolean null default true,
  is_deleted boolean null default false,
  is_archived boolean null default false,
  archive_reason character varying(100) null,
  archive_date timestamp with time zone null,
  archive_review_date date null,
  deleted_at timestamp with time zone null,
  deleted_by uuid null,
  deletion_reason text null,
  deletion_approval_required boolean null default true,
  deletion_approval_status character varying(20) null default 'pending'::character varying,
  deletion_approval_by uuid null,
  deletion_approval_at timestamp with time zone null,
  created_by uuid null,
  modified_by uuid null,
  created_at timestamp with time zone null default now(),
  updated_at timestamp with time zone null default now(),
  constraint providers_pkey primary key (provider_id),
  constraint providers_provider_name_key unique (provider_name),
  constraint chk_providers_provider_type check (
    (
      (provider_type)::text = any (
        (
          array[
            'calendar'::character varying,
            'sms'::character varying,
            'email'::character varying,
            'storage'::character varying,
            'payment'::character varying,
            'crm'::character varying,
            'other'::character varying
          ]
        )::text[]
      )
    )
  )
) TABLESPACE pg_default;

create index IF not exists idx_providers_provider_type on public.providers using btree (provider_type) TABLESPACE pg_default;

create index IF not exists idx_providers_is_active on public.providers using btree (is_active) TABLESPACE pg_default;

create index IF not exists idx_providers_created on public.providers using btree (created_at) TABLESPACE pg_default;

create index IF not exists idx_providers_updated on public.providers using btree (updated_at) TABLESPACE pg_default;

create index IF not exists idx_providers_is_deleted on public.providers using btree (is_deleted) TABLESPACE pg_default;create table public.returning_caller_sessions (
  session_id uuid not null default gen_random_uuid (),
  tenant_id uuid not null,
  caller_first_name character varying(255) null,
  caller_email character varying(255) null,
  caller_phone character varying(50) null,
  contact_id uuid null,
  contact_found boolean null default false,
  lookup_attempts integer null default 0,
  lookup_method character varying(50) null,
  request_type character varying(100) null,
  previous_appointment_id uuid null,
  previous_lead_id uuid null,
  database_error boolean null default false,
  fallback_used boolean null default false,
  notes text null,
  is_deleted boolean null default false,
  deleted_at timestamp with time zone null,
  deleted_by uuid null,
  created_by uuid null,
  modified_by uuid null,
  created_at timestamp with time zone null default now(),
  updated_at timestamp with time zone null default now(),
  constraint returning_caller_sessions_pkey primary key (session_id),
  constraint fk_returning_caller_sessions_contact_id foreign KEY (contact_id) references contacts (contact_id),
  constraint fk_returning_caller_sessions_previous_appointment foreign KEY (previous_appointment_id) references appointments (appointment_id),
  constraint fk_returning_caller_sessions_previous_lead foreign KEY (previous_lead_id) references intake_leads (lead_id),
  constraint fk_returning_caller_sessions_tenant_id foreign KEY (tenant_id) references tenants (tenant_id),
  constraint chk_returning_caller_sessions_lookup_method check (
    (
      (lookup_method)::text = any (
        (
          array[
            'email'::character varying,
            'phone'::character varying,
            'both'::character varying,
            'manual'::character varying,
            'none'::character varying
          ]
        )::text[]
      )
    )
  ),
  constraint chk_returning_caller_sessions_request_type check (
    (
      (request_type)::text = any (
        (
          array[
            'reschedule'::character varying,
            'new_booking'::character varying,
            'general_inquiry'::character varying,
            'status_check'::character varying,
            'other'::character varying
          ]
        )::text[]
      )
    )
  )
) TABLESPACE pg_default;

create index IF not exists idx_returning_caller_sessions_tenant on public.returning_caller_sessions using btree (tenant_id) TABLESPACE pg_default;

create index IF not exists idx_returning_caller_sessions_contact on public.returning_caller_sessions using btree (contact_id) TABLESPACE pg_default;

create index IF not exists idx_returning_caller_sessions_caller_email on public.returning_caller_sessions using btree (caller_email) TABLESPACE pg_default;

create index IF not exists idx_returning_caller_sessions_caller_phone on public.returning_caller_sessions using btree (caller_phone) TABLESPACE pg_default;

create index IF not exists idx_returning_caller_sessions_request_type on public.returning_caller_sessions using btree (request_type) TABLESPACE pg_default;

create index IF not exists idx_returning_caller_sessions_contact_found on public.returning_caller_sessions using btree (contact_found) TABLESPACE pg_default;

create index IF not exists idx_returning_caller_sessions_created_at on public.returning_caller_sessions using btree (created_at) TABLESPACE pg_default;create table public.role_change_logs (
  role_change_log_id uuid not null default gen_random_uuid (),
  user_profile_id uuid null,
  law_firm_id uuid null,
  previous_role_id uuid null,
  new_role_id uuid null,
  permission_diffs jsonb null,
  change_reason text null,
  change_method character varying(50) null,
  changed_by uuid null,
  created_at timestamp without time zone null default CURRENT_TIMESTAMP,
  constraint role_change_logs_pkey primary key (role_change_log_id)
) TABLESPACE pg_default;

create index IF not exists idx_role_change_firm on public.role_change_logs using btree (law_firm_id) TABLESPACE pg_default;

create index IF not exists idx_role_change_date on public.role_change_logs using btree (created_at desc) TABLESPACE pg_default;

create index IF not exists idx_role_change_user on public.role_change_logs using btree (user_profile_id) TABLESPACE pg_default;create table public.session_analytics (
  analytics_id uuid not null default gen_random_uuid (),
  tenant_id uuid not null,
  session_id uuid not null,
  practice_area character varying(100) null,
  session_duration integer null,
  questions_answered integer null,
  completion_rate numeric(5, 2) null,
  caller_satisfaction integer null,
  conversion_status character varying(50) null,
  created_at timestamp with time zone null default now(),
  constraint session_analytics_pkey primary key (analytics_id)
) TABLESPACE pg_default;

create index IF not exists idx_session_analytics_tenant_id on public.session_analytics using btree (tenant_id) TABLESPACE pg_default;create table public.sms_messages (
  sms_id uuid not null default gen_random_uuid (),
  tenant_id uuid not null,
  recipient_phone character varying(50) not null,
  sender_phone character varying(50) null,
  message_content text not null,
  message_type character varying(100) null,
  message_status character varying(50) null default 'pending'::character varying,
  sent_at timestamp with time zone null,
  delivered_at timestamp with time zone null,
  error_message text null,
  session_id uuid null,
  appointment_id uuid null,
  created_by uuid null,
  modified_by uuid null,
  created_at timestamp with time zone null default now(),
  updated_at timestamp with time zone null default now(),
  constraint sms_messages_pkey primary key (sms_id)
) TABLESPACE pg_default;

create index IF not exists idx_sms_messages_tenant_id on public.sms_messages using btree (tenant_id) TABLESPACE pg_default;

create trigger update_sms_messages_updated_at BEFORE
update on sms_messages for EACH row
execute FUNCTION update_updated_at_column ();create table public.social_media_invitations (
  invitation_id uuid not null default gen_random_uuid (),
  tenant_id uuid not null,
  lead_id uuid null,
  contact_id uuid null,
  appointment_id uuid null,
  session_id uuid null,
  platform character varying(50) not null,
  invitation_link character varying(500) null,
  invitation_status character varying(50) null default 'sent'::character varying,
  sent_at timestamp with time zone null default now(),
  accepted_at timestamp with time zone null,
  declined_at timestamp with time zone null,
  notes text null,
  is_deleted boolean null default false,
  deleted_at timestamp with time zone null,
  deleted_by uuid null,
  created_by uuid null,
  modified_by uuid null,
  created_at timestamp with time zone null default now(),
  updated_at timestamp with time zone null default now(),
  constraint social_media_invitations_pkey primary key (invitation_id),
  constraint fk_social_media_invitations_appointment_id foreign KEY (appointment_id) references appointments (appointment_id),
  constraint fk_social_media_invitations_contact_id foreign KEY (contact_id) references contacts (contact_id),
  constraint fk_social_media_invitations_lead_id foreign KEY (lead_id) references intake_leads (lead_id),
  constraint fk_social_media_invitations_session_id foreign KEY (session_id) references intake_sessions (session_id),
  constraint fk_social_media_invitations_tenant_id foreign KEY (tenant_id) references tenants (tenant_id),
  constraint chk_social_media_invitations_platform check (
    (
      (platform)::text = any (
        (
          array[
            'linkedin'::character varying,
            'facebook'::character varying,
            'twitter'::character varying,
            'instagram'::character varying,
            'other'::character varying
          ]
        )::text[]
      )
    )
  ),
  constraint chk_social_media_invitations_status check (
    (
      (invitation_status)::text = any (
        (
          array[
            'sent'::character varying,
            'accepted'::character varying,
            'declined'::character varying,
            'expired'::character varying,
            'cancelled'::character varying
          ]
        )::text[]
      )
    )
  )
) TABLESPACE pg_default;

create index IF not exists idx_social_media_invitations_tenant on public.social_media_invitations using btree (tenant_id) TABLESPACE pg_default;

create index IF not exists idx_social_media_invitations_lead on public.social_media_invitations using btree (lead_id) TABLESPACE pg_default;

create index IF not exists idx_social_media_invitations_contact on public.social_media_invitations using btree (contact_id) TABLESPACE pg_default;

create index IF not exists idx_social_media_invitations_appointment on public.social_media_invitations using btree (appointment_id) TABLESPACE pg_default;

create index IF not exists idx_social_media_invitations_session on public.social_media_invitations using btree (session_id) TABLESPACE pg_default;

create index IF not exists idx_social_media_invitations_platform on public.social_media_invitations using btree (platform) TABLESPACE pg_default;

create index IF not exists idx_social_media_invitations_status on public.social_media_invitations using btree (invitation_status) TABLESPACE pg_default;

create index IF not exists idx_social_media_invitations_sent_at on public.social_media_invitations using btree (sent_at) TABLESPACE pg_default;create table public.system_settings (
  setting_id uuid not null default gen_random_uuid (),
  tenant_id uuid null,
  setting_key character varying(255) not null,
  setting_value text null,
  setting_type character varying(100) null default 'string'::character varying,
  is_encrypted boolean null default false,
  description text null,
  created_by uuid null,
  modified_by uuid null,
  created_at timestamp with time zone null default now(),
  updated_at timestamp with time zone null default now(),
  constraint system_settings_pkey primary key (setting_id)
) TABLESPACE pg_default;

create trigger update_system_settings_updated_at BEFORE
update on system_settings for EACH row
execute FUNCTION update_updated_at_column ();create table public.tenant_message_templates (
  template_id uuid not null default gen_random_uuid (),
  tenant_id uuid not null,
  template_type character varying(100) not null,
  template_name character varying(255) not null,
  template_content text not null,
  template_variables jsonb null,
  is_active boolean null default true,
  created_by uuid null,
  modified_by uuid null,
  created_at timestamp with time zone null default now(),
  updated_at timestamp with time zone null default now(),
  constraint tenant_message_templates_pkey primary key (template_id)
) TABLESPACE pg_default;

create trigger update_tenant_message_templates_updated_at BEFORE
update on tenant_message_templates for EACH row
execute FUNCTION update_updated_at_column ();create table public.tenants (
  tenant_id uuid not null default gen_random_uuid (),
  firm_name character varying(255) not null,
  firm_legal_name character varying(255) null,
  firm_email character varying(255) null,
  firm_phone character varying(50) null,
  firm_website character varying(255) null,
  jurisdiction character varying(100) null,
  jurisdiction_cities text null,
  bar_number character varying(100) null,
  tax_id character varying(50) null,
  subscription_status character varying(50) null default 'trial'::character varying,
  subscription_tier character varying(50) null default 'basic'::character varying,
  trial_ends_at timestamp with time zone null,
  container_id character varying(255) null,
  container_status character varying(50) null default 'pending'::character varying,
  deployed_at timestamp with time zone null,
  created_by uuid null,
  modified_by uuid null,
  created_at timestamp with time zone null default now(),
  updated_at timestamp with time zone null default now(),
  registration_number character varying(100) null,
  year_established integer null,
  website character varying(255) null,
  description text null,
  number_of_attorneys integer null,
  total_staff_count integer null,
  annual_revenue_range character varying(50) null,
  timezone character varying(100) null,
  enable_direct_booking boolean null default true,
  require_engagement_letter boolean null default false,
  default_engagement_template_id uuid null,
  constraint tenants_pkey primary key (tenant_id),
  constraint fk_tenants_default_engagement_template_id foreign KEY (default_engagement_template_id) references engagement_letter_templates (template_id),
  constraint chk_tenants_year_established check (
    (
      (year_established >= 1800)
      and (
        (year_established)::numeric <= EXTRACT(
          year
          from
            CURRENT_DATE
        )
      )
    )
  )
) TABLESPACE pg_default;

create index IF not exists idx_tenants_firm_name on public.tenants using btree (firm_name) TABLESPACE pg_default;

create index IF not exists idx_tenants_subscription_status on public.tenants using btree (subscription_status) TABLESPACE pg_default;

create index IF not exists idx_tenants_timezone on public.tenants using btree (timezone) TABLESPACE pg_default;

create index IF not exists idx_tenants_enable_direct_booking on public.tenants using btree (enable_direct_booking) TABLESPACE pg_default;

create index IF not exists idx_tenants_require_engagement_letter on public.tenants using btree (require_engagement_letter) TABLESPACE pg_default;

create trigger update_tenants_updated_at BEFORE
update on tenants for EACH row
execute FUNCTION update_updated_at_column ();create table public.user_profiles (
  user_profile_id uuid not null default gen_random_uuid (),
  tenant_id uuid not null,
  contact_id uuid null,
  user_role_id uuid not null,
  username character varying(100) null,
  password_hash character varying(255) null,
  is_active boolean null default true,
  last_login_at timestamp with time zone null,
  login_attempts integer null default 0,
  locked_until timestamp with time zone null,
  two_factor_enabled boolean null default false,
  two_factor_secret character varying(255) null,
  created_by uuid null,
  modified_by uuid null,
  created_at timestamp with time zone null default now(),
  updated_at timestamp with time zone null default now(),
  expertise_areas text[] null,
  case_load_limit integer null,
  availability_status character varying(50) null,
  working_hours jsonb null,
  theme_preferences jsonb null,
  constraint user_profiles_pkey primary key (user_profile_id),
  constraint user_profiles_username_key unique (username),
  constraint chk_user_profiles_availability_status check (
    (
      (availability_status)::text = any (
        (
          array[
            'available'::character varying,
            'busy'::character varying,
            'away'::character varying,
            'do_not_disturb'::character varying,
            'offline'::character varying
          ]
        )::text[]
      )
    )
  )
) TABLESPACE pg_default;

create index IF not exists idx_user_profiles_tenant_id on public.user_profiles using btree (tenant_id) TABLESPACE pg_default;

create index IF not exists idx_user_profiles_user_role_id on public.user_profiles using btree (user_role_id) TABLESPACE pg_default;

create index IF not exists idx_user_profiles_availability_status on public.user_profiles using btree (availability_status) TABLESPACE pg_default;

create trigger update_user_profiles_updated_at BEFORE
update on user_profiles for EACH row
execute FUNCTION update_updated_at_column ();create table public.user_roles (
  user_role_id uuid not null default gen_random_uuid (),
  role_name character varying(100) not null,
  description text null,
  role_level integer not null,
  permissions jsonb not null,
  is_internal boolean null default false,
  is_active boolean null default true,
  created_by uuid null,
  modified_by uuid null,
  created_at timestamp without time zone null default CURRENT_TIMESTAMP,
  updated_at timestamp without time zone null default CURRENT_TIMESTAMP,
  constraint user_roles_pkey primary key (user_role_id),
  constraint user_roles_role_name_key unique (role_name)
) TABLESPACE pg_default;

create index IF not exists idx_user_roles_name on public.user_roles using btree (role_name) TABLESPACE pg_default;

create index IF not exists idx_user_roles_internal on public.user_roles using btree (is_internal) TABLESPACE pg_default;

create index IF not exists idx_user_roles_level on public.user_roles using btree (role_level) TABLESPACE pg_default;

create trigger update_user_roles_updated_at BEFORE
update on user_roles for EACH row
execute FUNCTION update_updated_at_column ();create table public.webhooks (
  webhook_id uuid not null default gen_random_uuid (),
  tenant_id uuid not null,
  webhook_name character varying(255) not null,
  webhook_url character varying(500) not null,
  webhook_secret character varying(255) null,
  webhook_events jsonb not null,
  is_active boolean null default true,
  last_triggered_at timestamp with time zone null,
  failure_count integer null default 0,
  created_by uuid null,
  modified_by uuid null,
  created_at timestamp with time zone null default now(),
  updated_at timestamp with time zone null default now(),
  constraint webhooks_pkey primary key (webhook_id)
) TABLESPACE pg_default;

create index IF not exists idx_webhooks_tenant_id on public.webhooks using btree (tenant_id) TABLESPACE pg_default;

create trigger update_webhooks_updated_at BEFORE
update on webhooks for EACH row
execute FUNCTION update_updated_at_column ();