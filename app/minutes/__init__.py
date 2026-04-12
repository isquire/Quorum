from flask import Blueprint

bp = Blueprint("minutes", __name__, url_prefix="/minutes")

from . import routes  # noqa: E402, F401
