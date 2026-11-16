-- =====================================================================
-- Bug Tracking System - Supabase PostgreSQL schema (fresh install)
--
-- How to use:
--   1. Open your Supabase project -> SQL Editor -> New query
--   2. Paste this whole file and click "Run"
--
-- Already ran an older version of this file? Run
-- sql/migrations/001_projects_notifications_support.sql instead - it
-- upgrades your existing tables and keeps your data.
--
-- Tables:
--   projects, users, bugs, comments, bug_history   (core tracker)
--   notifications                                    (live + email alerts)
--   admin_requests                                   (request admin role)
--   faqs, support_questions                          (support chat box)
-- =====================================================================

create extension if not exists "pgcrypto";   -- gen_random_uuid()

-- ---------------------------------------------------------------------
-- projects  (an admin creates one; members join with its invite code)
-- ---------------------------------------------------------------------
create table if not exists projects (
    id          uuid primary key default gen_random_uuid(),
    name        text not null,
    invite_code text not null unique,          -- e.g. BUG-7KQ2X9, can be regenerated
    created_by  uuid,                          -- FK added after users exists
    created_at  timestamptz not null default now()
);

-- ---------------------------------------------------------------------
-- users
--   role: owner     = platform owner (approves admin requests, no project)
--         admin     = project admin
--         tester / developer = project members
--   project_id is null until the user creates or joins a project.
-- ---------------------------------------------------------------------
create table if not exists users (
    id                  uuid primary key default gen_random_uuid(),
    name                text not null,
    email               text not null unique,
    password_hash       text not null,
    role                text not null check (role in ('owner', 'admin', 'tester', 'developer')),
    project_id          uuid references projects (id) on delete set null,
    email_notifications boolean not null default true,
    created_at          timestamptz not null default now()
);

alter table projects
    drop constraint if exists projects_created_by_fkey,
    add constraint projects_created_by_fkey foreign key (created_by) references users (id) on delete set null;

create index if not exists idx_users_email on users (email);
create index if not exists idx_users_role on users (role);
create index if not exists idx_users_project on users (project_id);

-- ---------------------------------------------------------------------
-- bugs
-- ---------------------------------------------------------------------
create table if not exists bugs (
    id           uuid primary key default gen_random_uuid(),
    project_id   uuid not null references projects (id) on delete cascade,
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

create index if not exists idx_bugs_project on bugs (project_id);
create index if not exists idx_bugs_status on bugs (status);
create index if not exists idx_bugs_assigned_to on bugs (assigned_to);
create index if not exists idx_bugs_reported_by on bugs (reported_by);
create index if not exists idx_bugs_created_at on bugs (created_at desc);

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
-- bug_history  (audit trail)
-- ---------------------------------------------------------------------
create table if not exists bug_history (
    id         uuid primary key default gen_random_uuid(),
    bug_id     uuid not null references bugs (id) on delete cascade,
    user_id    uuid not null references users (id) on delete restrict,
    action     text not null,   -- created, status_changed, assignment_changed, priority_changed, severity_changed
    old_value  text,
    new_value  text,
    created_at timestamptz not null default now()
);

create index if not exists idx_bug_history_bug_id on bug_history (bug_id);

-- ---------------------------------------------------------------------
-- notifications  (bell icon, live stream and email)
-- ---------------------------------------------------------------------
create table if not exists notifications (
    id         uuid primary key default gen_random_uuid(),
    user_id    uuid not null references users (id) on delete cascade,
    bug_id     uuid references bugs (id) on delete cascade,
    type       text not null,   -- bug_created, bug_assigned, status_changed, comment_added, ...
    message    text not null,
    link       text,            -- where clicking it goes, e.g. /bugs/<id>
    is_read    boolean not null default false,
    created_at timestamptz not null default now()
);

create index if not exists idx_notifications_user on notifications (user_id, created_at desc);

-- ---------------------------------------------------------------------
-- admin_requests  (someone asks the owners to make them an admin)
-- ---------------------------------------------------------------------
create table if not exists admin_requests (
    id          uuid primary key default gen_random_uuid(),
    user_id     uuid not null references users (id) on delete cascade,
    reason      text not null,
    status      text not null default 'pending' check (status in ('pending', 'approved', 'rejected')),
    reviewed_by uuid references users (id) on delete set null,
    reviewed_at timestamptz,
    created_at  timestamptz not null default now()
);

create index if not exists idx_admin_requests_status on admin_requests (status);

-- ---------------------------------------------------------------------
-- faqs  (support chat answers, per project; `hits` ranks "most asked")
-- ---------------------------------------------------------------------
create table if not exists faqs (
    id         uuid primary key default gen_random_uuid(),
    project_id uuid not null references projects (id) on delete cascade,
    question   text not null,
    answer     text not null,
    keywords   text not null default '',
    hits       integer not null default 0,
    created_at timestamptz not null default now()
);

create index if not exists idx_faqs_project on faqs (project_id);

-- ---------------------------------------------------------------------
-- support_questions  (chat questions the FAQ couldn't answer)
-- ---------------------------------------------------------------------
create table if not exists support_questions (
    id          uuid primary key default gen_random_uuid(),
    project_id  uuid not null references projects (id) on delete cascade,
    user_id     uuid not null references users (id) on delete cascade,
    question    text not null,
    answer      text,
    status      text not null default 'open' check (status in ('open', 'answered')),
    answered_by uuid references users (id) on delete set null,
    answered_at timestamptz,
    created_at  timestamptz not null default now()
);

create index if not exists idx_support_questions_project on support_questions (project_id, status);

-- ---------------------------------------------------------------------
-- Backend access: the Flask API connects as service_role. Grant it every
-- table explicitly (some Supabase projects don't do it automatically, which
-- caused "permission denied for table faqs"). anon/authenticated get nothing.
-- ---------------------------------------------------------------------
grant usage on schema public to service_role;

grant select, insert, update, delete on table
    public.projects,
    public.users,
    public.bugs,
    public.comments,
    public.bug_history,
    public.notifications,
    public.admin_requests,
    public.faqs,
    public.support_questions
to service_role;

-- Tables created later in this schema get the same access automatically.
alter default privileges in schema public grant select, insert, update, delete on tables to service_role;

-- ---------------------------------------------------------------------
-- Row Level Security
--
-- The Flask backend connects with the SERVICE ROLE key and enforces all
-- authorization itself. RLS is enabled with no policies, so the public
-- anon key can read/write nothing: all access goes through the API.
-- ---------------------------------------------------------------------
alter table projects enable row level security;
alter table users enable row level security;
alter table bugs enable row level security;
alter table comments enable row level security;
alter table bug_history enable row level security;
alter table notifications enable row level security;
alter table admin_requests enable row level security;
alter table faqs enable row level security;
alter table support_questions enable row level security;
