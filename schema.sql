-- schema.sql
-- ---------------------------------------------------------------------------
-- Full database schema for the Event Registration Portal.
-- Written in raw SQL (not hidden behind an ORM) so the queries, joins,
-- constraints, and indexes are all explicit and interview-defensible.
-- Run automatically by db.py on first startup (init_db()).
-- ---------------------------------------------------------------------------

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------------
-- Users: students, organizers, and admins all live in one table, split by role.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT NOT NULL,
    email               TEXT NOT NULL UNIQUE,
    password_hash       TEXT NOT NULL,
    role                TEXT NOT NULL CHECK (role IN ('student', 'organizer', 'admin')),
    department          TEXT DEFAULT '',
    is_blocked          INTEGER NOT NULL DEFAULT 0,
    is_verified         INTEGER NOT NULL DEFAULT 0,
    reset_token         TEXT,
    reset_token_expiry  TEXT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------------------
-- Event categories (managed by admin)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS categories (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    name    TEXT NOT NULL UNIQUE
);

-- ---------------------------------------------------------------------------
-- Events created by organizers, approved/rejected by admin.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS events (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    title                  TEXT NOT NULL,
    description            TEXT NOT NULL DEFAULT '',
    poster_filename        TEXT,
    category_id            INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    organizer_id           INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    venue                  TEXT NOT NULL DEFAULT '',
    mode                   TEXT NOT NULL DEFAULT 'offline' CHECK (mode IN ('online', 'offline')),
    start_datetime         TEXT NOT NULL,
    end_datetime           TEXT NOT NULL,
    registration_deadline  TEXT NOT NULL,
    max_participants       INTEGER NOT NULL DEFAULT 50,
    is_paid                INTEGER NOT NULL DEFAULT 0,
    price                  REAL NOT NULL DEFAULT 0,
    tags                   TEXT DEFAULT '',
    -- draft: organizer still editing | pending: awaiting admin approval
    -- published: live and visible to students | rejected: admin rejected
    -- cancelled: organizer/admin cancelled after publishing
    status                 TEXT NOT NULL DEFAULT 'draft'
                           CHECK (status IN ('draft', 'pending', 'published', 'rejected', 'cancelled')),
    created_at             TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_events_status ON events(status);
CREATE INDEX IF NOT EXISTS idx_events_organizer ON events(organizer_id);
CREATE INDEX IF NOT EXISTS idx_events_category ON events(category_id);

-- ---------------------------------------------------------------------------
-- Registrations: a student signing up for an event.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS registrations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id        INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    student_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    -- confirmed: has a seat | waitlisted: event was full | cancelled: student cancelled
    status          TEXT NOT NULL DEFAULT 'confirmed'
                    CHECK (status IN ('confirmed', 'waitlisted', 'cancelled')),
    ticket_code     TEXT NOT NULL UNIQUE,
    registered_at   TEXT NOT NULL DEFAULT (datetime('now')),
    attended        INTEGER NOT NULL DEFAULT 0,
    attended_at     TEXT,
    UNIQUE (event_id, student_id)
);

CREATE INDEX IF NOT EXISTS idx_registrations_event ON registrations(event_id);
CREATE INDEX IF NOT EXISTS idx_registrations_student ON registrations(student_id);

-- ---------------------------------------------------------------------------
-- Feedback + rating left by students after attending an event.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS feedback (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id    INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    student_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    rating      INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    comment     TEXT DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (event_id, student_id)
);

-- ---------------------------------------------------------------------------
-- In-app notifications (registration confirmed, event cancelled, etc.)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS notifications (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    message     TEXT NOT NULL,
    is_read     INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id);

-- ---------------------------------------------------------------------------
-- Bookmarked / favorited events
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bookmarks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    event_id    INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (student_id, event_id)
);

-- ---------------------------------------------------------------------------
-- Activity log (security / audit trail)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS activity_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER REFERENCES users(id) ON DELETE SET NULL,
    action      TEXT NOT NULL,
    details     TEXT DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
