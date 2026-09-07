# Bug Tracking System — Backend API

A Flask + Supabase (PostgreSQL) REST API for a university Bug Tracking System,
with JWT authentication and role-based access control for three roles:
**Admin**, **Tester**, and **Developer**.

This repo is backend-only (no frontend), built for CSC480.

---

## 1. Project Structure

```
bug-tracking-backend/
│
├── app/
│   ├── __init__.py          # Flask app factory: creates the app, wires up
│   │                         # CORS, the Supabase client, and blueprints
│   ├── config.py             # Loads env vars, creates the Supabase client
│   │
│   ├── routes/
│   │   ├── auth.py           # /api/auth/* - register, login, me
│   │   ├── bugs.py           # /api/bugs/* - CRUD, assign, status, history
│   │   ├── comments.py       # /api/bugs/<id>/comments
│   │   └── users.py          # /api/users/* - admin user management
│   │
│   ├── middleware/
│   │   ├── auth.py           # JWT create/verify + @token_required decorator
│   │   └── permissions.py    # @role_required(...) decorator (RBAC)
│   │
│   └── utils/
│       ├── responses.py      # success_response()/error_response() helpers
│       └── validators.py     # field validation + status-transition rules
│
├── tests/
│   └── test_api.py           # pytest integration tests (12 scenarios)
│
├── sql/
│   └── schema.sql            # run this in the Supabase SQL editor
│
├── postman/
│   └── Bug_Tracking_API.postman_collection.json
│
├── .env.example
├── requirements.txt
├── run.py                    # local dev entry point
├── Procfile                  # tells Render how to start the app
└── README.md
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
    supabase = current_app.config["SUPABASE_CLIENT"]
    ...
    return success_response(...) / error_response(...)
```

---

## 2. Supabase Setup

1. Create a project at [supabase.com](https://supabase.com).
2. Go to **SQL Editor → New query**, paste the contents of `sql/schema.sql`,
   and run it. This creates `users`, `bugs`, `comments`, and `bug_history`
   with the right foreign keys, `CHECK` constraints, and indexes.
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

### Creating your first Admin
`POST /api/auth/register` always creates a **tester** account on purpose
(see security notes below) — nobody can register themselves in as an admin.
To get your first Admin/Developer accounts:
1. Register normally through the API.
2. In Supabase's **Table Editor → users**, edit that row's `role` column to
   `admin` (or `developer`).
3. From then on, that Admin can promote other users via
   `PUT /api/users/<id>/role`.

---

## 4. API Documentation

All responses share this shape:
```json
{ "success": true,  "message": "...", "data": { ... } }
{ "success": false, "message": "...", "errors": { ... } }
```

### Auth
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/api/auth/register` | – | Create account (always role=`tester`) |
| POST | `/api/auth/login` | – | Returns `{ token, user }` |
| GET | `/api/auth/me` | any | Current user's profile |

### Users
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/api/users` | admin | List all users |
| GET | `/api/users/developers` | any | List developers (for assign dropdown) |
| PUT | `/api/users/<id>/role` | admin | Change a user's role |

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
pip install pytest
# pre-create one admin + one developer account (see section 3), then:
export TEST_ADMIN_EMAIL=admin@example.com
export TEST_ADMIN_PASSWORD=Passw0rd!
export TEST_DEVELOPER_EMAIL=developer@example.com
export TEST_DEVELOPER_PASSWORD=Passw0rd!
pytest tests/test_api.py -v
```
These are integration tests — they run against whatever Supabase project
your `.env` points at, so consider using a separate test project.

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
   - **Start Command**: `gunicorn run:app --bind 0.0.0.0:$PORT` (already in `Procfile`, Render auto-detects it)
4. Add Environment Variables in the Render dashboard (Environment tab):
   `SUPABASE_URL`, `SUPABASE_KEY`, `JWT_SECRET_KEY`, `JWT_EXPIRES_HOURS`,
   `CORS_ORIGINS`, `FLASK_ENV=production`.
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
