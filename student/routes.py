"""
student/routes.py
-----------------
Phase 2 - Student Module:
  Dashboard, browse events (upcoming/ongoing/completed), search & filter,
  event details, register/cancel, view registrations, receipt, QR ticket,
  bookmarks, feedback & rating, certificate download, calendar (.ics),
  notifications.
"""

from datetime import datetime

from flask import (
    render_template, request, redirect, url_for, session, flash,
    send_from_directory, Response, current_app,
)

from . import student_bp
from db import query, query_one, execute
from decorators import login_required, role_required
from utils import (
    generate_ticket_code, generate_qr_code, generate_ics,
    generate_certificate_pdf, log_activity, create_notification,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def compute_time_status(event) -> str:
    """Derives upcoming/ongoing/completed from the event's start/end datetimes."""
    now = datetime.now()
    start = datetime.fromisoformat(event["start_datetime"])
    end = datetime.fromisoformat(event["end_datetime"])
    if now < start:
        return "upcoming"
    elif start <= now <= end:
        return "ongoing"
    return "completed"


def seats_taken(event_id: int) -> int:
    row = query_one(
        "SELECT COUNT(*) AS c FROM registrations WHERE event_id = ? AND status = 'confirmed'",
        (event_id,),
    )
    return row["c"]


# --------------------------------------------------------------------------- #
# Dashboard
# --------------------------------------------------------------------------- #
@student_bp.route("/dashboard")
@role_required("student")
def dashboard():
    student_id = session["user_id"]

    upcoming_count = query_one(
        """SELECT COUNT(*) AS c FROM registrations r JOIN events e ON r.event_id = e.id
           WHERE r.student_id = ? AND r.status = 'confirmed' AND e.start_datetime > ?""",
        (student_id, datetime.now().isoformat()),
    )["c"]

    total_registrations = query_one(
        "SELECT COUNT(*) AS c FROM registrations WHERE student_id = ? AND status != 'cancelled'",
        (student_id,),
    )["c"]

    unread_notifications = query_one(
        "SELECT COUNT(*) AS c FROM notifications WHERE user_id = ? AND is_read = 0",
        (student_id,),
    )["c"]

    recent_events = query(
        """SELECT * FROM events WHERE status = 'published'
           ORDER BY start_datetime ASC LIMIT 5"""
    )

    return render_template(
        "student/dashboard.html",
        upcoming_count=upcoming_count,
        total_registrations=total_registrations,
        unread_notifications=unread_notifications,
        recent_events=recent_events,
        compute_time_status=compute_time_status,
    )


# --------------------------------------------------------------------------- #
# Browse / Search / Filter events
# --------------------------------------------------------------------------- #
@student_bp.route("/events")
@role_required("student")
def events_list():
    search = request.args.get("q", "").strip()
    category_id = request.args.get("category", "")
    mode = request.args.get("mode", "")
    paid = request.args.get("paid", "")
    time_filter = request.args.get("time_status", "")

    sql = """
        SELECT e.*, c.name AS category_name, u.name AS organizer_name
        FROM events e
        LEFT JOIN categories c ON e.category_id = c.id
        LEFT JOIN users u ON e.organizer_id = u.id
        WHERE e.status = 'published'
    """
    params = []

    if search:
        sql += " AND (e.title LIKE ? OR e.venue LIKE ? OR u.name LIKE ? OR e.tags LIKE ?)"
        like = f"%{search}%"
        params += [like, like, like, like]

    if category_id:
        sql += " AND e.category_id = ?"
        params.append(category_id)

    if mode in ("online", "offline"):
        sql += " AND e.mode = ?"
        params.append(mode)

    if paid == "free":
        sql += " AND e.is_paid = 0"
    elif paid == "paid":
        sql += " AND e.is_paid = 1"

    sql += " ORDER BY e.start_datetime ASC"

    events = query(sql, tuple(params))

    # Time-based status is computed in Python (not stored), then filtered here
    if time_filter in ("upcoming", "ongoing", "completed"):
        events = [e for e in events if compute_time_status(e) == time_filter]

    categories = query("SELECT * FROM categories ORDER BY name")

    bookmarked_ids = {
        row["event_id"] for row in
        query("SELECT event_id FROM bookmarks WHERE student_id = ?", (session["user_id"],))
    }

    return render_template(
        "student/events_list.html",
        events=events,
        categories=categories,
        compute_time_status=compute_time_status,
        seats_taken=seats_taken,
        bookmarked_ids=bookmarked_ids,
        filters=request.args,
    )


# --------------------------------------------------------------------------- #
# Event details
# --------------------------------------------------------------------------- #
@student_bp.route("/events/<int:event_id>")
@role_required("student")
def event_detail(event_id):
    event = query_one(
        """SELECT e.*, c.name AS category_name, u.name AS organizer_name
           FROM events e
           LEFT JOIN categories c ON e.category_id = c.id
           LEFT JOIN users u ON e.organizer_id = u.id
           WHERE e.id = ? AND e.status = 'published'""",
        (event_id,),
    )
    if not event:
        flash("Event not found.", "danger")
        return redirect(url_for("student.events_list"))

    registration = query_one(
        "SELECT * FROM registrations WHERE event_id = ? AND student_id = ? AND status != 'cancelled'",
        (event_id, session["user_id"]),
    )

    is_bookmarked = query_one(
        "SELECT 1 FROM bookmarks WHERE event_id = ? AND student_id = ?",
        (event_id, session["user_id"]),
    ) is not None

    rating_row = query_one(
        "SELECT AVG(rating) AS avg_rating, COUNT(*) AS count FROM feedback WHERE event_id = ?",
        (event_id,),
    )

    return render_template(
        "student/event_detail.html",
        event=event,
        registration=registration,
        seats_taken=seats_taken(event_id),
        time_status=compute_time_status(event),
        is_bookmarked=is_bookmarked,
        avg_rating=rating_row["avg_rating"],
        rating_count=rating_row["count"],
    )


# --------------------------------------------------------------------------- #
# Register / Cancel
# --------------------------------------------------------------------------- #
@student_bp.route("/events/<int:event_id>/register", methods=["POST"])
@role_required("student")
def register_event(event_id):
    student_id = session["user_id"]
    event = query_one("SELECT * FROM events WHERE id = ? AND status = 'published'", (event_id,))

    if not event:
        flash("Event not found.", "danger")
        return redirect(url_for("student.events_list"))

    if datetime.now() > datetime.fromisoformat(event["registration_deadline"]):
        flash("Registration deadline has passed for this event.", "danger")
        return redirect(url_for("student.event_detail", event_id=event_id))

    existing = query_one(
        "SELECT * FROM registrations WHERE event_id = ? AND student_id = ? AND status != 'cancelled'",
        (event_id, student_id),
    )
    if existing:
        flash("You're already registered for this event.", "info")
        return redirect(url_for("student.event_detail", event_id=event_id))

    taken = seats_taken(event_id)
    status = "confirmed" if taken < event["max_participants"] else "waitlisted"

    ticket_code = generate_ticket_code()
    generate_qr_code(ticket_code)

    execute(
        """INSERT INTO registrations (event_id, student_id, status, ticket_code)
           VALUES (?, ?, ?, ?)""",
        (event_id, student_id, status, ticket_code),
    )

    log_activity(student_id, "event_registered", f"event_id={event_id}, status={status}")

    if status == "confirmed":
        create_notification(student_id, f"You're registered for '{event['title']}'. See you there!")
        flash(f"Registered successfully! Your ticket code is {ticket_code}.", "success")
    else:
        create_notification(student_id, f"'{event['title']}' is full -- you've been added to the waitlist.")
        flash("This event is full. You've been added to the waitlist.", "warning")

    return redirect(url_for("student.my_registrations"))


@student_bp.route("/events/<int:event_id>/cancel", methods=["POST"])
@role_required("student")
def cancel_registration(event_id):
    student_id = session["user_id"]
    registration = query_one(
        "SELECT * FROM registrations WHERE event_id = ? AND student_id = ? AND status != 'cancelled'",
        (event_id, student_id),
    )
    if not registration:
        flash("No active registration found for this event.", "danger")
        return redirect(url_for("student.my_registrations"))

    was_confirmed = registration["status"] == "confirmed"
    execute("UPDATE registrations SET status = 'cancelled' WHERE id = ?", (registration["id"],))
    log_activity(student_id, "registration_cancelled", f"event_id={event_id}")
    flash("Registration cancelled.", "info")

    # --- Auto seat allocation: promote the earliest waitlisted student ---
    if was_confirmed:
        next_in_line = query_one(
            """SELECT * FROM registrations WHERE event_id = ? AND status = 'waitlisted'
               ORDER BY registered_at ASC LIMIT 1""",
            (event_id,),
        )
        if next_in_line:
            execute("UPDATE registrations SET status = 'confirmed' WHERE id = ?", (next_in_line["id"],))
            event = query_one("SELECT title FROM events WHERE id = ?", (event_id,))
            create_notification(
                next_in_line["student_id"],
                f"A seat opened up for '{event['title']}' -- you're now confirmed!",
            )

    return redirect(url_for("student.my_registrations"))


# --------------------------------------------------------------------------- #
# My registrations
# --------------------------------------------------------------------------- #
@student_bp.route("/my-registrations")
@role_required("student")
def my_registrations():
    registrations = query(
        """SELECT r.*, e.title, e.start_datetime, e.end_datetime, e.venue, e.id AS event_id
           FROM registrations r JOIN events e ON r.event_id = e.id
           WHERE r.student_id = ? ORDER BY e.start_datetime DESC""",
        (session["user_id"],),
    )
    return render_template(
        "student/my_registrations.html",
        registrations=registrations,
        compute_time_status=compute_time_status,
    )


# --------------------------------------------------------------------------- #
# Ticket (QR) + Receipt
# --------------------------------------------------------------------------- #
@student_bp.route("/ticket/<int:registration_id>")
@role_required("student")
def ticket(registration_id):
    reg = query_one(
        """SELECT r.*, e.title, e.venue, e.start_datetime FROM registrations r
           JOIN events e ON r.event_id = e.id
           WHERE r.id = ? AND r.student_id = ?""",
        (registration_id, session["user_id"]),
    )
    if not reg:
        flash("Ticket not found.", "danger")
        return redirect(url_for("student.my_registrations"))

    return render_template("student/ticket.html", reg=reg)


@student_bp.route("/receipt/<int:registration_id>")
@role_required("student")
def receipt(registration_id):
    reg = query_one(
        """SELECT r.*, e.title, e.venue, e.start_datetime, e.price, e.is_paid FROM registrations r
           JOIN events e ON r.event_id = e.id
           WHERE r.id = ? AND r.student_id = ?""",
        (registration_id, session["user_id"]),
    )
    if not reg:
        flash("Receipt not found.", "danger")
        return redirect(url_for("student.my_registrations"))

    student = query_one("SELECT * FROM users WHERE id = ?", (session["user_id"],))
    return render_template("student/receipt.html", reg=reg, student=student)


@student_bp.route("/calendar/<int:event_id>.ics")
@role_required("student")
def download_calendar(event_id):
    event = query_one("SELECT * FROM events WHERE id = ?", (event_id,))
    if not event:
        flash("Event not found.", "danger")
        return redirect(url_for("student.events_list"))

    ics_content = generate_ics(event)
    return Response(
        ics_content,
        mimetype="text/calendar",
        headers={"Content-Disposition": f"attachment; filename={event['title']}.ics"},
    )


# --------------------------------------------------------------------------- #
# Bookmarks / Favorites
# --------------------------------------------------------------------------- #
@student_bp.route("/events/<int:event_id>/bookmark", methods=["POST"])
@role_required("student")
def toggle_bookmark(event_id):
    student_id = session["user_id"]
    existing = query_one(
        "SELECT * FROM bookmarks WHERE event_id = ? AND student_id = ?", (event_id, student_id)
    )
    if existing:
        execute("DELETE FROM bookmarks WHERE id = ?", (existing["id"],))
        flash("Removed from favorites.", "info")
    else:
        execute("INSERT INTO bookmarks (student_id, event_id) VALUES (?, ?)", (student_id, event_id))
        flash("Added to favorites.", "success")
    return redirect(request.referrer or url_for("student.events_list"))


@student_bp.route("/favorites")
@role_required("student")
def favorites():
    events = query(
        """SELECT e.* FROM bookmarks b JOIN events e ON b.event_id = e.id
           WHERE b.student_id = ? ORDER BY b.created_at DESC""",
        (session["user_id"],),
    )
    return render_template(
        "student/events_list.html", events=events, categories=[],
        compute_time_status=compute_time_status, seats_taken=seats_taken,
        bookmarked_ids={e["id"] for e in events}, filters={}, is_favorites_page=True,
    )


# --------------------------------------------------------------------------- #
# Feedback & Rating
# --------------------------------------------------------------------------- #
@student_bp.route("/events/<int:event_id>/feedback", methods=["GET", "POST"])
@role_required("student")
def feedback(event_id):
    student_id = session["user_id"]
    event = query_one("SELECT * FROM events WHERE id = ?", (event_id,))

    attended = query_one(
        "SELECT * FROM registrations WHERE event_id = ? AND student_id = ? AND attended = 1",
        (event_id, student_id),
    )
    if not attended:
        flash("Feedback is only available for events you attended.", "warning")
        return redirect(url_for("student.my_registrations"))

    existing = query_one(
        "SELECT * FROM feedback WHERE event_id = ? AND student_id = ?", (event_id, student_id)
    )

    if request.method == "POST":
        rating = int(request.form.get("rating", 0))
        comment = request.form.get("comment", "").strip()

        if rating < 1 or rating > 5:
            flash("Please select a rating between 1 and 5.", "danger")
        else:
            if existing:
                execute(
                    "UPDATE feedback SET rating = ?, comment = ? WHERE id = ?",
                    (rating, comment, existing["id"]),
                )
            else:
                execute(
                    "INSERT INTO feedback (event_id, student_id, rating, comment) VALUES (?, ?, ?, ?)",
                    (event_id, student_id, rating, comment),
                )
            flash("Thanks for your feedback!", "success")
            return redirect(url_for("student.my_registrations"))

    return render_template("student/feedback.html", event=event, existing=existing)


# --------------------------------------------------------------------------- #
# Certificate download
# --------------------------------------------------------------------------- #
@student_bp.route("/events/<int:event_id>/certificate")
@role_required("student")
def certificate(event_id):
    student_id = session["user_id"]
    reg = query_one(
        "SELECT * FROM registrations WHERE event_id = ? AND student_id = ? AND attended = 1",
        (event_id, student_id),
    )
    if not reg:
        flash("Certificates are only available after attending the event.", "warning")
        return redirect(url_for("student.my_registrations"))

    event = query_one("SELECT * FROM events WHERE id = ?", (event_id,))
    student = query_one("SELECT * FROM users WHERE id = ?", (student_id,))

    event_date = datetime.fromisoformat(event["start_datetime"]).strftime("%B %d, %Y")
    filename = generate_certificate_pdf(student["name"], event["title"], event_date)

    return send_from_directory(current_app.config["CERTIFICATE_FOLDER"], filename, as_attachment=True)


# --------------------------------------------------------------------------- #
# Notifications
# --------------------------------------------------------------------------- #
@student_bp.route("/notifications")
@login_required
def notifications():
    rows = query(
        "SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC LIMIT 30",
        (session["user_id"],),
    )
    execute("UPDATE notifications SET is_read = 1 WHERE user_id = ?", (session["user_id"],))
    return render_template("student/notifications.html", notifications=rows)
