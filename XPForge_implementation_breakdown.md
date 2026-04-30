# XPForge — Complete Implementation Breakdown

---

## 🔧 Bug Fix Applied
Two issues caused the transparent mobile dropdown:
1. **`--bg-elevated: #21253300`** — the `00` at the end is a hex alpha channel set to zero, making that token **fully transparent**. Fixed to `#212533`.
2. **Mobile `.notif-dropdown`** — when the dropdown goes `position: fixed` (full-screen), it was missing an explicit `background`, `backdrop-filter: none`, and `-webkit-backdrop-filter: none`. Without those, the `backdrop-filter` inherited from the parent `.navbar` bleed through and neutralized the background. Now explicitly set.

---

## 📚 Library Inventory

### Backend (Python)

| Library | Why It's Used |
|---|---|
| **Flask** | Micro web framework. Serves the API AND the static frontend from a single process (`static_folder="../frontend"`). Chosen for its simplicity, Blueprint modularity, and zero overhead. |
| **firebase-admin** | Official Google SDK to connect Flask to **Firestore** (the NoSQL database). Used for all reads, writes, and queries on collections like `users`, `tasks`, `daily_plans`, `xp_logs`, etc. |
| **PyJWT (`jwt`)** | Signs and verifies JSON Web Tokens. Every protected API route decodes the `Authorization: Bearer <token>` header to extract `user_id`. Tokens expire after a configurable number of hours. |
| **bcrypt** | Secure, adaptive password hashing. `bcrypt.hashpw()` on signup, `bcrypt.checkpw()` on login. Resistant to GPU brute-force because it's intentionally slow. |
| **flask-cors** | Adds `Access-Control-Allow-Origin` headers to all `/api/*` routes so the frontend (served from the same origin) and any external clients can make fetch requests without CORS errors. |
| **flask-limiter** | Rate limits requests — 60 per minute per user by default. The key function extracts the JWT `user_id` when available (so rate-limits are per-account, not per-IP), falling back to remote IP. |
| **APScheduler** (`BackgroundScheduler`, `CronTrigger`) | Runs background cron jobs inside the Flask process without needing a separate worker/Celery. Four jobs are registered: midnight finalization, morning reminder (08:00 UTC), evening reminder (20:00 UTC), and hourly battle check. |
| **pytz** | Timezone-aware date calculations. Every user stores a `timezone` field; `pytz.timezone(tz_str)` converts UTC "now" to their local date so "today" and "tomorrow" are always correct for that user. |
| **py-vapid / pywebpush** | Generates VAPID keys and delivers Web Push notifications to browser endpoints (Chrome, Firefox, etc.) using the RFC 8292 standard. |
| **smtplib** (stdlib) | Sends password-reset emails. Tries `SMTP_SSL` (port 465) first, falls back to `STARTTLS` (port 587) on failure — resilient to server configuration differences. |

### Frontend (JavaScript / HTML / CSS)

| Library/API | Why It's Used |
|---|---|
| **Bootstrap 5.3** | Grid system, utility classes (`d-flex`, `gap-2`, `ms-auto`, etc.), modal components. Used purely for layout scaffolding — all visual design is overridden by `style.css`. |
| **Lucide Icons** | SVG icon library loaded from CDN (`unpkg.com/lucide`). Rendered by `lucide.createIcons()` which scans the DOM for `data-lucide="<icon-name>"` attributes and injects the SVG. Chosen for crisp, consistent strokes. |
| **Google Identity Services** (`accounts.google.com/gsi/client`) | Renders the "Continue with Google" button. On credential receipt, the `handleGoogleCredential` callback fires, which sends the ID token to `/api/auth/google`. The backend verifies it with Google's tokeninfo endpoint. |
| **Service Worker API** (`sw.js`) | Enables the app as a **Progressive Web App (PWA)**. Intercepts fetch requests for offline caching, listens for `push` events to show OS notifications, and handles `sync` events to replay queued API calls when connectivity returns. |
| **PushManager API** | Browser-native API used in `api.js → subscribeToPush()` to register the browser with a push server using VAPID keys. The subscription object (endpoint + keys) is POSTed to `/api/users/me/push-subscription`. |
| **localStorage** | Persists `jwt_token` and `user_data` across page refreshes. `getToken()` / `setToken()` / `clearToken()` in `api.js` are the only functions that touch it — keeping auth state centralized. |
| **Inter + Space Grotesk** (Google Fonts) | Two fonts. Inter is the body/UI font (clean, readable at small sizes). Space Grotesk is the display font used for headers, stats, rank numbers — it has a distinctive, technical personality. |

---

## 🗂️ Firestore Collections (The Data Model)

```
users/            {user_id}          → profile, total_xp, timezone, clan_id, push subscription
daily_plans/      {plan_id}          → user_id, date (YYYY-MM-DD), locked (bool)
tasks/            {task_id}          → user_id, plan_id, title, type, status, date, xp_awarded
xp_logs/          {log_id}          → user_id, task_id, xp_delta, reason, is_provisional
leaderboards/     {period_type}/
                    {period_key}/
                      entries/{user_id} → username, xp, avatar_color, rank
clans/            {clan_id}          → name, member_ids[], created_by
clan_battles/     {battle_id}        → clan_a_id, clan_b_id, status, end_at, winner_clan_id
notifications/    {notif_id}         → user_id, type, message, read, created_at, metadata
password_resets/  {token}            → user_id, email, expires_at, used
```

---

## 🔄 Data Flow: From User Action → Dashboard

### Step 0 — App Startup (`run.py` → `app/__init__.py`)

```
run.py → create_app()
  ├─ Flask("../frontend")     # Flask also serves static files
  ├─ CORS(app)                # Allow cross-origin API calls
  ├─ Limiter(app)             # 60 req/min rate limit
  ├─ init_firebase()          # Connect to Firestore
  ├─ Register 8 Blueprints    # auth, plan, task, leaderboard, clan, battle, notification, user
  ├─ Route "/" → index.html   # Catch-all for SPA routing
  └─ start_scheduler(app)     # Start APScheduler background jobs
```

Firebase connects using a service account JSON — either a file path (`firebase_credentials.json`) or a JSON string injected as an environment variable (`FIREBASE_CREDENTIALS_JSON`). The second approach is how Railway (the deployment platform) receives secrets without file commits.

---

### Step 1 — Authentication Flow

**Signup (email/password):**
1. Browser POSTs `{email, password, username, timezone}` to `/api/auth/signup`
2. Backend queries Firestore: no duplicate email or username allowed
3. `bcrypt.hashpw()` hashes the password
4. User document is written to `users/` collection
5. `update_all_leaderboards()` initializes the user with 0 XP on all 5 leaderboard periods
6. A JWT is signed (`HS256`, expires in N hours) and returned
7. Frontend stores token in `localStorage` and redirects to `dashboard.html`

**Login:**
- If `identifier` contains `@`, queries `where("email", "==", ...)`, else queries `where("username", "==", ...)`
- `bcrypt.checkpw()` validates the password
- Fresh JWT returned

**Google Sign-In:**
- GIS library sends a `credential` (ID token) to the callback `handleGoogleCredential`
- Frontend POSTs that token to `/api/auth/google`
- Backend calls `https://oauth2.googleapis.com/tokeninfo?id_token=...` to verify it with Google
- Checks `aud` claim matches the configured Google Client ID
- Upserts the user (creates on first sign-in, returns existing on subsequent)
- Google users have `password_hash: null` — the login route detects this and blocks password login

**JWT Middleware (`app/middleware.py`):**
Every protected route is decorated with `@require_auth`. This decorator decodes the JWT, extracts `user_id`, and stores it in Flask's `g` object. Route handlers then use `g.user_id` directly — no re-authentication logic needed inside routes.

---

### Step 2 — Daily Plan Creation

When `dashboard.html` loads:
```
dashboard.js → loadDashboard()
  POST /api/plans/create   ← creates today's plan if not exists
  GET  /api/plans/today    ← returns { plan, tasks[] }
```

**`POST /api/plans/create`:**
- Queries `daily_plans` where `user_id == g.user_id` AND `date == today_for_user`
- If no document exists, creates one: `{ user_id, date, locked: false }`
- Uses `pytz` to compute "today" in the user's local timezone

**`GET /api/plans/today`:**
- Returns the plan document + all tasks for that date
- Tasks are keyed by `date == today` AND `user_id == g.user_id`

---

### Step 3 — Task Management

**Adding a task (`POST /api/tasks/add`):**
1. Middleware verifies JWT → `g.user_id`
2. Fetches user's timezone → computes `today`
3. Checks plan is not locked (for planned tasks)
4. Counts existing tasks of that type (max 10 planned, max 5 unplanned)
5. Writes task to `tasks/` collection with `status: "pending"`, `xp_awarded: null`
6. Returns the task JSON → `dashboard.js` pushes it into the local `_tasks[]` array and re-renders

**Completing a task (`PATCH /api/tasks/:id/complete`):**
```
task_routes.complete_task()
  ├─ Verify ownership (task.user_id == g.user_id)
  ├─ Verify status == "pending"
  ├─ Update task: { status: "completed", completed_at: now }
  └─ award_provisional_xp(user_id, task_id, task_type)
        ├─ _has_xp_log_for_task()  ← duplicate guard
        ├─ _append_xp_log()        ← writes to xp_logs/
        ├─ user.total_xp += xp_delta  (7 for planned, 3 for unplanned)
        └─ update_all_leaderboards()  ← updates 5 leaderboard subcollections
              └─ Rank-change notifications if user overtook someone
```

**Carry-Over (`POST /api/tasks/:id/carry-over`):**
1. Validates task is `pending`, `planned`, not already carried
2. Checks tomorrow won't exceed 10 tasks
3. Writes `-2 XP` log immediately (non-provisional)
4. Updates `user.total_xp`
5. Marks original task `status: "carried_over"`, `carried_over: true`
6. Creates a **clone task** with `date: tomorrow` and `carried_from_task_id` reference

---

### Step 4 — XP Economy

All XP math lives exclusively in `app/services/xp_service.py`:

| Action | XP | Timing |
|---|---|---|
| Complete planned task | +7 | Immediately (provisional) |
| Fail planned task (manual) | −4 | Immediately (provisional) |
| Complete unplanned task | +3 | Immediately (provisional) |
| Carry task to tomorrow | −2 | Immediately (final) |
| Auto-fail at midnight | −4 | Finalized at 00:00 UTC |

**Provisional vs Final:**
- All XP awarded during the day has `is_provisional: true` in the `xp_logs` collection
- At midnight, the scheduler flips all provisional logs to `is_provisional: false` in a **batch write** (single Firestore roundtrip)
- This design allows future features like "dispute resolution" or "admin override" without losing an audit trail
- The `_has_xp_log_for_task()` duplicate guard prevents awarding XP twice if a route is somehow called twice

---

### Step 5 — Leaderboard Update

Every XP mutation calls `update_all_leaderboards(user_id, xp_delta, username, avatar_color)`:

```python
for period_type in ["daily", "weekly", "monthly", "yearly", "global"]:
    key = _period_key(period_type)   # e.g., "2026-04-30" / "2026-W18" / "2026-04" / "2026" / "all-time"
    ref = leaderboards/{period_type}/{key}/entries/{user_id}
    if doc.exists:
        update xp += xp_delta
    else:
        set { user_id, username, xp: xp_delta, rank: 0 }
```

Ranks are computed **at read time** (not stored), by sorting the entries by XP descending and assigning `rank = index + 1`. This avoids maintaining rank across concurrent writes.

---

### Step 6 — The Scheduler (Nightly Jobs)

APScheduler runs four background jobs inside the Flask process context:

**Midnight (00:00 UTC) — `_run_midnight_job()`:**
1. Find all `daily_plans` where `date == yesterday` AND `locked == true`
2. For each plan, find `tasks` where `status == "pending"` AND `type == "planned"`
3. Mark them `failed` and call `finalize_xp_for_task()` (−4 XP, non-provisional log)
4. Batch-update all provisional XP logs → `is_provisional: false`
5. Assign **Beast** badge (top of daily leaderboard) and **Slacker** badge (bottom)
6. Send daily summary notifications (rank + XP earned)
7. Send peer task completion notifications to clan members
8. Check **Ghost** badge (inactive user) and **Committed** badge (consecutive-day streak) for all users
9. Finalize any clan battles whose `end_at` has passed — determine winner by average XP

**Morning (08:00 UTC) — `_run_morning_reminder_job()`:**
- Per user, in their local timezone: if no planned tasks yet → `notify_no_tasks_created`
- If tasks exist but plan not locked → `notify_no_plan_locked`
- Deduplicated: one notification per type per day

**Evening (20:00 UTC) — `_run_evening_reminder_job()`:**
- Per user: if any planned tasks are still `pending` → `notify_tasks_pending(count)`
- Deduplicated per day

**Hourly — `_run_battle_check_job()`:**
- For every active clan battle: compute average XP for both clans
- If losing clan is behind by ≥1 XP: notify each member once per battle per day

---

### Step 7 — Notification System (In-App + Web Push)

**In-app notifications** are written as documents to the `notifications/` Firestore collection:
```json
{
  "user_id": "...",
  "type": "rank_overtaken",
  "message": "BeastMode99 just overtook you! Get back to work! 💪",
  "read": false,
  "created_at": "ISO timestamp"
}
```

**Fetching notifications (`GET /api/notifications`):**
- Returns last 20 unread notifications for the authenticated user
- The bell icon's badge count shows the unread count
- Clicking "Mark all read" POSTs to `/api/notifications/mark-read` which batch-updates all `read: false` docs

**Web Push notifications (`push_service.py`):**
When a user grants browser notification permission:
1. `subscribeToPush()` in `api.js` fetches the VAPID public key from `/api/users/vapid-key`
2. Calls `registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey })` 
3. POSTs the subscription object (endpoint + encryption keys) to `/api/users/me/push-subscription`
4. Backend stores it on the user document
5. When the scheduler (or rank-change event) needs to notify someone, it calls `push_service.send_push()` which uses pywebpush to POST to the browser's push endpoint
6. The **Service Worker** receives the `push` event even when the app is closed, and calls `self.registration.showNotification()` to display the OS-level popup

**VAPID key mismatch detection:**
When VAPID keys are rotated (e.g., after a deploy), the client detects the mismatch by comparing the existing subscription's `applicationServerKey` with the one fetched from the server. On mismatch, it calls `subscription.unsubscribe()` then re-subscribes with the new key automatically.

---

### Step 8 — How the Dashboard Renders

The frontend is a **Multi-Page Application (MPA)** — each page is a separate HTML file. There is no React/Vue/Angular. All rendering is vanilla JS DOM manipulation.

**Data flow on dashboard load:**
```
DOMContentLoaded
  → requireLogin()           checks localStorage for JWT, redirects to / if missing
  → getUser()                parses user_data from localStorage
  → initNotifications()      sets up bell click handler, fetches + renders notifications
  → loadDashboard()
      → POST /api/plans/create  (idempotent — no-ops if plan exists)
      → GET /api/plans/today    returns { plan: {...}, tasks: [...] }
      → _plan = data.plan
      → _tasks = data.tasks
      → renderAll()
          → renderDateHeader()     formats today's date
          → renderStatsStrip()     counts done/planned/unplanned from _tasks[]
          → renderPlanStatus()     shows/hides lock button based on _plan.locked
          → renderTaskList("planned")    generates HTML for each task
          → renderTaskList("unplanned")
```

**Task rendering (`renderTaskItem(task)`):**
The function builds HTML strings (not DOM nodes) for performance. Each task gets:
- A checkbox div (state: checked / failed-check / empty)
- The task title (XSS-escaped via `escHtml()`)
- A type badge (planned / unplanned)
- An XP chip — if `task.xp_awarded` is set it shows the actual delta; if still pending it shows the provisional estimate
- Action buttons — conditional on task type and plan lock state:
  - Planned + not locked → shows "Lock plan to complete" message, no action buttons
  - Planned + locked + pending → shows Done / Fail / Carry buttons
  - Unplanned + pending → shows Done button always (no lock requirement)

**Optimistic state updates:**
When a task is completed, the frontend:
1. Immediately updates `_tasks[idx].status = "completed"` and `_tasks[idx].xp_awarded = result.xp_delta`
2. Updates `user.total_xp` in localStorage
3. Calls `renderAll()` — the DOM is synchronously rebuilt from the updated state
4. Applies `xp-pop` CSS animation to the XP stat card

There's no polling — the dashboard reflects state from the last API fetch. Reloading or navigating away and back re-fetches fresh data.

---

## 🔌 Offline / PWA Layer

The Service Worker (`sw.js`) implements two capabilities:

**1. Cache-first serving:**
- Static assets (HTML, CSS, JS) are cached on install
- Subsequent requests are served from cache first (fast), then updated in background

**2. Offline queue (`offline-queue.js`):**
- Mutating API calls (`POST`, `PATCH`) that fail due to no network are saved to **IndexedDB**
- On reconnect (`online` event or `sync` event), the queued requests are replayed in order
- Success triggers `showToast("Offline actions synced!")` and re-renders the dashboard

---

## 🚀 Deployment Architecture

```
Railway (cloud)
  └─ Gunicorn (Procfile: web: gunicorn run:app)
       └─ Flask app
            ├─ Serves frontend/  (static files)
            ├─ /api/*            (REST endpoints)
            └─ APScheduler       (background thread, same process)
                  └─ All jobs run with app.app_context() to access Firestore
```

Environment variables on Railway (not in repo):
- `SECRET_KEY` — JWT signing key
- `FIREBASE_CREDENTIALS_JSON` — the full service account JSON as a string
- `VAPID_PRIVATE_KEY` / `VAPID_PUBLIC_KEY` — Web Push keys
- `SMTP_EMAIL` / `SMTP_PASSWORD` — Gmail app password for reset emails
- `GOOGLE_CLIENT_ID` — for verifying Google ID tokens
- `APP_URL` — used in reset email links

