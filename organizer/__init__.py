from flask import Blueprint

organizer_bp = Blueprint("organizer", __name__, url_prefix="/organizer")

from . import routes  # noqa: E402,F401
