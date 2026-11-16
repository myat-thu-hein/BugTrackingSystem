-- =====================================================================
-- Migration 003: let the backend use every table.
--
-- Fixes: "permission denied for table faqs" (or support_questions,
-- notifications, ...) with code 42501, which made the help chat and
-- Help Center fail with a 500 error.
--
-- Why it happens: the backend connects with the SERVICE ROLE key, and
-- Supabase only lets that role use tables it has been GRANTed. Some
-- projects don't grant new tables automatically, so tables created by
-- migration 001 could exist while the backend wasn't allowed to read them.
--
-- Safe to re-run. Only service_role (the backend) gets access; the public
-- anon/authenticated keys stay locked out, as before.
-- =====================================================================

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

-- Check: every row should say true.
select t as table_name, has_table_privilege('service_role', 'public.' || t, 'select, insert, update, delete') as backend_can_use
from unnest(array['projects','users','bugs','comments','bug_history','notifications','admin_requests','faqs','support_questions']) as t;
