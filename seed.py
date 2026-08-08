"""
seed.py
-------
Populates the database with demo data so the app isn't empty on first
run: one admin, two organizers, three students, a few categories, and
a handful of events in different statuses (draft, pending, published).

Run with:
    python seed.py

Safe to re-run -- it checks for existing data first and skips seeding
if the database already has users in it.
"""

from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash

from app import create_app
from db import get_db, query_one, execute


def seed():
    app = create_app()
    with app.app_context():
        existing = query_one("SELECT COUNT(*) AS c FROM users")["c"]
        if existing > 0:
            print("Database already has users -- skipping seed. "
                  "Delete instance/event_portal.db to reseed from scratch.")
            return

        def make_user(name, email, password, role, department=""):
            return execute(
                """INSERT INTO users (name, email, password_hash, role, department, is_verified)
                   VALUES (?, ?, ?, ?, ?, 1)""",
                (name, email, generate_password_hash(password), role, department),
            )

        admin_id = make_user("Admin User", "admin@events.com", "admin1234", "admin")
        organizer1_id = make_user("Priya Sharma", "priya.organizer@events.com", "organizer123", "organizer", "Computer Science")
        organizer2_id = make_user("Rahul Verma", "rahul.organizer@events.com", "organizer123", "organizer", "Electronics")
        student1_id = make_user("Aisha Khan", "aisha.student@events.com", "student1234", "student", "Computer Science")
        student2_id = make_user("Rohan Gupta", "rohan.student@events.com", "student1234", "student", "Mechanical")
        student3_id = make_user("Sneha Patil", "sneha.student@events.com", "student1234", "student", "Electronics")

        categories = ["Technical", "Cultural", "Sports", "Workshop", "Seminar"]
        category_ids = {}
        for cat in categories:
            category_ids[cat] = execute("INSERT INTO categories (name) VALUES (?)", (cat,))

        now = datetime.now()

        def iso(dt):
            return dt.isoformat(timespec="minutes")

        events = [
            dict(
                title="AI & Machine Learning Hackathon", description="A 24-hour hackathon building ML-powered projects.",
                category_id=category_ids["Technical"], organizer_id=organizer1_id, venue="Main Auditorium",
                mode="offline", start_datetime=iso(now + timedelta(days=10)),
                end_datetime=iso(now + timedelta(days=11)),
                registration_deadline=iso(now + timedelta(days=8)),
                max_participants=100, is_paid=0, price=0, tags="AI ML hackathon coding",
                status="published",
            ),
            dict(
                title="Web Development Workshop", description="Hands-on workshop covering modern frontend and backend basics.",
                category_id=category_ids["Workshop"], organizer_id=organizer1_id, venue="Lab 204",
                mode="offline", start_datetime=iso(now + timedelta(days=3)),
                end_datetime=iso(now + timedelta(days=3, hours=4)),
                registration_deadline=iso(now + timedelta(days=2)),
                max_participants=40, is_paid=1, price=199, tags="web development coding workshop",
                status="published",
            ),
            dict(
                title="Annual Cultural Fest", description="A full day of music, dance, and drama competitions.",
                category_id=category_ids["Cultural"], organizer_id=organizer2_id, venue="Open Ground",
                mode="offline", start_datetime=iso(now + timedelta(days=20)),
                end_datetime=iso(now + timedelta(days=20, hours=8)),
                registration_deadline=iso(now + timedelta(days=18)),
                max_participants=300, is_paid=0, price=0, tags="cultural fest music dance",
                status="published",
            ),
            dict(
                title="Guest Lecture: Future of Robotics", description="An industry expert talk on advances in robotics.",
                category_id=category_ids["Seminar"], organizer_id=organizer2_id, venue="Seminar Hall B",
                mode="online", start_datetime=iso(now - timedelta(days=2)),
                end_datetime=iso(now - timedelta(days=2) + timedelta(hours=2)),
                registration_deadline=iso(now - timedelta(days=3)),
                max_participants=200, is_paid=0, price=0, tags="robotics seminar guest lecture",
                status="published",
            ),
            dict(
                title="Inter-College Cricket Tournament", description="A weekend cricket tournament between college teams.",
                category_id=category_ids["Sports"], organizer_id=organizer2_id, venue="Sports Complex",
                mode="offline", start_datetime=iso(now + timedelta(days=15)),
                end_datetime=iso(now + timedelta(days=16)),
                registration_deadline=iso(now + timedelta(days=12)),
                max_participants=16, is_paid=1, price=50, tags="cricket sports tournament",
                status="pending",
            ),
            dict(
                title="Photography Club Meetup", description="Casual meetup and photo-walk for the photography club.",
                category_id=category_ids["Cultural"], organizer_id=organizer1_id, venue="Campus Garden",
                mode="offline", start_datetime=iso(now + timedelta(days=5)),
                end_datetime=iso(now + timedelta(days=5, hours=2)),
                registration_deadline=iso(now + timedelta(days=4)),
                max_participants=25, is_paid=0, price=0, tags="photography club meetup",
                status="draft",
            ),
        ]

        event_ids = []
        for e in events:
            eid = execute(
                """INSERT INTO events (title, description, category_id, organizer_id, venue, mode,
                                        start_datetime, end_datetime, registration_deadline,
                                        max_participants, is_paid, price, tags, status)
                   VALUES (:title, :description, :category_id, :organizer_id, :venue, :mode,
                           :start_datetime, :end_datetime, :registration_deadline,
                           :max_participants, :is_paid, :price, :tags, :status)""",
                e,
            )
            event_ids.append(eid)

        # A few sample registrations, including one attended (for the past guest lecture)
        import uuid
        def ticket():
            return uuid.uuid4().hex[:12].upper()

        execute(
            "INSERT INTO registrations (event_id, student_id, status, ticket_code) VALUES (?, ?, 'confirmed', ?)",
            (event_ids[0], student1_id, ticket()),
        )
        execute(
            "INSERT INTO registrations (event_id, student_id, status, ticket_code) VALUES (?, ?, 'confirmed', ?)",
            (event_ids[0], student2_id, ticket()),
        )
        execute(
            "INSERT INTO registrations (event_id, student_id, status, ticket_code) VALUES (?, ?, 'confirmed', ?)",
            (event_ids[1], student1_id, ticket()),
        )
        past_reg_id = execute(
            "INSERT INTO registrations (event_id, student_id, status, ticket_code, attended, attended_at) "
            "VALUES (?, ?, 'confirmed', ?, 1, datetime('now'))",
            (event_ids[3], student3_id, ticket()),
        )
        execute(
            "INSERT INTO feedback (event_id, student_id, rating, comment) VALUES (?, ?, 5, 'Really insightful talk!')",
            (event_ids[3], student3_id),
        )

        print("Database seeded successfully.\n")
        print("Demo accounts (all passwords shown below):")
        print("  Admin     -> admin@events.com / admin1234")
        print("  Organizer -> priya.organizer@events.com / organizer123")
        print("  Organizer -> rahul.organizer@events.com / organizer123")
        print("  Student   -> aisha.student@events.com / student1234")
        print("  Student   -> rohan.student@events.com / student1234")
        print("  Student   -> sneha.student@events.com / student1234")


if __name__ == "__main__":
    seed()
