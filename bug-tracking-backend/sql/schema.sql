-- =====================================================================
-- Bug Tracking System - Supabase PostgreSQL schema
--
-- How to use:
--   1. Open your Supabase project -> SQL Editor -> New query
--   2. Paste this whole file and click "Run"
--
-- This creates: users, bugs, comments, bug_history
-- with primary keys, foreign keys, and sensible CHECK constraints so
-- invalid roles/severities/priorities/statuses can never be inserted,
-- even by mistake.
-- =====================================================================

-- Needed for gen_random_uuid()
create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------------
-- users
-- ---------------------------------------------------------------------
create table if not exists users (
    id            uuid primary key default gen_random_uuid(),
    name          text not null,
    email         text not null unique,
    password_hash text not null,
    role          text not null check (role in ('admin', 'tester', 'developer')),
    created_at    timestamptz not null default now()
);

create index if not exists idx_users_email on users (email);
create index if not exists idx_users_role on users (role);

-- ---------------------------------------------------------------------
-- bugs
-- ---------------------------------------------------------------------
create table if not exists bugs (
    id           uuid primary key default gen_random_uuid(),
    title        text not null,
    description  text not null,
    severity     text not null check (severity in ('Minor', 'Major', 'Critical', 'Blocker')),
    priority     text not null check (priority in ('Low', 'Medium', 'High', 'Critical')),
    status       text not null default 'Open'
                 check (status in ('Open', 'In Progress', 'Resolved', 'Closed', 'Reopened')),
    reported_by  uuid not null references users (id) on delete restrict,
    assigned_to  uuid references users (id) on delete set null,
    created_at   timestamptz not null default now(),
    updated_at   timestamptz not null default now()
);

create index if not exists idx_bugs_status on bugs (status);
create index if not exists idx_bugs_assigned_to on bugs (assigned_to);
create index if not exists idx_bugs_reported_by on bugs (reported_by);

-- ---------------------------------------------------------------------
-- comments
-- ---------------------------------------------------------------------
create table if not exists comments (
    id         uuid primary key default gen_random_uuid(),
    bug_id     uuid not null references bugs (id) on delete cascade,
    user_id    uuid not null references users (id) on delete restrict,
    comment    text not null,
    created_at timestamptz not null default now()
);

create index if not exists idx_comments_bug_id on comments (bug_id);

-- ---------------------------------------------------------------------
-- bug_history  (audit trail: "User A changed BUG-001: Open -> In Progress")
-- ---------------------------------------------------------------------
create table if not exists bug_history (
    id         uuid primary key default gen_random_uuid(),
    bug_id     uuid not null references bugs (id) on delete cascade,
    user_id    uuid not null references users (id) on delete restrict,
    action     text not null,       -- e.g. 'status_changed', 'assignment_changed',
                                     -- 'priority_changed', 'severity_changed', 'created'
    old_value  text,
    new_value  text,
    created_at timestamptz not null default now()
);

create index if not exists idx_bug_history_bug_id on bug_history (bug_id);

-- ---------------------------------------------------------------------
-- Row Level Security
--
-- The Flask backend connects using the SERVICE ROLE key and enforces all
-- authorization itself (see app/middleware/permissions.py), so RLS is not
-- required for the API to function. We still enable it and lock the
-- tables down to service-role-only access, so that if the anon/public key
-- were ever leaked or misused directly against Supabase, no data could be
-- read or written without going through the Flask API.
-- ---------------------------------------------------------------------
alter table users enable row level security;
alter table bugs enable row level security;
alter table comments enable row level security;
alter table bug_history enable row level security;

-- No policies are created for the anon/authenticated roles on purpose:
-- with RLS enabled and zero policies, only the service_role key (which
-- bypasses RLS entirely) can read/write these tables.
