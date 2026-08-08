"""
admin/routes.py
---------------
Phase 4 - Admin Module + Phase 7 - Reports & Analytics:
  Dashboard, manage students/organizers (block/unblock, reset password),
  approve/reject events, manage categories, system reports.

The reporting queries here lean on raw SQL joins/aggregates (GROUP BY,
COUNT, AVG) rather than pulling everything into Python and looping --
this is deliberately the part of the project that shows the most SQL,
since aggregate reporting is exactly where SQL earns its keep over
just fetching rows and calculating in application code.
"""

import secrets
from datetime import datetime

from flask import render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash

from . import admin_bp
from db import query, query_one, execute
from decorators import role_required
from utils import log_activity, create_notification


# --------------------------------------------------------------------------- #
# Dashboard
# --------------------------------------------------------------------------- #
@admin_bp.route("/dashboard")
@role_required("admin")
def dashboard():
    now = datetime.now().isoformat()

    counts = {
        "students": query_one("SELECT COUNT(*) AS c FROM users WHERE role = 'student'")["c"],
        "organizers": query_one("SELECT COUNT(*) AS c FROM users WHERE role = 'organizer'")["c"],
        "total_events": query_one("SELECT COUNT(*) AS c FROM events")["c"],
        "pending_events": query_one("SELECT COUNT(*) AS c FROM events WHERE status = 'pending'")["c"],
        "active_events": query_one(
            "SELECT COUNT(*) AS c FROM events WHERE status = 'published' AND end_datetime > ?", (now,)
        )["c"],
        "completed_events": query_one(
            "SELECT COUNT(*) AS c FROM events WHERE status = 'published' AND end_datetime <= ?", (now,)
        )["c"],
        "total_registrations": query_one(
            "SELECT COUNT(*) AS c FROM registrations WHERE status != 'cancelled'"
        )["c"],
    }

    pending_events = query(
        """SELECT e.*, u.name AS organizer_name FROM events e JOIN users u ON e.organizer_id = u.id
           WHERE e.status = 'pending' ORDER BY e.created_at ASC LIMIT 5"""
    )

    return render_template("admin/dashboard.html", counts=counts, pending_events=pending_events)


# --------------------------------------------------------------------------- #
# Manage users (students & organizers share the same logic)
# --------------------------------------------------------------------------- #
@admin_bp.route("/users/<role>")
@role_required("admin")
def manage_users(role):
    if role not in ("student", "organizer"):
        flash("Invalid role.", "danger")
        return redirect(url_for("admin.dashboard"))

    search = request.args.get("q", "").strip()
    sql = "SELECT * FROM users WHERE role = ?"
    params = [role]
    if search:
        sql += " AND (name LIKE ? OR email LIKE ?)"
        params += [f"%{search}%", f"%{search}%"]
    sql += " ORDER BY created_at DESC"

    users = query(sql, tuple(params))
    return render_template("admin/manage_users.html", users=users, role=role, search=search)


@admin_bp.route("/users/<int:user_id>/toggle-block", methods=["POST"])
@role_required("admin")
def toggle_block_user(user_id):
    user = query_one("SELECT * FROM users WHERE id = ?", (user_id,))
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("admin.dashboard"))

    new_state = 0 if user["is_blocked"] else 1
    execute("UPDATE users SET is_blocked = ? WHERE id = ?", (new_state, user_id))
    log_activity(session["user_id"], "user_block_toggled", f"user_id={user_id}, blocked={new_state}")
    flash(f"{user['name']} has been {'blocked' if new_state else 'unblocked'}.", "success")
    return redirect(url_for("admin.manage_users", role=user["role"]))


@admin_bp.route("/users/<int:user_id>/reset-password", methods=["POST"])
@role_required("admin")
def admin_reset_password(user_id):
    user = query_one("SELECT * FROM users WHERE id = ?", (user_id,))
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("admin.dashboard"))

    temp_password = secrets.token_urlsafe(9)
    execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (generate_password_hash(temp_password), user_id),
    )
    log_activity(session["user_id"], "admin_password_reset", f"user_id={user_id}")

    # NOTE: as with forgot-password, no email service is wired up -- in
    # production this temporary password would be emailed, not flashed.
    flash(f"Password reset for {user['name']}. Temporary password: {temp_password}", "info")
    return redirect(url_for("admin.manage_users", role=user["role"]))


# --------------------------------------------------------------------------- #
# Manage events: approve / reject / delete
# --------------------------------------------------------------------------- #
@admin_bp.route("/events")
@role_required("admin")
def manage_events():
    status_filter = request.args.get("status", "")
    sql = """SELECT e.*, u.name AS organizer_name, c.name AS category_name
             FROM events e JOIN users u ON e.organizer_id = u.id
             LEFT JOIN categories c ON e.category_id = c.id"""
    params = []
    if status_filter:
        sql += " WHERE e.status = ?"
        params.append(status_filter)
    sql += " ORDER BY e.created_at DESC"

    events = query(sql, tuple(params))
    return render_template("admin/manage_events.html", events=events, status_filter=status_filter)


@admin_bp.route("/events/<int:event_id>/approve", methods=["POST"])
@role_required("admin")
def approve_event(event_id):
    event = query_one("SELECT * FROM events WHERE id = ?", (event_id,))
    if not event:
        flash("Event not found.", "danger")
        return redirect(url_for("admin.manage_events"))

    execute("UPDATE events SET status = 'published' WHERE id = ?", (event_id,))
    log_activity(session["user_id"], "event_approved", event["title"])
    create_notification(event["organizer_id"], f"Your event '{event['title']}' was approved and is now live.")
    flash("Event approved and published.", "success")
    return redirect(url_for("admin.manage_events"))


@admin_bp.route("/events/<int:event_id>/reject", methods=["POST"])
@role_required("admin")
def reject_event(event_id):
    event = query_one("SELECT * FROM events WHERE id = ?", (event_id,))
    if not event:
        flash("Event not found.", "danger")
        return redirect(url_for("admin.manage_events"))

    execute("UPDATE events SET status = 'rejected' WHERE id = ?", (event_id,))
    log_activity(session["user_id"], "event_rejected", event["title"])
    create_notification(event["organizer_id"], f"Your event '{event['title']}' was rejected by the admin.")
    flash("Event rejected.", "info")
    return redirect(url_for("admin.manage_events"))


@admin_bp.route("/events/<int:event_id>/delete", methods=["POST"])
@role_required("admin")
def admin_delete_event(event_id):
    event = query_one("SELECT * FROM events WHERE id = ?", (event_id,))
    if not event:
        flash("Event not found.", "danger")
        return redirect(url_for("admin.manage_events"))

    execute("DELETE FROM events WHERE id = ?", (event_id,))
    log_activity(session["user_id"], "event_deleted_by_admin", event["title"])
    flash("Event deleted.", "info")
    return redirect(url_for("admin.manage_events"))


# --------------------------------------------------------------------------- #
# Manage categories
# --------------------------------------------------------------------------- #
@admin_bp.route("/categories", methods=["GET", "POST"])
@role_required("admin")
def manage_categories():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Category name cannot be empty.", "danger")
        else:
            existing = query_one("SELECT id FROM categories WHERE name = ?", (name,))
            if existing:
                flash("That category already exists.", "warning")
            else:
                execute("INSERT INTO categories (name) VALUES (?)", (name,))
                flash("Category added.", "success")
        return redirect(url_for("admin.manage_categories"))

    categories = query(
        """SELECT c.*, (SELECT COUNT(*) FROM events e WHERE e.category_id = c.id) AS event_count
           FROM categories c ORDER BY c.name"""
    )
    return render_template("admin/manage_categories.html", categories=categories)


@admin_bp.route("/categories/<int:category_id>/delete", methods=["POST"])
@role_required("admin")
def delete_category(category_id):
    execute("DELETE FROM categories WHERE id = ?", (category_id,))
    flash("Category deleted.", "info")
    return redirect(url_for("admin.manage_categories"))


# --------------------------------------------------------------------------- #
# Reports & Analytics (Phase 7)
# --------------------------------------------------------------------------- #
@admin_bp.route("/reports")
@role_required("admin")
def reports():
    now = datetime.now().isoformat()

    totals = {
        "total_users": query_one("SELECT COUNT(*) AS c FROM users")["c"],
        "total_events": query_one("SELECT COUNT(*) AS c FROM events")["c"],
        "active_events": query_one(
            "SELECT COUNT(*) AS c FROM events WHERE status='published' AND end_datetime > ?", (now,)
        )["c"],
        "completed_events": query_one(
            "SELECT COUNT(*) AS c FROM events WHERE status='published' AND end_datetime <= ?", (now,)
        )["c"],
    }

    # Event-wise registration report: how many confirmed sign-ups per event
    event_registrations = query(
        """SELECT e.title, COUNT(r.id) AS registration_count
           FROM events e LEFT JOIN registrations r ON e.id = r.event_id AND r.status = 'confirmed'
           GROUP BY e.id ORDER BY registration_count DESC LIMIT 10"""
    )

    # Department-wise participation
    department_participation = query(
        """SELECT u.department, COUNT(r.id) AS count
           FROM registrations r JOIN users u ON r.student_id = u.id
           WHERE r.status != 'cancelled' AND u.department != ''
           GROUP BY u.department ORDER BY count DESC"""
    )

    # Monthly participation report (registration trend)
    monthly_trend = query(
        """SELECT strftime('%Y-%m', registered_at) AS month, COUNT(*) AS count
           FROM registrations WHERE status != 'cancelled'
           GROUP BY month ORDER BY month"""
    )

    # Attendance report: attended vs registered per event
    attendance_report = query(
        """SELECT e.title,
                  COUNT(r.id) AS total_registered,
                  SUM(CASE WHEN r.attended = 1 THEN 1 ELSE 0 END) AS total_attended
           FROM events e LEFT JOIN registrations r ON e.id = r.event_id AND r.status != 'cancelled'
           GROUP BY e.id HAVING total_registered > 0
           ORDER BY total_registered DESC LIMIT 10"""
    )

    # Feedback analysis
    feedback_summary = query(
        """SELECT e.title, AVG(f.rating) AS avg_rating, COUNT(f.id) AS review_count
           FROM feedback f JOIN events e ON f.event_id = e.id
           GROUP BY e.id ORDER BY avg_rating DESC LIMIT 10"""
    )

    # Most popular events (by confirmed registrations)
    most_popular = query(
        """SELECT e.title,
                  (SELECT COUNT(*) FROM registrations r WHERE r.event_id = e.id AND r.status = 'confirmed') AS count
           FROM events e ORDER BY count DESC LIMIT 5"""
    )

    return render_template(
        "admin/reports.html", totals=totals, event_registrations=event_registrations,
        department_participation=department_participation, monthly_trend=monthly_trend,
        attendance_report=attendance_report, feedback_summary=feedback_summary,
        most_popular=most_popular,
    )
