from flask import Blueprint

bp = Blueprint("boards", __name__, url_prefix="/boards")

from . import routes  # noqa: E402, F401
