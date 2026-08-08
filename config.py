"""
config.py
---------
Central configuration. In a real deployment, SECRET_KEY and any email/SMS
credentials would come from environment variables, never hardcoded --
this file reads from os.environ with safe local-dev fallbacks.

DATA_DIR controls where the database and uploaded files live. Locally it
defaults to this project's own folder. On Render, set the DATA_DIR
environment variable to the mount path of a persistent disk (e.g.
/var/data) -- otherwise every deploy/restart wipes the database and
uploaded posters/QR codes/certificates, since Render's regular filesystem
is ephemeral. See DEPLOYMENT.md.
"""

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("DATA_DIR", BASE_DIR)

# Render (and some other platforms) set this automatically -- used below
# to only mark cookies "secure" (HTTPS-only) once actually deployed there,
# so local http:// development still works.
IS_RENDER = os.environ.get("RENDER", "").lower() == "true"


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-this-in-production")
    DATABASE_PATH = os.path.join(DATA_DIR, "instance", "event_portal.db")

    UPLOAD_FOLDER = os.path.join(DATA_DIR, "uploads")
    POSTER_FOLDER = os.path.join(UPLOAD_FOLDER, "posters")
    QRCODE_FOLDER = os.path.join(UPLOAD_FOLDER, "qrcodes")
    CERTIFICATE_FOLDER = os.path.join(UPLOAD_FOLDER, "certificates")

    ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5 MB upload limit

    # How long a password-reset token stays valid
    RESET_TOKEN_EXPIRY_MINUTES = 30

    # Session cookie hardening
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = IS_RENDER  # only require HTTPS once actually deployed
