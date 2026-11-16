# Refactor notes

Two cleanup passes. Original features, URLs and API responses are unchanged; the exceptions are listed under
"Small intentional behaviour changes" in each pass.

---

# Fix: errors from the backend log (Windows, local run)

| Error in the log | Root cause | Fix |
|---|---|---|
| `postgrest.exceptions.APIError: permission denied for table faqs` / `support_questions` (`42501`) | The tables existed, but the backend's `service_role` had never been granted access to them, so every FAQ / Help Center request returned 500 | `sql/migrations/003_grant_service_role.sql` grants `service_role` (only) access to all 9 tables, plus default privileges for future tables; `schema.sql` and migration 001 now include the same grants. The API now says which migration to run, and `/api/health/setup` reports `no permission` per table. Reproduced and verified on PostgreSQL 16 with Supabase-like roles. |
| `httpx.ReadError: [WinError 10035] A non-blocking socket operation could not be completed immediately` | supabase-py's database client always uses one shared HTTP/2 connection; the threaded server's parallel requests (page loads, notifications, live stream) read it at the same time, which breaks on Windows | `app/services/supabase_http.py` makes the client use HTTP/1.1, so httpx gives each parallel request its own pooled connection. Verified: 600 requests from 30 threads through the real supabase client, 600 correct, 0 errors. Network errors to Supabase now return a temporary 503 ("please try again") instead of 500. |

Verified: 56 backend tests (new: permission-denied message and setup report, network error → 503, real client
uses HTTP/1.1), frontend unchanged (44 tests, lint, build).

---

# Fix: "Couldn't load the FAQ" and Help Center "Something went wrong"

**Root cause:** on Render, the dashboard's Start Command overrides the `Procfile`. With the old command
(`gunicorn run:app`, one single-threaded "sync" worker) each browser tab's live-notification stream occupied
the only worker. Every other request queued behind it until gunicorn killed the worker after 30 s
(`WORKER TIMEOUT`), and Render returned 5xx errors. The FAQ endpoints were the first requests made after the
stream opened, so the chat and Help Center failed. Reproduced locally with gunicorn (FAQ request: 29.9 s, then
a worker timeout).

**Fix:**
- The stream only runs where it's safe (threaded/async worker, single process; read from `wsgi.multithread`
  / `wsgi.multiprocess`). Otherwise it answers 503 immediately and the browser checks every 10 s instead,
  still showing toasts. Streams now last 55 s instead of 300 s.
- `GET /api/health/setup`: plain-language check of every table, the FAQ count and live-notification support,
  with the exact fix for each problem.
- Missing table/column errors from Supabase now say "Run the latest SQL migration" instead of a bare 500.
- The frontend shows the server's specific message or the status code ("error 502") instead of a generic
  "Something went wrong".

Verified: 53 backend tests (new: stream refusal, setup check, missing-table message, with the fake DB raising
Supabase's `PGRST205`); browser runs on real gunicorn with both start commands. Sync worker: everything loads,
notification delivered in 7 s by polling. Gthread worker: instant. No worker timeouts with either.

---

# Fix: help chat / FAQ not working

| # | Symptom | Root cause | Fix |
|---|---|---|---|
| 1 | Chat said "No FAQs yet" and could never answer, in a database upgraded with migration 001 | The migration created "Default Project" but no FAQs; only projects created in the app got the starter set | New `002_seed_starter_faqs.sql` (and migration 001 now seeds them too); **Add starter FAQs** button on the empty Help Center; `POST /api/support/faqs/defaults` |
| 2 | After one failed load (e.g. Render waking up) the chat stayed empty until a page reload | The error was stored as "no FAQs" (`[]`) and never retried | Errors show **Try again**; the FAQ reloads each time the chat opens; a failed refresh keeps the FAQs already loaded |
| 3 | A question typed right after opening the chat got "couldn't find an answer" | It was matched against the list while it was still loading (or the old list while refreshing) | Questions wait for the load in progress |
| 4 | Most-asked suggestions, and FAQs an admin added later, disappeared after the first question | Suggestions only rendered while the conversation had one message | A "Most asked" row is always visible above the input |
| 5 | Typos ("notifcation"), partial words ("notif"), Thai/Burmese text never matched | Exact word matching only, and every non a–z character was stripped | Typo- and prefix-tolerant matching, Unicode letters kept, character-pair matching for languages without spaces |

Verified: backend 50 tests (new: starter FAQs, repeatable), frontend 44 tests (new: typos, partial words, Thai,
accents, still rejecting unrelated words); a browser run reproducing each case above (10/10 pass, no page
errors); migrations 001 → 002 run twice on PostgreSQL 16 (0 → 9 FAQs, then unchanged).

---

# Pass 3: new features (projects, owner approval, live notifications, email, help chat)

Built on top of pass 2; every earlier feature still works the same inside a project.

- **Data model:** new `projects`, `notifications`, `admin_requests`, `faqs`, `support_questions` tables;
  `users.project_id`, `users.email_notifications`, `bugs.project_id`, and an `owner` role.
  `sql/migrations/001_projects_notifications_support.sql` upgrades an existing database without losing data.
- **Design decision:** each user belongs to one project (simpler and safer for the deadline). Joining always
  makes you a Tester; admins promote. Invite codes are short, random, case-insensitive and can be regenerated.
- **Isolation:** every bug/comment/member query is filtered by the caller's project (`@project_required` +
  `fetch_bug` scoping), so other projects' data returns 404.
- **Notifications:** one `notify()` helper (skips the person acting, stores, pushes live, optionally emails).
  Live delivery is Server-Sent Events from Flask with an in-memory pub/sub; the browser reads it with `fetch()`
  so the token stays in a header, reconnects with back-off, re-syncs on reconnect and polls every minute.
- **Email:** standard-library SMTP in a background thread; logs instead of sending when SMTP isn't configured.
- **Help chat:** FAQ matching runs in the browser (instant, no AI); `hits` ranks the most asked questions;
  unanswered questions go to admins, whose answers can become FAQs.

**Verification:** backend 49 offline tests (11 new: registration modes, admin approval, isolation, invite codes,
notifications, email preference, live stream, support); frontend 41 tests (new: FAQ matcher, SSE parser, role
routing); lint clean; build OK. A 21-step browser run with five simultaneous users (owner, lead, tester,
developer, other-project admin) checked every live update, the role-change redirect, project isolation,
the chat → admin → answer loop and 6 captured emails, at desktop and phone widths, with no console errors.

---

# Pass 2: bugs found by running it, UX and structure

This pass ran the real Flask app (in-memory database, seeded data) behind the real frontend in a browser at
desktop and phone widths, and clicked through every role's main flows. Most findings came from that.

## Real bugs found (and the root cause of each)

| # | Symptom | Root cause | Fix |
|---|---|---|---|
| 1 | The bug list scrolled sideways on phones (page 651px wide on a 390px screen) | The table's screen-reader-only "Actions" label is `position: absolute`; with no positioned ancestor it escaped the scroll container and stretched the page | Shared `Table` wrapper is `relative`; phones now get a card list instead of a 10-column table |
| 2 | At 1366px the filter bar overflowed its card and the page scrolled sideways | Six fixed-width controls in one row didn't fit beside the sidebar | Search on its own row, selects in a responsive grid |
| 3 | Sending a JSON array (e.g. `["x"]`) to register, login, create bug, status or role returned **500** | Code called `.get()` on whatever JSON arrived | `json_body()` helper: non-object bodies get a clean 400 |
| 4 | The only admin could demote themselves through the API, leaving nobody able to manage roles | The guard existed only in the UI | API now rejects changing your own role (400) |
| 5 | `GET /api/bugs?assigned_to=abc` (or any malformed id) returned **500** | Filter values went straight to PostgreSQL, which rejects a non-uuid | Filters validated first: unknown status/priority/severity or bad id → 400 |
| 6 | Filters, sort and page reset every time you opened a bug and came back | They lived in component state, which unmounts | Stored in the URL (`/bugs?status=Open&page=2`); Back, reload and shared links keep them |
| 7 | In dialogs, focus jumped back to the dialog box on every re-render (e.g. while "Deleting...") and Tab could leave the dialog | `onClose` (an inline arrow) was an effect dependency, so the focus effect re-ran each render; no focus trap | `onClose` read through a ref; Tab is trapped; page behind doesn't scroll; can't dismiss mid-request |
| 8 | `.execute().data[0]` raised `IndexError` (500) if a row vanished between read and write | No guard on empty results | `first_row()` → 404 |
| 9 | A 413 handler existed but large bodies were never limited | `MAX_CONTENT_LENGTH` was not set | 1 MB limit (configurable) |
| 10 | Admins couldn't change a bug's title, priority or severity | The API supported it (and audits it), but no screen called it; the "Priority changed" timeline text was unreachable | Admin **Edit** dialog on the bug page, sending only changed fields |
| 11 | Re-assigning a bug to its current developer added a duplicate history entry | No same-value check | Treated as a no-op |
| 12 | Tester dashboard said "Track bugs you have reported" but showed every bug | Wrong copy (testers verify all bugs) | Corrected |

## Structure / code quality

- **Backend errors are raised, not returned.** `app/errors.py` defines `ApiError` and `BadRequestError`,
  `UnauthorizedError`, `ForbiddenError`, `NotFoundError`, `ConflictError`, all rendered by one handler. The
  `bug, error = ...; if error: return error` pattern (repeated in every route) is gone; `get_viewable_bug(id)` just
  returns the bug or stops the request. Middleware uses the same exceptions.
- `app/utils/request.py` (`json_body`, `first_row`); `update_bug_row()` in the bug service (sets `updated_at` in one
  place); `validate_list_filters()` and `one_of_message()` in validators; `NAME_MAX` moved next to the other limits.
- **Frontend:** `FieldShell` holds the label/error/hint/counter wiring once (Field and PasswordField both use it);
  `Table`/`Th`/`Td` primitives shared by the bug list and users page; one `BugBadge` (with optional "Priority:"
  label) replaces the badge factory; colours grouped per kind (the old flat map could only give "Critical" one
  colour even though it's both a priority and a severity); `useBugListParams` hook; URL parse/build helpers are pure
  and unit-tested; the bug page's action logic is one `applyBug` helper instead of four near-copies.
- Removed: `AssignDeveloperCard` (replaced by `AssignDeveloper` inside the details panel), unused `capitalize`,
  `BAR_COLORS`.

## UI/UX

- **Bug page** follows the familiar issue-tracker layout: bug + comments on the left; a sticky side panel with
  Status (badge, a plain-language "what happens next" line, and only the buttons you're allowed to press), Details
  (assignee, reporter, created/updated, assignment control for admins) and Activity (newest first, colour-coded).
  On phones the panel sits between the bug and the comments, so the next action is visible without scrolling.
- **Closing a bug asks first** (Closed is final). Only the clicked status button shows a spinner.
- Priority and severity badges are labelled ("Priority: Critical") wherever they appear together.
- Comments: avatars with initials, role, "(you)", relative times with the exact time on hover, Ctrl/⌘+Enter to post,
  character counter, new comment scrolled into view. Description editor: counter, Ctrl/⌘+Enter / Esc.
- **Dashboards:** every stat card and summary row links to the list filtered to that value; percentages shown;
  "View all" link; helpful empty states (testers get a "Create Bug" button).
- **Bug list:** more sorts (recently updated, highest priority, highest severity); search by title *or* `#id`;
  active filters are tinted; "4 of 15 bugs match"; distinct empty states for "no bugs yet" vs "no matches";
  whole row clickable; "Back to bugs" returns to the same filtered page.
- **Users:** search, role filter chips with counts, avatars; granting or removing **admin** asks for confirmation;
  loading skeleton instead of a spinner.
- Forms: length limits and counters matching the backend; Register pre-fills the email on the sign-in page;
  Create Bug defaults to Medium/Major with a reproduction-steps placeholder; Cancel works even when opened directly.
- If your session expires mid-use you now see "Your session has expired" instead of a silent jump to sign-in.
- A crash inside one page now shows an in-page error with "Try again", keeping the sidebar usable; moving to
  another page clears it (previously the whole app was replaced by the error screen).

## Small intentional behaviour changes

- API: `PUT /api/users/<own id>/role` → 400 (the UI already blocked it).
- API: invalid list filters (`?status=Banana`, `?assigned_to=abc`) → 400 instead of an empty list / 500.
- API: request bodies over 1 MB → 413 (`MAX_CONTENT_LENGTH` env var to change).
- UI: Create Bug defaults to Medium priority / Major severity (was Low / Minor).

## Verification performed

- Backend: **38** offline tests pass (5 new regression tests for #3, #4, #5, #9, #11); 9 live tests are opt-in.
- Frontend: `npm run lint` clean; **34** tests pass (10 new: sorting, `#id` search, URL params, relative time,
  length limits); `npm run build` succeeds. The bug-page chunk grew from 4.2 KB to 6.6 KB gzipped (edit dialog,
  side panel); everything else is about the same size.
- **Browser check (Playwright, Chromium)** against the real Flask app: admin, tester and developer sign-in;
  dashboard card → filtered list → sort → open bug → "Back to bugs" keeps `?status=Open&sort=priority`; close with
  confirmation (focus starts on the confirm button and stays trapped); admin edit writes "Severity changed from
  Major to Blocker" to the timeline; comment via Ctrl+Enter; delete dialog closes on Esc; admin-role confirmation;
  tester creates a bug and lands on it. No console errors. No sideways scroll at 390, 768, 1024, 1280 or 1366px.
- **Still not done:** a run against your real Supabase project (the in-memory fake mirrors the queries used, but
  not every PostgreSQL behaviour).

---

# Pass 1

What was found, what changed, and how to check it. Original features and URLs are unchanged.

## Real bugs found (and the root cause of each)

| # | Symptom | Root cause | Fix |
|---|---|---|---|
| 1 | Every bug showed **"Unassigned"** and an empty reporter, even after assignment | The API returned only user ids; the UI read name fields that were never sent | Backend now adds `reporter_name` / `assigned_developer_name` (one extra query for the whole list, not one per bug) |
| 2 | Comment authors showed as **"Unknown"** with no role | The API nested the author under `users`; the UI read `user_name` | Backend flattens to `user_name` / `user_role`; frontend mappers accept both shapes |
| 3 | History timeline showed raw text like `status_changed` | UI printed the action code, not the old/new values | Readable sentences ("Status changed from Open to In Progress"); assignment ids are resolved to names |
| 4 | Wrong password said **"Your session has expired"** | Error helper mapped every 401 to that text | The server's own message is shown ("Invalid email or password") |
| 5 | Two sidebar configs; the unused one pointed at routes that don't exist; "Dashboard" and "Assigned Bugs" both opened the same page | Copy-pasted config | One `config/navigation.js`; developer's "Assigned Bugs" now opens the bug list |
| 6 | Dead or broken files (`bugStats.js` imported constants that don't exist, `Spinner` used an undefined colour, `RecentBugsList` passed wrong props, duplicate Toast) | Abandoned drafts left in the tree | Removed or fixed and actually used |
| 7 | `npm run lint` could not run | Script existed but ESLint was not installed or configured | ESLint 9 flat config added; lint is clean |
| 8 | Non-text JSON (e.g. `"title": 5`) and malformed ids (`/api/bugs/abc`) could crash a request | Code assumed strings/UUIDs | Validated up front: clean 400/404 instead of a server error |
| 9 | CORS allowed `*` together with credentials | Over-broad setting; the API uses a Bearer header, not cookies | Credentials turned off |

## Structure

- **Backend:** new `app/services/` (shared bug/user helpers that were copy-pasted across route files), `app/errors.py`
  (all failures return the JSON envelope), `app/extensions.py`, validation centralised in `utils/validators.py`.
  `create_app()` now accepts an injected client for testing. `test_supabase.py` moved to `scripts/check_supabase.py`.
- **Frontend:** grouped into `config/ context/ hooks/ services/ utils/ components/{ui,feedback,layout,bugs,dashboard}`;
  `@/` import alias; removed 20 duplicate/obsolete files.
- Overall line count is a little higher (about 2,500 → 2,900) because accessibility, loading skeletons, hooks and tests
  were added; the duplicated logic itself is gone (three dashboards → one component, three badges → one, two toast
  systems → one, three near-identical loaders → one `useFetch` hook).

## Reusable pieces added

`Button` (built-in loading state), `Field` / `PasswordField` (label + error + hint wired for screen readers), `Alert`,
`Badge`, `Modal` / `ConfirmDialog` (Escape, backdrop click, focus handling), `Pagination`, `PageHeader`, `Skeleton`,
`ErrorBoundary`, `StatusPage`, `BugDashboard`, `SummaryCard`, and hooks `useFetch`, `useBugDetails`, `useDebouncedValue`,
`usePageTitle`.

## UI/UX

Loading skeletons instead of lone spinners; inline form validation that matches backend rules; show/hide password;
success toasts; "Clear filters" with an active-filter count; "Showing 1–10 of 34" pagination; responsive table that hides
low-priority columns on small screens; short bug references (`#a1b2c3d4`) instead of 36-character ids; tab titles per
page; skip-to-content link; keyboard-accessible menus and dialogs.

## Performance

Pages are code-split (lazy routes) with vendor chunks; in-flight requests are cancelled when you navigate away or
reload (no stale responses); search is debounced; bug details load bug, comments, history and developers in parallel and
update locally after actions (no full-page spinner/reload); dashboard counts computed in one pass; date formatters
created once; the 401 handler no longer forces a full page reload.

## Small intentional behaviour changes

- An admin cannot change **their own** role in the Users table (prevents locking yourself out).
- Admin status buttons show only legal workflow moves (the backend rejected the others anyway).
- Backend length limits: title 200, description 5000, comment 2000, name 100.

## Verification performed

- Backend: 33 offline tests pass (`pytest`); 9 live tests are opt-in.
- Frontend: `npm run lint` clean, `npm test` 24 passing, `npm run build` succeeds.
- Contract check: the real frontend service modules were run against the real Flask app (in-memory database) through
  login, create, assign, status change, comments and history.
- **Not done:** a visual check in a browser and a run against your real Supabase project.
