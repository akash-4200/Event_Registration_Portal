"""
app.py
------
Application factory + entry point.

Local run:
    python app.py

Production (Render, etc.) run via gunicorn -- see Procfile:
    gunicorn app:app

On first run this creates the database from schema.sql automatically.
Run seed.py separately to populate demo data (an admin account, a couple
of organizers/students, categories, and sample events) so the app isn't
empty on first login.

Uploaded files (posters, QR codes, certificates) are served through a
dedicated /uploads/<path> route rather than Flask's static file handler,
so their storage location can live outside the app's own folder --
required on Render, where only a mounted persistent disk survives
restarts/redeploys. See config.py (DATA_DIR) and DEPLOYMENT.md.
"""

import os
from datetime import datetime

from flask import Flask, render_template, session, g, send_from_directory

from config import Config
from db import init_db, query_one


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    init_db(app)

    # Ensure upload subfolders exist -- required on a fresh persistent disk,
    # which starts empty (db.py already does the equivalent for the database
    # directory, but the upload folders need the same treatment here).
    for folder in (app.config["POSTER_FOLDER"], app.config["QRCODE_FOLDER"], app.config["CERTIFICATE_FOLDER"]):
        os.makedirs(folder, exist_ok=True)

    # --- Register blueprints ---
    from auth import auth_bp
    from student import student_bp
    from organizer import organizer_bp
    from admin import admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(student_bp)
    app.register_blueprint(organizer_bp)
    app.register_blueprint(admin_bp)

    # --- Landing page ---
    @app.route("/")
    def index():
        if "user_id" in session:
            role = session.get("role")
            if role == "admin":
                return render_template("index.html", logged_in=True)
        return render_template("index.html", logged_in="user_id" in session)

    # --- Static/help pages ---
    @app.route("/faq")
    def faq():
        return render_template("shared/faq.html")

    @app.route("/help")
    def help_page():
        return render_template("shared/help.html")

    # --- Serve uploaded files (posters, QR codes, certificates) from
    #     whatever directory config.UPLOAD_FOLDER points to, independent
    #     of Flask's static/ folder ---
    @app.route("/uploads/<path:filename>")
    def serve_upload(filename):
        return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

    # --- Make the logged-in user's unread notification count available
    #     to every template (used for the navbar bell icon) ---
    @app.before_request
    def load_notification_count():
        g.unread_notifications = 0
        if "user_id" in session:
            row = query_one(
                "SELECT COUNT(*) AS c FROM notifications WHERE user_id = ? AND is_read = 0",
                (session["user_id"],),
            )
            g.unread_notifications = row["c"] if row else 0

    @app.context_processor
    def inject_globals():
        return {
            "current_year": datetime.now().year,
            "unread_notifications": getattr(g, "unread_notifications", 0),
        }

    # --- Error handlers ---
    @app.errorhandler(403)
    def forbidden(e):
        return render_template("shared/403.html"), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template("shared/404.html"), 404

    return app


app = create_app()

if __name__ == "__main__":
    # Local development only -- production uses gunicorn (see Procfile),
    # which ignores this block entirely.
    port = int(os.environ.get("PORT", 5000))
    debug_mode = os.environ.get("FLASK_DEBUG", "true").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug_mode)
