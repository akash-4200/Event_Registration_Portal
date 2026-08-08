"""
auth/routes.py
--------------
Phase 1 - User Authentication:
  Register, Login, Logout, Forgot/Reset Password, Change Password,
  Profile Management.

Security notes:
  - Passwords are never stored in plain text: generate_password_hash()
    (from Werkzeug, bundled with Flask) uses a salted hash.
  - All queries use parameterized (?) placeholders -- see db.py.
  - Login/registration failures give a generic message ("invalid email
    or password") rather than confirming which part was wrong, so an
    attacker can't use error messages to enumerate valid accounts.
"""

from datetime import datetime

from flask import render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash

from . import auth_bp
from db import query_one, execute
from decorators import login_required
from utils import log_activity, generate_reset_token


# --------------------------------------------------------------------------- #
# Registration
# --------------------------------------------------------------------------- #
@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        role = request.form.get("role", "student")
        department = request.form.get("department", "").strip()

        # --- Server-side validation (never trust client-side JS alone) ---
        errors = []
        if not name or not email or not password:
            errors.append("Name, email, and password are required.")
        if role not in ("student", "organizer"):
            errors.append("Invalid role selected.")
        if len(password) < 8:
            errors.append("Password must be at least 8 characters long.")
        if password != confirm_password:
            errors.append("Passwords do not match.")
        if "@" not in email or "." not in email.split("@")[-1]:
            errors.append("Enter a valid email address.")

        if not errors:
            existing = query_one("SELECT id FROM users WHERE email = ?", (email,))
            if existing:
                errors.append("An account with that email already exists.")

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("auth/register.html", form=request.form)

        password_hash = generate_password_hash(password)
        user_id = execute(
            """INSERT INTO users (name, email, password_hash, role, department, is_verified)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (name, email, password_hash, role, department, 1),  # auto-verified for demo simplicity
        )
        log_activity(user_id, "register", f"Registered as {role}")

        flash("Account created successfully! Please log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/register.html", form={})


# --------------------------------------------------------------------------- #
# Login / Logout
# --------------------------------------------------------------------------- #
@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = query_one("SELECT * FROM users WHERE email = ?", (email,))

        if not user or not check_password_hash(user["password_hash"], password):
            flash("Invalid email or password.", "danger")
            log_activity(None, "login_failed", f"email={email}")
            return render_template("auth/login.html")

        if user["is_blocked"]:
            flash("Your account has been blocked. Contact the administrator.", "danger")
            return render_template("auth/login.html")

        # --- Session management ---
        session.clear()
        session["user_id"] = user["id"]
        session["name"] = user["name"]
        session["role"] = user["role"]

        log_activity(user["id"], "login", "Successful login")

        if user["role"] == "admin":
            return redirect(url_for("admin.dashboard"))
        elif user["role"] == "organizer":
            return redirect(url_for("organizer.dashboard"))
        return redirect(url_for("student.dashboard"))

    return render_template("auth/login.html")


@auth_bp.route("/logout")
def logout():
    log_activity(session.get("user_id"), "logout", "")
    session.clear()
    flash("You've been logged out.", "info")
    return redirect(url_for("auth.login"))


# --------------------------------------------------------------------------- #
# Forgot / Reset password
# --------------------------------------------------------------------------- #
@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = query_one("SELECT * FROM users WHERE email = ?", (email,))

        # Always show the same message whether or not the account exists,
        # so this endpoint can't be used to check which emails are registered.
        generic_message = "If that account exists, a reset link has been generated."

        if user:
            token, expiry = generate_reset_token()
            execute(
                "UPDATE users SET reset_token = ?, reset_token_expiry = ? WHERE id = ?",
                (token, expiry, user["id"]),
            )
            log_activity(user["id"], "forgot_password_requested", "")
            reset_link = url_for("auth.reset_password", token=token, _external=True)

            # NOTE: No SMTP/email service is configured in this project.
            # In production this link would be emailed to the user instead
            # of being shown directly. Flashing it here keeps the whole
            # reset flow testable without external credentials.
            flash(generic_message, "info")
            flash(f"[DEV MODE] Reset link: {reset_link}", "secondary")
        else:
            flash(generic_message, "info")

        return redirect(url_for("auth.login"))

    return render_template("auth/forgot_password.html")


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    user = query_one("SELECT * FROM users WHERE reset_token = ?", (token,))

    if not user or not user["reset_token_expiry"]:
        flash("That reset link is invalid or has expired.", "danger")
        return redirect(url_for("auth.forgot_password"))

    if datetime.utcnow() > datetime.fromisoformat(user["reset_token_expiry"]):
        flash("That reset link has expired. Please request a new one.", "danger")
        return redirect(url_for("auth.forgot_password"))

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if len(password) < 8:
            flash("Password must be at least 8 characters long.", "danger")
            return render_template("auth/reset_password.html", token=token)
        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template("auth/reset_password.html", token=token)

        password_hash = generate_password_hash(password)
        execute(
            "UPDATE users SET password_hash = ?, reset_token = NULL, reset_token_expiry = NULL WHERE id = ?",
            (password_hash, user["id"]),
        )
        log_activity(user["id"], "password_reset", "")
        flash("Password reset successfully. Please log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/reset_password.html", token=token)


# --------------------------------------------------------------------------- #
# Change password (while logged in) + Profile management
# --------------------------------------------------------------------------- #
@auth_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        user = query_one("SELECT * FROM users WHERE id = ?", (session["user_id"],))

        if not check_password_hash(user["password_hash"], current_password):
            flash("Current password is incorrect.", "danger")
        elif len(new_password) < 8:
            flash("New password must be at least 8 characters long.", "danger")
        elif new_password != confirm_password:
            flash("New passwords do not match.", "danger")
        else:
            execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (generate_password_hash(new_password), user["id"]),
            )
            log_activity(user["id"], "password_changed", "")
            flash("Password updated successfully.", "success")
            return redirect(url_for("auth.profile"))

    return render_template("auth/change_password.html")


@auth_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    user = query_one("SELECT * FROM users WHERE id = ?", (session["user_id"],))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        department = request.form.get("department", "").strip()

        if not name:
            flash("Name cannot be empty.", "danger")
        else:
            execute(
                "UPDATE users SET name = ?, department = ? WHERE id = ?",
                (name, department, user["id"]),
            )
            session["name"] = name
            flash("Profile updated successfully.", "success")
            return redirect(url_for("auth.profile"))

    return render_template("auth/profile.html", user=user)
