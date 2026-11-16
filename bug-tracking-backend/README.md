# Bug Tracking System — Backend API

A Flask + Supabase (PostgreSQL) REST API for a university Bug Tracking System,
with JWT authentication and role-based access control for three roles:
**Admin**, **Tester**, and **Developer**.

This repo is backend-only (no frontend), built for CSC480.

---

## 1. Project Structure

```
bug-tracking-backend/
├── app/
│   ├── __init__.py          # create_app() factory (CORS, Supabase client, blueprints)
│   ├── config.py            # env-var config + Supabase client creation
│   ├── extensions.py        # get_db() accessor for the shared Supabase client
│   ├── errors.py            # ApiError classes + global JSON error handlers
│   ├── routes/              # auth, bugs, comments, users, projects, admin_requests,
│   │                        # notifications (incl. live stream), support (thin HTTP layer)
│   ├── services/            # bug, user, project, admin_request, notification (notify()),
│   │                        # realtime (live pub/sub), email (SMTP in background)
│   ├── middleware/          # auth.py (JWT, @token_required), permissions.py (@role_required)
│   └── utils/               # responses.py, request.py (json_body), validators.py (rules, workflow)
├── tests/
│   ├── fakes.py             # in-memory fake Supabase (offline tests)
│   ├── conftest.py          # fixtures
│   ├── test_*.py            # fast offline suite (runs by default)
│   └── integration/         # opt-in tests against a real Supabase project
├── scripts/check_supabase.py   # connectivity check (was test_supabase.py)
├── sql/schema.sql  sql/migrations/001_projects_notifications_support.sql, 002_seed_starter_faqs.sql,
│                   003_grant_service_role.sql
├── postman/
├── .env.example  requirements.txt  requirements-dev.txt  pytest.ini
├── run.py  Procfile  README.md
```

### How the files connect
`run.py` calls `create_app()` from `app/__init__.py`. That factory function:
1. Loads config from `app/config.py` (which reads `.env`/environment variables).
2. Creates one shared Supabase client and stores it on `app.config["SUPABASE_CLIENT"]`.
3. Enables CORS.
4. Registers the four blueprints (`auth`, `bugs`, `comments`, `users`) under `/api/...`.

Every route file follows the same pattern:
```
@some_bp.route(...)
@token_required        # from middleware/auth.py - verifies the JWT
@role_required("admin")  # from middleware/permissions.py - checks the role
def handler():
    data = json_body()               # utils/request.py - always a dict, or 400
    bug = get_viewable_bug(bug_id)   # services raise NotFoundError / ForbiddenError
    if not data.get("status"):
        raise BadRequestError("...")  # app/errors.py turns this into the JSON envelope
    ...
    return success_response(...)
```

Failures are *raised* (`BadRequestError`, `UnauthorizedError`, `ForbiddenError`,
`NotFoundError`), never returned, so helpers can stop a request from any depth
and every error reaches the client in the same `{"success": false, "message": ...}` shape.

---

## 2. Supabase Setup

1. Create a project at [supabase.com](https://supabase.com).
2. Go to **SQL Editor → New query** and run ONE of these:
   - **New database:** paste `sql/schema.sql` and run it. It creates every table
     (projects, users, bugs, comments, bug_history, notifications,
     admin_requests, faqs, support_questions).
   - **Database from the older version:** paste
     `sql/migrations/001_projects_notifications_support.sql` and run it. It keeps
     your data, moves everyone into a "Default Project", adds the starter help-chat
     FAQs, and prints that project's invite code at the end.
   - **Then, for any existing database, run `sql/migrations/003_grant_service_role.sql`**
     (safe to re-run). It lets the backend use every table; without it some
     projects fail with `permission denied for table faqs`.
   - **Already ran migration 001 from the earlier v2 zip?** Also run
     `sql/migrations/002_seed_starter_faqs.sql` once. That version left
     "Default Project" with an empty FAQ, so the help chat couldn't answer anything.
3. Go to **Project Settings → API** and copy:
   - **Project URL** → `SUPABASE_URL`
   - **`service_role` secret key** → `SUPABASE_KEY`

   **Use the `service_role` key, not the `anon` key.** This backend does its
   own authentication and authorization in Flask (JWT + role checks), so it
   needs to bypass Supabase's Row Level Security to read/write freely. The
   schema enables RLS with **no policies**, which locks the tables so that
   only the `service_role` key can touch them — the `anon` key (the one a
   browser could see) can't read or write anything directly. Never send the
   `service_role` key to a frontend.

---

## 3. Install & Run Locally

```bash
# 1. Clone/open the project folder, then create a virtual environment
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment variables
cp .env.example .env
# and edit .env and fill in SUPABASE_URL, SUPABASE_KEY, JWT_SECRET_KEY

# 4. Run the server
python run.py
```

The API is now running at `http://localhost:5000/api`. Check
`GET http://localhost:5000/api/health` to confirm it's up.

### Who is who (roles)

| Role | Belongs to a project? | Can |
|---|---|---|
| **Owner** (you and your team) | No | Approve or reject admin requests, see every project |
| **Admin** | Yes, the one they created | Manage bugs, members' roles, invite code, Help Center |
| **Tester** | Yes | Report bugs, verify fixes (close / reopen) |
| **Developer** | Yes | Work on bugs assigned to them |

### First-time setup (numbered, with checkpoints)
1. Put your team's emails in `OWNER_EMAILS` in `.env` (comma-separated), restart the server.
2. Register on the website with one of those emails (choose either tab; owner
   emails always become owners). **Checkpoint:** after signing in you land on
   **Admin Requests**.
3. A team lead registers with **Request admin access**. **Checkpoint:** you get a
   notification (and an email if SMTP is set up); approve it.
4. The lead signs in, creates a project and sees its **invite code** on the
   dashboard. **Checkpoint:** the code looks like `BUG-7KQ2X9`.
5. Everyone else registers with **Join a project** + that code. They join as
   Testers; the admin promotes developers on the **Users** page.

No owner yet and want to approve requests directly? In Supabase run
`update users set role = 'owner', project_id = null where email = 'you@example.com';`

### Email setup (optional)
Without `SMTP_HOST` the app works normally and writes each email to the server
log instead (look for `Email (SMTP not configured, not sent)`). To really send
with Gmail:
1. Turn on 2-Step Verification for the Google account.
2. Google Account → Security → **App passwords** → create one (16 characters).
3. In `.env`: `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`, `SMTP_USER=you@gmail.com`,
   `SMTP_PASSWORD=<the app password>`, `APP_URL=<your frontend URL>`.
4. Restart. **Checkpoint:** assign a bug to a developer; their inbox gets
   "Assigned to you: ...". If not, the server log shows `Failed to send email` with the reason.

Emails are sent in a background thread (clicking "Assign" never waits for
them) and only for important events: admin request (to owners), request
decided, assigned to you, ready to verify, reopened, role changed, support
question (to admins). Each user can turn them off in Settings.

### Check your deployment
Open `https://<your-backend>/api/health/setup` in a browser. It lists every
database table as `ok` or `missing or out of date`, counts the FAQs, says
whether live notifications are on, and gives the exact fix for anything
wrong. `"success": true` means everything is set up.

### Live notifications
`GET /api/notifications/stream` is a Server-Sent Events stream: the server
pushes each notification the moment it is created. The browser reconnects
automatically and re-syncs over normal HTTP, so nothing is missed. Because
connected tabs are tracked in memory, run **one** gunicorn process with
threads (the `Procfile` already does: `--worker-class gthread --workers 1 --threads 32`).

**Render ignores the `Procfile` when a Start Command is set in its dashboard.**
Check Render → your backend → Settings → Start Command. If it is the old
`gunicorn run:app --bind 0.0.0.0:$PORT`, the server handles one request at a
time. The app detects this and switches to checking for notifications every
10 seconds (everything still works), but for instant notifications change it to
the command in the `Procfile`.

---

## 4. API Documentation

All responses share this shape:
```json
{ "success": true,  "message": "...", "data": { ... } }
{ "success": false, "message": "...", "errors": { ... } }
```

Everything below except auth, notifications and admin requests is **scoped to
your project**: you never see or touch another project's bugs or members
(they return 404).

### Auth
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/api/auth/register` | – | Body: name, email, password + `invite_code` (join as tester) **or** `request_admin: true, reason`. Emails in `OWNER_EMAILS` become owners. |
| POST | `/api/auth/login` | – | Returns `{ token, user, project, admin_request }` |
| GET | `/api/auth/me` | any | `{ user, project, admin_request }` (project includes `invite_code` for admins) |
| PUT | `/api/auth/me/preferences` | any | `{ "email_notifications": false }` |

### Projects
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/api/projects` | admin without a project | `{ "name": "..." }`; creates it with an invite code and starter FAQs |
| POST | `/api/projects/join` | user without a project | `{ "invite_code": "BUG-..." }`; joins as tester |
| GET | `/api/projects/current` | member | Project, member count (+ invite code for admins) |
| PUT | `/api/projects/current` | admin | Rename |
| POST | `/api/projects/current/invite-code` | admin | New code; the old one stops working |
| GET | `/api/projects` | owner | Every project with member and bug counts |

### Admin requests
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/api/admin-requests` | user without a project | `{ "reason": "..." }` (also possible at registration) |
| GET | `/api/admin-requests` | owner | All requests, newest first |
| PUT | `/api/admin-requests/<id>` | owner | `{ "decision": "approve" \| "reject" }` |

### Notifications
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/api/notifications` | any | Latest (`?limit=`, `?unread=true`) + `unread_count` |
| GET | `/api/notifications/unread-count` | any | For the bell badge |
| PUT | `/api/notifications/<id>/read` | any (own only) | Mark one read |
| PUT | `/api/notifications/read-all` | any | Mark all read |
| GET | `/api/notifications/stream` | any | Live Server-Sent Events stream |

### Support chat
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/api/support/faqs` | member | Project FAQs, most helpful first |
| POST | `/api/support/faqs/<id>/hit` | member | "That helped" counter |
| POST / PUT / DELETE | `/api/support/faqs[/<id>]` | admin | Manage FAQs (`question`, `answer`, `keywords`) |
| POST | `/api/support/faqs/defaults` | admin | Add the starter FAQs the project doesn't have yet (safe to repeat) |
| POST | `/api/support/questions` | member | Ask the admins (they get a notification + email) |
| GET | `/api/support/questions` | member | Admins: all; others: their own |
| PUT | `/api/support/questions/<id>/answer` | admin | `{ "answer", "add_to_faq": true }`; the asker is notified |

### Users
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/api/users` | admin | Members of your project |
| GET | `/api/users/developers` | member | Developers in your project (for the assign dropdown) |
| PUT | `/api/users/<id>/role` | admin | `admin` / `tester` / `developer` (not your own; never `owner`) |

### Bugs
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/api/bugs` | tester | Create a bug (`status` starts at `Open`) |
| GET | `/api/bugs` | any | List bugs (`?status=&severity=&priority=&assigned_to=`). Developers only ever see bugs assigned to them. |
| GET | `/api/bugs/<id>` | any (if permitted) | Get one bug |
| PUT | `/api/bugs/<id>` | admin (any field), developer (description on own assigned bugs) | Edit a bug |
| DELETE | `/api/bugs/<id>` | admin | Delete a bug |
| PUT | `/api/bugs/<id>/assign` | admin | Body: `{ "assigned_to": "<developer user id>" }` |
| PUT | `/api/bugs/<id>/status` | role- and workflow-restricted | Body: `{ "status": "..." }` |
| GET | `/api/bugs/<id>/history` | any (if permitted) | Full audit trail |

### Comments
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/api/bugs/<id>/comments` | any (if permitted to view the bug) | Body: `{ "comment": "..." }` |
| GET | `/api/bugs/<id>/comments` | any (if permitted to view the bug) | List comments |

### Status workflow
```
Open ──────► In Progress ──────► Resolved ──┬──► Closed
                  ▲                          └──► Reopened ──► In Progress
                  └──────────────────────────────────┘
```
Any move outside these arrows is rejected with `400` and a clear message.
On top of the workflow itself, **who** can make **which** move is also
checked (see `app/routes/bugs.py::ROLE_STATUS_MOVES`):
- **Developer**: `Open → In Progress`, `In Progress → Resolved`, `Reopened → In Progress` (only on bugs assigned to them)
- **Tester**: `Resolved → Closed`, `Resolved → Reopened` (verifying the fix)
- **Admin**: any transition allowed by the workflow diagram above

### HTTP status codes used
`200` OK · `201` Created · `400` Bad Request (validation/invalid transition)
· `401` Unauthorized (missing/invalid/expired token, bad credentials) ·
`403` Forbidden (valid user, wrong role/ownership) · `404` Not Found ·
`405` Method Not Allowed · `500` Internal Server Error

---

## 5. Testing with Postman

Import `postman/Bug_Tracking_API.postman_collection.json` into Postman.
It defines collection variables `base_url`, `token`, `bug_id`, `developer_id`.

Suggested run order:
1. **Auth → Register**, then **Auth → Login** (its test script auto-saves
   the JWT into `{{token}}`, so every later request is already authenticated).
2. **Bugs → Create Bug** (auto-saves `{{bug_id}}`).
3. Log in as an admin (change the request body's email/password to your
   admin account first) and try **Assign Bug to Developer**, **Update Bug**,
   **Delete Bug**.
4. Log in as the developer and try **Change Status** (`Open → In Progress`).
5. Try an invalid jump, e.g. `In Progress → Closed`, and confirm you get a
   `400` with a clear message.
6. **Comments → Add Comment / Get Comments**, then **Get Bug History** to
   see the full audit trail.

## Running the automated tests

```bash
pip install -r requirements-dev.txt
pytest                      # offline suite: no network, no credentials, ~10s
```

The default suite runs the whole API against an in-memory fake of Supabase
(`tests/fakes.py`), covering registration, login, token handling, validation,
the full bug lifecycle, role permissions, history and comments.

To also run the live tests against a real Supabase project (pre-create an
admin and a developer account first, see section 3):

```bash
export RUN_LIVE_TESTS=1
export TEST_ADMIN_EMAIL=admin@example.com   TEST_ADMIN_PASSWORD=Passw0rd!
export TEST_DEVELOPER_EMAIL=developer@example.com   TEST_DEVELOPER_PASSWORD=Passw0rd!
pytest tests/integration -v
```

---

## 6. Frontend Integration

1. Point the frontend at your API's base URL, e.g. `http://localhost:5000/api`
   locally or `https://your-app.onrender.com/api` once deployed.
2. Login flow: `POST /api/auth/login` → store the returned `token`
   (e.g. in memory or `localStorage`) → send it on every subsequent request:
   ```js
   fetch(`${API_URL}/bugs`, {
     headers: { Authorization: `Bearer ${token}` }
   });
   ```
3. Handle `401` responses by redirecting to the login page (token missing/expired).
4. Handle `403` responses by showing a "not allowed" message rather than a crash.
5. Because CORS is configured via the `CORS_ORIGINS` env var, set it to your
   deployed frontend's exact origin (e.g. `https://my-frontend.vercel.app`)
   once you're past local development with `*`.

---

## 7. Deploying to Render

1. Push this repo to GitHub (make sure `.env` is in `.gitignore` and never committed).
2. On [Render](https://render.com): **New → Web Service**, connect the repo.
3. Settings:
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn run:app --bind 0.0.0.0:$PORT --worker-class gthread --workers 1 --threads 32 --timeout 120`
     (already in `Procfile`; one process with threads keeps live notifications working)
4. Add Environment Variables in the Render dashboard (Environment tab):
   `SUPABASE_URL`, `SUPABASE_KEY`, `JWT_SECRET_KEY`, `JWT_EXPIRES_HOURS`,
   `CORS_ORIGINS`, `FLASK_ENV=production`, `OWNER_EMAILS`, `APP_URL`, and the
   `SMTP_*` / `EMAIL_FROM` values if you want real emails.
   Note: Render's free tier sleeps when idle, so the first request (and the
   live connection) can take ~30 s to wake it.
5. Deploy. Render sets `PORT` automatically; `run.py`/gunicorn both read it,
   so the app listens on the host/port Render expects.
6. Confirm with `GET https://your-app.onrender.com/api/health`.

---

## 8. Common Errors & Fixes

| Symptom | Likely cause | Fix |
|---|---|---|
| `RuntimeError: Missing required environment variables` on startup | `.env` not created/filled in | `cp .env.example .env` and fill in all three required values |
| `401 Missing or invalid Authorization header` | Forgot the `Bearer ` prefix, or no header at all | Send `Authorization: Bearer <token>` |
| `401 Token has expired` | JWT lifetime (`JWT_EXPIRES_HOURS`) passed | Log in again to get a fresh token |
| `403 You do not have permission...` | Logged in with the wrong role for that action | Check the role table above; log in as the right role |
| `400 Invalid status transition` | Tried to skip a step in the workflow | Only move one arrow at a time (see workflow diagram) |
| CORS error in the browser console | Frontend origin not in `CORS_ORIGINS` | Add the exact frontend URL (or use `*` for local dev only) |
| Supabase insert/select errors mentioning RLS | Using the `anon` key instead of `service_role` | Double check `SUPABASE_KEY` in `.env`/Render is the service_role key |
| `relation "bugs" does not exist` | `sql/schema.sql` not run yet | Run it in the Supabase SQL Editor |
| `column users.project_id does not exist` / `relation "notifications" does not exist` | Database created with the old schema | Run `sql/migrations/001_projects_notifications_support.sql` |
| `403 Join or create a project first` | Account has no project yet | Sign in on the website; the Welcome page lets you join with a code or create a project |
| Registering says "Invite code not found" | Typo, or the admin made a new code | Copy the current code from the admin dashboard |
| Bell never updates until refresh | Several gunicorn workers, or a proxy buffering the stream | Use the `Procfile` command (1 worker, threads) |
| `permission denied for table faqs` (code `42501`) in the backend log | The table exists but was never granted to `service_role` | Run `sql/migrations/003_grant_service_role.sql` in the Supabase SQL Editor; `/api/health/setup` then shows every table `ok` |
| `httpx.ReadError: [WinError 10035] A non-blocking socket operation could not be completed immediately` (Windows) | The Supabase library shared one HTTP/2 connection between parallel requests | Fixed in this version (the backend talks to Supabase over HTTP/1.1). Re-copy the backend files and restart `python run.py` |
| "Couldn't load the FAQ" / Help Center error / "The server ran into a problem (error 502)" with an older version | One sync worker + an open live-notification stream blocked every other request | Update to this version (it stops streaming on such servers), and set Render's Start Command to the `Procfile` command |
| Help chat says "no FAQs yet" / never finds an answer | The project's FAQ is empty (e.g. made by the first version of migration 001) | Run `sql/migrations/002_seed_starter_faqs.sql`, or click **Add starter FAQs** on the Help Center page |
| No emails arrive | SMTP not configured or wrong app password | Check the server log for `Email (SMTP not configured` or `Failed to send email` |
| App crashes on Render but works locally | Missing environment variables in Render's dashboard | Re-add all vars from `.env.example` under Render → Environment |

---

## 9. Security Notes
- Passwords are hashed with `werkzeug.security.generate_password_hash`
  (PBKDF2-SHA256) — plain-text passwords are never stored.
- `password_hash` is never included in any API response.
- Registration always assigns the `tester` role server-side, ignoring any
  `role` field sent by the client — this prevents privilege escalation at
  sign-up. Promotions to `developer`/`admin` must go through an existing
  admin's `PUT /api/users/<id>/role`.
- All secrets (`SUPABASE_URL`, `SUPABASE_KEY`, `JWT_SECRET_KEY`) live only
  in environment variables, never in code, and `.env` should be listed in
  `.gitignore`.
- Supabase Row Level Security is enabled on every table with no policies,
  so only the backend's `service_role` key can access the data directly.

---

## 10. Backend Workflow Summary for this project

1. A **Tester** finds a bug and calls `POST /api/bugs` — it's stored in
   Supabase with `status = "Open"` and a `created` entry is written to
   `bug_history`.
2. An **Admin** calls `PUT /api/bugs/<id>/assign` to hand it to a
   **Developer**; this is logged as an `assignment_changed` history entry.
3. The **Developer** calls `PUT /api/bugs/<id>/status` to move it
   `Open → In Progress` and later `In Progress → Resolved`. Every status
   change is checked against both the workflow diagram (is this move legal
   at all?) and the caller's role (is *this person* allowed to make *this*
   move?), then logged to `bug_history`.
4. The **Tester** verifies the fix, optionally leaving a comment via
   `POST /api/bugs/<id>/comments`, then calls
   `PUT /api/bugs/<id>/status` with `"Closed"` if it's fixed, or
   `"Reopened"` (which routes back to the developer) if it isn't.
5. At any point, anyone with permission to view the bug can call
   `GET /api/bugs/<id>/history` to see the complete, timestamped trail of
   who changed what — this is what makes the system auditable.

Throughout, a single JWT (issued at login) authenticates every request,
and a small stack of two decorators — `@token_required` then
`@role_required(...)` — enforces exactly who is allowed to do what.
