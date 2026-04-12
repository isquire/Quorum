from flask import Blueprint

bp = Blueprint("attachments", __name__, url_prefix="/files")

from . import routes  # noqa: E402, F401
