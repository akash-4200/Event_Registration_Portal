"""
organizer/routes.py
--------------------
Phase 3 - Organizer Module:
  Dashboard, create/edit/delete events, publish/unpublish, poster upload,
  registration deadline & capacity, participant list + search, CSV export,
  mark attendance (manual + QR scan), announcements, event stats/reports.
"""

import os
from datetime import datetime

from flask import (
    render_template, request, redirect, url_for, session, flash,
    send_file, jsonify,
)
from werkzeug.utils import secure_filename

from . import organizer_bp
from db import query, query_one, execute
from decorators import role_required
from utils import (
    allowed_file, export_participants_csv, log_activity, create_notification,
)
from config import Config


# --------------------------------------------------------------------------- #
# Dashboard
# --------------------------------------------------------------------------- #
@organizer_bp.route("/dashboard")
@role_required("organizer")
def dashboard():
    organizer_id = session["user_id"]

    events = query(
        """SELECT e.*, c.name AS category_name,
                  (SELECT COUNT(*) FROM registrations r WHERE r.event_id = e.id AND r.status = 'confirmed') AS confirmed_count
           FROM events e LEFT JOIN categories c ON e.category_id = c.id
           WHERE e.organizer_id = ? ORDER BY e.created_at DESC""",
        (organizer_id,),
    )

    stats = {
        "total_events": len(events),
        "pending": sum(1 for e in events if e["status"] == "pending"),
        "published": sum(1 for e in events if e["status"] == "published"),
        "total_participants": sum(e["confirmed_count"] for e in events),
    }

    return render_template("organizer/dashboard.html", events=events, stats=stats)


# --------------------------------------------------------------------------- #
# Create / Edit event
# --------------------------------------------------------------------------- #
def _handle_event_form(event_id=None):
    """Shared validation + save logic for create and edit."""
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    category_id = request.form.get("category_id") or None
    venue = request.form.get("venue", "").strip()
    mode = request.form.get("mode", "offline")
    start_datetime = request.form.get("start_datetime", "")
    end_datetime = request.form.get("end_datetime", "")
    registration_deadline = request.form.get("registration_deadline", "")
    max_participants = request.form.get("max_participants", "0")
    is_paid = 1 if request.form.get("is_paid") == "on" else 0
    price = request.form.get("price", "0") or "0"
    tags = request.form.get("tags", "").strip()

    errors = []
    if not title or not venue or not start_datetime or not end_datetime or not registration_deadline:
        errors.append("Title, venue, and all date/time fields are required.")
    try:
        max_participants = int(max_participants)
        if max_participants < 1:
            errors.append("Maximum participants must be at least 1.")
    except ValueError:
        errors.append("Maximum participants must be a number.")
        max_participants = 0

    try:
        price = float(price)
    except ValueError:
        price = 0.0

    try:
        start_dt = datetime.fromisoformat(start_datetime)
        end_dt = datetime.fromisoformat(end_datetime)
        deadline_dt = datetime.fromisoformat(registration_deadline)
        if end_dt <= start_dt:
            errors.append("End time must be after start time.")
        if deadline_dt > start_dt:
            errors.append("Registration deadline must be before the event starts.")
    except ValueError:
        errors.append("Invalid date/time format.")

    # --- Poster upload validation ---
    poster_filename = None
    file = request.files.get("poster")
    if file and file.filename:
        if not allowed_file(file.filename):
            errors.append("Poster must be an image file (png, jpg, jpeg, gif, webp).")
        else:
            poster_filename = secure_filename(f"event_{datetime.now().timestamp():.0f}_{file.filename}")

    if errors:
        for e in errors:
            flash(e, "danger")
        return None

    if file and file.filename and poster_filename:
        file.save(os.path.join(Config.POSTER_FOLDER, poster_filename))

    return {
        "title": title, "description": description, "category_id": category_id,
        "venue": venue, "mode": mode, "start_datetime": start_datetime,
        "end_datetime": end_datetime, "registration_deadline": registration_deadline,
        "max_participants": max_participants, "is_paid": is_paid, "price": price,
        "tags": tags, "poster_filename": poster_filename,
    }


@organizer_bp.route("/events/new", methods=["GET", "POST"])
@role_required("organizer")
def create_event():
    categories = query("SELECT * FROM categories ORDER BY name")

    if request.method == "POST":
        data = _handle_event_form()
        if data is None:
            return render_template("organizer/event_form.html", categories=categories, event=request.form)

        execute(
            """INSERT INTO events (title, description, poster_filename, category_id, organizer_id,
                                    venue, mode, start_datetime, end_datetime, registration_deadline,
                                    max_participants, is_paid, price, tags, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'draft')""",
            (data["title"], data["description"], data["poster_filename"], data["category_id"],
             session["user_id"], data["venue"], data["mode"], data["start_datetime"],
             data["end_datetime"], data["registration_deadline"], data["max_participants"],
             data["is_paid"], data["price"], data["tags"]),
        )
        log_activity(session["user_id"], "event_created", data["title"])
        flash("Event created as a draft. Publish it when you're ready to submit for approval.", "success")
        return redirect(url_for("organizer.dashboard"))

    return render_template("organizer/event_form.html", categories=categories, event=None)


@organizer_bp.route("/events/<int:event_id>/edit", methods=["GET", "POST"])
@role_required("organizer")
def edit_event(event_id):
    event = query_one(
        "SELECT * FROM events WHERE id = ? AND organizer_id = ?", (event_id, session["user_id"])
    )
    if not event:
        flash("Event not found.", "danger")
        return redirect(url_for("organizer.dashboard"))

    categories = query("SELECT * FROM categories ORDER BY name")

    if request.method == "POST":
        data = _handle_event_form(event_id)
        if data is None:
            return render_template("organizer/event_form.html", categories=categories, event=event)

        # Editing a live event sends it back for re-approval
        new_status = "pending" if event["status"] in ("published", "rejected") else event["status"]
        poster = data["poster_filename"] or event["poster_filename"]

        execute(
            """UPDATE events SET title=?, description=?, poster_filename=?, category_id=?, venue=?,
                                  mode=?, start_datetime=?, end_datetime=?, registration_deadline=?,
                                  max_participants=?, is_paid=?, price=?, tags=?, status=?
               WHERE id = ?""",
            (data["title"], data["description"], poster, data["category_id"], data["venue"],
             data["mode"], data["start_datetime"], data["end_datetime"], data["registration_deadline"],
             data["max_participants"], data["is_paid"], data["price"], data["tags"], new_status, event_id),
        )
        log_activity(session["user_id"], "event_edited", data["title"])
        flash("Event updated.", "success")
        return redirect(url_for("organizer.dashboard"))

    return render_template("organizer/event_form.html", categories=categories, event=event)


@organizer_bp.route("/events/<int:event_id>/delete", methods=["POST"])
@role_required("organizer")
def delete_event(event_id):
    event = query_one(
        "SELECT * FROM events WHERE id = ? AND organizer_id = ?", (event_id, session["user_id"])
    )
    if not event:
        flash("Event not found.", "danger")
        return redirect(url_for("organizer.dashboard"))

    confirmed = query_one(
        "SELECT COUNT(*) AS c FROM registrations WHERE event_id = ? AND status = 'confirmed'",
        (event_id,),
    )["c"]

    if confirmed > 0:
        flash(
            f"Cannot delete: {confirmed} student(s) are registered. Cancel the event instead.",
            "danger",
        )
        return redirect(url_for("organizer.dashboard"))

    execute("DELETE FROM events WHERE id = ?", (event_id,))
    log_activity(session["user_id"], "event_deleted", event["title"])
    flash("Event deleted.", "info")
    return redirect(url_for("organizer.dashboard"))


# --------------------------------------------------------------------------- #
# Publish / Unpublish
# --------------------------------------------------------------------------- #
@organizer_bp.route("/events/<int:event_id>/publish", methods=["POST"])
@role_required("organizer")
def publish_event(event_id):
    event = query_one(
        "SELECT * FROM events WHERE id = ? AND organizer_id = ?", (event_id, session["user_id"])
    )
    if not event:
        flash("Event not found.", "danger")
        return redirect(url_for("organizer.dashboard"))

    execute("UPDATE events SET status = 'pending' WHERE id = ?", (event_id,))
    log_activity(session["user_id"], "event_submitted_for_approval", event["title"])
    flash("Submitted for admin approval.", "success")
    return redirect(url_for("organizer.dashboard"))


@organizer_bp.route("/events/<int:event_id>/unpublish", methods=["POST"])
@role_required("organizer")
def unpublish_event(event_id):
    event = query_one(
        "SELECT * FROM events WHERE id = ? AND organizer_id = ?", (event_id, session["user_id"])
    )
    if not event:
        flash("Event not found.", "danger")
        return redirect(url_for("organizer.dashboard"))

    execute("UPDATE events SET status = 'draft' WHERE id = ?", (event_id,))
    log_activity(session["user_id"], "event_unpublished", event["title"])
    flash("Event unpublished and moved back to drafts.", "info")
    return redirect(url_for("organizer.dashboard"))


# --------------------------------------------------------------------------- #
# Participants
# --------------------------------------------------------------------------- #
@organizer_bp.route("/events/<int:event_id>/participants")
@role_required("organizer")
def participants(event_id):
    event = query_one(
        "SELECT * FROM events WHERE id = ? AND organizer_id = ?", (event_id, session["user_id"])
    )
    if not event:
        flash("Event not found.", "danger")
        return redirect(url_for("organizer.dashboard"))

    search = request.args.get("q", "").strip()
    sql = """SELECT r.*, u.name, u.email, u.department FROM registrations r
             JOIN users u ON r.student_id = u.id WHERE r.event_id = ?"""
    params = [event_id]
    if search:
        sql += " AND (u.name LIKE ? OR u.email LIKE ?)"
        params += [f"%{search}%", f"%{search}%"]
    sql += " ORDER BY r.registered_at ASC"

    rows = query(sql, tuple(params))
    return render_template("organizer/participants.html", event=event, participants=rows, search=search)


@organizer_bp.route("/events/<int:event_id>/participants/export")
@role_required("organizer")
def export_participants(event_id):
    event = query_one(
        "SELECT * FROM events WHERE id = ? AND organizer_id = ?", (event_id, session["user_id"])
    )
    if not event:
        flash("Event not found.", "danger")
        return redirect(url_for("organizer.dashboard"))

    rows = query(
        """SELECT r.*, u.name, u.email, u.department FROM registrations r
           JOIN users u ON r.student_id = u.id WHERE r.event_id = ? ORDER BY r.registered_at ASC""",
        (event_id,),
    )
    buffer = export_participants_csv(rows)
    log_activity(session["user_id"], "participants_exported", event["title"])
    safe_title = "".join(c for c in event["title"] if c.isalnum() or c in " _-").strip() or "event"
    return send_file(
        buffer, mimetype="text/csv", as_attachment=True,
        download_name=f"{safe_title}_participants.csv",
    )


# --------------------------------------------------------------------------- #
# Attendance: manual + QR scan
# --------------------------------------------------------------------------- #
@organizer_bp.route("/events/<int:event_id>/attendance/mark", methods=["POST"])
@role_required("organizer")
def mark_attendance(event_id):
    registration_id = request.form.get("registration_id")
    event = query_one(
        "SELECT * FROM events WHERE id = ? AND organizer_id = ?", (event_id, session["user_id"])
    )
    if not event:
        flash("Event not found.", "danger")
        return redirect(url_for("organizer.dashboard"))

    execute(
        "UPDATE registrations SET attended = 1, attended_at = datetime('now') WHERE id = ? AND event_id = ?",
        (registration_id, event_id),
    )
    flash("Attendance marked.", "success")
    return redirect(url_for("organizer.participants", event_id=event_id))


@organizer_bp.route("/events/<int:event_id>/attendance/scan")
@role_required("organizer")
def scan_attendance_page(event_id):
    event = query_one(
        "SELECT * FROM events WHERE id = ? AND organizer_id = ?", (event_id, session["user_id"])
    )
    if not event:
        flash("Event not found.", "danger")
        return redirect(url_for("organizer.dashboard"))
    return render_template("organizer/scan_attendance.html", event=event)


@organizer_bp.route("/events/<int:event_id>/attendance/scan", methods=["POST"])
@role_required("organizer")
def scan_attendance_api(event_id):
    """AJAX endpoint hit by the QR scanner JS with the decoded ticket code."""
    event = query_one(
        "SELECT * FROM events WHERE id = ? AND organizer_id = ?", (event_id, session["user_id"])
    )
    if not event:
        return jsonify({"success": False, "message": "Event not found."}), 404

    ticket_code = request.json.get("ticket_code", "").strip() if request.is_json else ""
    reg = query_one(
        "SELECT r.*, u.name FROM registrations r JOIN users u ON r.student_id = u.id "
        "WHERE r.ticket_code = ? AND r.event_id = ?",
        (ticket_code, event_id),
    )

    if not reg:
        return jsonify({"success": False, "message": "Ticket code not recognized for this event."})
    if reg["status"] == "cancelled":
        return jsonify({"success": False, "message": f"{reg['name']}'s registration was cancelled."})
    if reg["attended"]:
        return jsonify({"success": False, "message": f"{reg['name']} was already marked present."})

    execute(
        "UPDATE registrations SET attended = 1, attended_at = datetime('now') WHERE id = ?",
        (reg["id"],),
    )
    return jsonify({"success": True, "message": f"Welcome, {reg['name']}! Attendance marked."})


# --------------------------------------------------------------------------- #
# Announcements
# --------------------------------------------------------------------------- #
@organizer_bp.route("/events/<int:event_id>/announce", methods=["GET", "POST"])
@role_required("organizer")
def announce(event_id):
    event = query_one(
        "SELECT * FROM events WHERE id = ? AND organizer_id = ?", (event_id, session["user_id"])
    )
    if not event:
        flash("Event not found.", "danger")
        return redirect(url_for("organizer.dashboard"))

    if request.method == "POST":
        message = request.form.get("message", "").strip()
        if not message:
            flash("Announcement message cannot be empty.", "danger")
        else:
            recipients = query(
                "SELECT student_id FROM registrations WHERE event_id = ? AND status != 'cancelled'",
                (event_id,),
            )
            for r in recipients:
                create_notification(r["student_id"], f"[{event['title']}] {message}")
            log_activity(session["user_id"], "announcement_sent", f"event_id={event_id}, recipients={len(recipients)}")
            flash(f"Announcement sent to {len(recipients)} participant(s).", "success")
            return redirect(url_for("organizer.dashboard"))

    return render_template("organizer/announce.html", event=event)


# --------------------------------------------------------------------------- #
# Stats / Reports
# --------------------------------------------------------------------------- #
@organizer_bp.route("/events/<int:event_id>/stats")
@role_required("organizer")
def stats(event_id):
    event = query_one(
        "SELECT * FROM events WHERE id = ? AND organizer_id = ?", (event_id, session["user_id"])
    )
    if not event:
        flash("Event not found.", "danger")
        return redirect(url_for("organizer.dashboard"))

    confirmed = query_one(
        "SELECT COUNT(*) AS c FROM registrations WHERE event_id = ? AND status = 'confirmed'", (event_id,)
    )["c"]
    waitlisted = query_one(
        "SELECT COUNT(*) AS c FROM registrations WHERE event_id = ? AND status = 'waitlisted'", (event_id,)
    )["c"]
    cancelled = query_one(
        "SELECT COUNT(*) AS c FROM registrations WHERE event_id = ? AND status = 'cancelled'", (event_id,)
    )["c"]
    attended = query_one(
        "SELECT COUNT(*) AS c FROM registrations WHERE event_id = ? AND attended = 1", (event_id,)
    )["c"]
    rating_row = query_one(
        "SELECT AVG(rating) AS avg_rating, COUNT(*) AS count FROM feedback WHERE event_id = ?", (event_id,)
    )

    # Registrations-over-time, for a simple Chart.js line chart
    daily = query(
        """SELECT date(registered_at) AS day, COUNT(*) AS count FROM registrations
           WHERE event_id = ? GROUP BY date(registered_at) ORDER BY day""",
        (event_id,),
    )

    return render_template(
        "organizer/stats.html", event=event, confirmed=confirmed, waitlisted=waitlisted,
        cancelled=cancelled, attended=attended, rating_row=rating_row, daily=daily,
    )
