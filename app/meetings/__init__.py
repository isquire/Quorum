from flask import Blueprint

bp = Blueprint("meetings", __name__, url_prefix="/meetings")

from . import routes  # noqa: E402, F401
