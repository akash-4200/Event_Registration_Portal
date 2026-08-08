# Event Registration Portal

A full-stack event registration system built with **HTML, CSS, JavaScript,
raw SQL (SQLite)**, and a lightweight **Flask (Python)** backend connecting
them — three roles (Student, Organizer, Admin), QR-code tickets, CSV/PDF
exports, a live QR attendance scanner, and dark/light mode.

> **Want to deploy this?** See [`DEPLOYMENT.md`](DEPLOYMENT.md) for a
> tested, step-by-step guide to deploying on Render (free tier), including
> the persistent-disk setup needed so your data survives restarts.

> **Scope note (read this first):** the original feature list ran to 106
> items. Building every single one as a fully separate, production-grade
> feature isn't realistic in one project — so instead of faking breadth with
> stub pages, this implements a genuinely working system covering every
> phase, with a few items intentionally simplified and clearly flagged below
> (see **What's Simplified / Not Included**). Everything listed as
> "implemented" was actually run end-to-end and tested before being handed
> to you — not just written and assumed to work.

## Why raw SQL instead of an ORM

You listed **SQL** as a skill, not just "a database" — so this project uses
plain `sqlite3` with parameterized queries throughout (`db.py`, `schema.sql`),
instead of hiding everything behind SQLAlchemy. That means you can actually
point to real `JOIN`s, `GROUP BY` aggregates, and `CHECK` constraints in
`schema.sql` and `admin/routes.py` and explain them in an interview — which
is a stronger signal than "I used an ORM and it handled the SQL for me."

## Features Implemented

**Phase 1 — Authentication**
Register, Login, Logout, Forgot/Reset Password, Change Password, Profile
Management, Role-Based Access Control (student/organizer/admin).

**Phase 2 — Student Module**
Dashboard, browse events with computed Upcoming/Ongoing/Completed status,
search & filter (name, category, mode, free/paid, time status), event
details with countdown timer, Register/Cancel, waitlist auto-promotion,
My Registrations, QR ticket, printable receipt, calendar (.ics) download,
Favorites/Bookmarks, Feedback & Rating, Certificate (PDF) download,
in-app notifications.

**Phase 3 — Organizer Module**
Dashboard, Create/Edit/Delete event, Publish (submit for approval) /
Unpublish, poster upload (validated), registration deadline & capacity,
participant list + search, CSV export, mark attendance (manual button +
live camera QR scan), send announcements, per-event stats with a
registrations-over-time chart.

**Phase 4 — Admin Module**
Dashboard, manage students/organizers (block/unblock, reset password),
approve/reject events, delete any event, manage categories, system-wide
reports.

**Phase 5 — Event Management**
Categories, venue, schedule, seat availability counter, waitlist, auto
seat allocation on cancellation, tags, event gallery *(poster image only
— see note below)*, feedback, rating, certificate generation.

**Phase 6 — Notifications**
In-app notifications for: registration confirmation, waitlist promotion,
event approval/rejection, organizer announcements. (Bell icon + unread
count in the navbar.)

**Phase 7 — Reports & Analytics**
Total users, total/active/completed events, event-wise registration
report, department-wise participation, monthly registration trend
(chart), attendance report, feedback analysis, most popular events —
all computed with real SQL `JOIN`/`GROUP BY` queries, rendered with
Chart.js.

**Phase 8 — Search & Filters**
By name, category, venue/organizer (via search box), date/time-status,
free/paid, online/offline.

**Phase 9 — Additional Features**
QR code generation & live scanning (`html5-qrcode` via CDN), countdown
timer, favorites/bookmarks, calendar (.ics) integration, share event
(copy link), FAQ and Help & Support pages.

**Phase 10 — Security**
Password hashing (Werkzeug's `generate_password_hash`), session-based
auth, Role-Based Access Control decorators, server-side form validation
(mirrored client-side for fast feedback), parameterized SQL everywhere
(no string-formatted queries — see `db.py`), file upload validation
(extension whitelist + 5MB size limit), activity log table recording
key actions.

**Dark / Light mode** — toggle in the navbar, persisted via
`localStorage`, respects system preference on first visit.

## What's Simplified / Not Included

Being upfront about this matters more than pretending it's all there:

- **Email/SMS delivery isn't wired up.** Forgot-password links and
  admin-generated temporary passwords are shown directly in a flash
  message (`[DEV MODE] ...`) instead of emailed, since that would need
  real SMTP/SMS credentials this project can't ship with. The code path
  (token generation, expiry, validation) is fully real — only the
  "send it" step is stubbed. Swapping in `Flask-Mail` + real credentials
  is a small, contained change in `auth/routes.py`.
- **Event gallery** is a single poster image per event, not a multi-photo
  gallery — extending to multiple images just means a second table
  (`event_photos`) and a loop in the upload form.
- **Payment for paid events** is tracked (`is_paid`, `price`) but there's
  no real payment gateway integration — that needs a provider account
  (Razorpay/Stripe) this project can't include credentials for.
- **QR attendance scanning** requires camera access, which needs HTTPS
  or `localhost` in the browser — it will show a clear fallback message
  if the camera is unavailable, and manual attendance-marking always
  works as a backup.

## Project Structure

```
event_portal/
├── app.py                  # Flask application factory + entry point
├── config.py                # Paths, upload limits, session settings
├── schema.sql                # Full raw-SQL schema (tables, constraints, indexes)
├── db.py                     # Parameterized query helpers (SQL injection protection)
├── decorators.py              # @login_required, @role_required (RBAC)
├── utils.py                   # QR codes, CSV export, .ics files, PDF certificates
├── seed.py                    # Demo data: 1 admin, 2 organizers, 3 students, 6 events
├── requirements.txt
├── auth/                       # Phase 1: register, login, password reset, profile
├── student/                    # Phase 2: browse, register, tickets, feedback
├── organizer/                  # Phase 3: event CRUD, participants, attendance, stats
├── admin/                      # Phase 4 + 7: user/event management, reports
├── templates/                  # Jinja2 templates, organized to match the blueprints
└── static/
    ├── css/style.css            # Design system + dark/light theme (CSS variables)
    ├── js/main.js                # Theme toggle, countdown timer, star rating, validation
    └── uploads/                  # posters/, qrcodes/, certificates/ (created at runtime)
```

## Setup

```bash
python -m venv venv
source venv/bin/activate      # macOS/Linux
venv\Scripts\activate         # Windows

pip install -r requirements.txt
```

## Running It

```bash
python seed.py     # creates the database + demo accounts (run once)
python app.py       # starts the dev server at http://127.0.0.1:5000
```

### Demo accounts (created by `seed.py`)

| Role | Email | Password |
|---|---|---|
| Admin | admin@events.com | admin1234 |
| Organizer | priya.organizer@events.com | organizer123 |
| Organizer | rahul.organizer@events.com | organizer123 |
| Student | aisha.student@events.com | student1234 |
| Student | rohan.student@events.com | student1234 |
| Student | sneha.student@events.com | student1234 |

To reset all data, delete `instance/event_portal.db` and run `python seed.py`
again.

## How the Approval Workflow Works

1. Organizer creates an event → saved as **draft**.
2. Organizer clicks "Submit for Approval" → status becomes **pending**.
3. Admin reviews it on the Admin Dashboard → **approves** (becomes
   **published**, visible to students) or **rejects**.
4. If an organizer edits an already-published event, it's automatically
   sent back to **pending** for re-approval — so students never see
   unreviewed changes.

## How Seat Allocation Works

- A student registering gets **confirmed** if seats remain, otherwise
  **waitlisted**.
- If a confirmed student cancels, the earliest waitlisted student is
  **automatically promoted** to confirmed and notified — this is the
  "Auto Seat Allocation" feature, implemented as a small piece of logic
  in `student/routes.py::cancel_registration`, not a background job.

## Testing Notes

Every route across all three roles (auth, student, organizer, admin) was
exercised with Flask's test client before this was handed to you,
including: the full register → ticket → receipt → cancel → waitlist
promotion flow, CSV export, PDF certificate generation, RBAC enforcement
(a student hitting `/admin/dashboard` correctly gets a 403), blocked-user
login rejection, and a SQL-injection login attempt (correctly rejected,
since every query uses `?` placeholders — see `db.py`).

## Talking Points for an Interview

- **Why raw SQL over an ORM** — direct control over joins/aggregates for
  the reporting queries; a stronger demonstration of SQL fundamentals.
- **RBAC as decorators** (`decorators.py`) rather than checking roles
  inline in every route — keeps authorization logic in one place and
  makes each route's access requirement visible at a glance.
- **Waitlist auto-promotion** — a concrete example of a business rule
  (not just CRUD) implemented directly in the cancellation flow.
- **Security tradeoffs made explicit** — e.g., login/registration errors
  are deliberately generic ("invalid email or password") to avoid
  leaking which accounts exist; forgot-password always shows the same
  message regardless of whether the email is registered.
- **What you'd add with more time/infra** — real email delivery, a
  payment gateway, multi-photo event galleries, and possibly moving
  from SQLite to PostgreSQL for concurrent write load at scale.
