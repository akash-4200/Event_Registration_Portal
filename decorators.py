"""
decorators.py
-------------
Role-Based Access Control (RBAC) as simple route decorators, built on
top of Flask's session -- no external auth library needed.

Usage:
    @login_required
    def some_route(): ...

    @role_required("organizer", "admin")
    def organizer_only_route(): ...
"""

from functools import wraps

from flask import session, redirect, url_for, flash, abort


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)
    return wrapped


def role_required(*allowed_roles):
    """Restricts a route to one or more roles, e.g. @role_required('admin')."""
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if "user_id" not in session:
                flash("Please log in to continue.", "warning")
                return redirect(url_for("auth.login"))
            if session.get("role") not in allowed_roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def current_user_id():
    return session.get("user_id")


def current_role():
    return session.get("role")
