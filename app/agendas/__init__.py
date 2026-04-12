from flask import Blueprint

bp = Blueprint("agendas", __name__, url_prefix="/meetings/<int:meeting_id>/agenda")

from . import routes  # noqa: E402, F401
