# Bug Tracking System

A team bug tracker for multiple projects, with an enforced workflow
**Open → In Progress → Resolved → Closed / Reopened**, live notifications, email alerts and a help chat.

## Features

| Feature | How it works |
|---|---|
| **Projects + invite codes** | An admin creates a project and gets a code like `BUG-7KQ2Xt9`. Teammates register with it and join as Testers; the admin promotes them. Each project's bugs and members are invisible to other projects. |
| **Owner approval for admins** | "Request admin access" on the Register page notifies and emails the owners (you and your team, set in `OWNER_EMAILS`), who approve or reject in the app. |
| **Live notifications** | Bell with unread badge, toasts and a Notifications page, updated instantly over Server-Sent Events. Open dashboards, lists and bug pages refresh themselves when something changes. |
| **Email** | Important events only (assigned to you, ready to verify, reopened, role changed, admin requests, support questions). Off switch in Settings. Works with any SMTP account, e.g. Gmail. |
| **Help chat** | Floating chat answers questions instantly from the project's FAQ (most-asked first). Unanswered questions go to the project admins, who reply from the Help Center and can add the answer to the FAQ. |
| **Roles** | Owner · Admin · Tester · Developer, checked on the server for every action. |

| Part | Stack | Docs |
|---|---|---|
| `bug-tracking-backend/` | Flask, Supabase PostgreSQL, JWT | [backend README](bug-tracking-backend/README.md) |
| `bug-tracking-frontend/` | React, Vite, Tailwind CSS | [frontend README](bug-tracking-frontend/README.md) |

## Demo script (about 5 minutes, three browser windows)

Use three windows (or one normal + two private windows), one per person.

1. **Owner** registers with an `OWNER_EMAILS` address → lands on Admin Requests.
2. **Lead** registers with *Request admin access* → sees "Request under review".
   *Show:* the owner's bell lights up instantly.
3. **Owner** clicks Approve → the lead's page switches to "Create your project" by itself.
4. **Lead** creates a project → the dashboard shows the invite code.
5. **Tester** registers with *Join a project* + the code → tester dashboard. *Show:* the lead's bell.
6. **Tester** reports a bug → **Lead** assigns it to a developer (promote someone on Users first).
   *Show:* the developer gets a toast and their dashboard count changes with no refresh.
7. **Developer** marks it In Progress → Resolved → the tester is told "Please verify it".
8. **Tester** opens the help chat, asks "how do I reopen a bug?" (instant answer), then
   "can we export to Excel?" → sends it to the admin → the lead answers in Help Center → the tester is notified.

## Run everything locally

1. Backend: follow `bug-tracking-backend/README.md` (create Supabase project, run `sql/schema.sql`, fill `.env`
   including `OWNER_EMAILS` with your team's emails, then `python run.py`). Email is optional (see "Email setup").
2. Checkpoint: open `http://localhost:5000/api/health` — you should see `"Bug Tracking API is running"`.
3. Frontend: `cd bug-tracking-frontend && npm install && cp .env.example .env && npm run dev`.
4. Checkpoint: open `http://localhost:5173`, register with an owner email, and you land on **Admin Requests**.

Upgrading a database made with an older version? In the Supabase SQL Editor run, in order: `bug-tracking-backend/sql/migrations/001_projects_notifications_support.sql` (if not run yet), `002_seed_starter_faqs.sql` and `003_grant_service_role.sql`. All three are safe to re-run.

See [REFACTOR_NOTES.md](REFACTOR_NOTES.md) for what changed in each cleanup pass, the bugs found, and how it was verified.
