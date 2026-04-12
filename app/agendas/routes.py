from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import login_required

from ..extensions import db
from ..meetings.forms import AgendaItemForm
from ..models import AgendaCategory, AgendaItem, Meeting, Role, User
from ..permissions import role_required
from . import bp


def _load_meeting(meeting_id: int) -> Meeting:
    return Meeting.query.get_or_404(meeting_id)


def _populate_presenters(form: AgendaItemForm) -> None:
    officers = (
        User.query.filter(User.is_active.is_(True))
        .order_by(User.full_name)
        .all()
    )
    form.presenter_id.choices = [(0, "— none —")] + [
        (u.id, u.full_name) for u in officers
    ]


@bp.route("/", methods=["GET"])
@login_required
def view_agenda(meeting_id: int):
    meeting = _load_meeting(meeting_id)
    form = AgendaItemForm()
    _populate_presenters(form)
    return render_template(
        "agendas/edit.html", meeting=meeting, form=form
    )


@bp.route("/items", methods=["POST"])
@role_required(Role.chair, Role.vice_chair, Role.secretary)
def create_item(meeting_id: int):
    meeting = _load_meeting(meeting_id)
    form = AgendaItemForm()
    _populate_presenters(form)
    if not form.validate_on_submit():
        flash("Please fill in the title.", "danger")
        return redirect(url_for("agendas.view_agenda", meeting_id=meeting_id))

    max_order = max((i.order_index for i in meeting.agenda_items), default=0)
    presenter_id = form.presenter_id.data or None
    if presenter_id == 0:
        presenter_id = None

    item = AgendaItem(
        meeting_id=meeting.id,
        order_index=max_order + 1,
        category=AgendaCategory(form.category.data),
        title=form.title.data.strip(),
        description=(form.description.data or "").strip(),
        presenter_id=presenter_id,
        is_confidential=form.is_confidential.data,
    )
    db.session.add(item)
    db.session.commit()
    flash("Agenda item added.", "success")
    return redirect(url_for("agendas.view_agenda", meeting_id=meeting_id))


@bp.route("/items/<int:item_id>/delete", methods=["POST"])
@role_required(Role.chair, Role.vice_chair, Role.secretary)
def delete_item(meeting_id: int, item_id: int):
    meeting = _load_meeting(meeting_id)
    item = next((i for i in meeting.agenda_items if i.id == item_id), None)
    if item is None:
        abort(404)
    db.session.delete(item)
    db.session.commit()
    flash("Agenda item removed.", "info")
    return redirect(url_for("agendas.view_agenda", meeting_id=meeting_id))


@bp.route("/items/<int:item_id>/move", methods=["POST"])
@role_required(Role.chair, Role.vice_chair, Role.secretary)
def move_item(meeting_id: int, item_id: int):
    meeting = _load_meeting(meeting_id)
    direction = request.form.get("direction", "up")
    items = sorted(meeting.agenda_items, key=lambda i: i.order_index)
    ids = [i.id for i in items]
    if item_id not in ids:
        abort(404)
    idx = ids.index(item_id)
    target = idx - 1 if direction == "up" else idx + 1
    if 0 <= target < len(items):
        items[idx].order_index, items[target].order_index = (
            items[target].order_index,
            items[idx].order_index,
        )
        db.session.commit()
    return redirect(url_for("agendas.view_agenda", meeting_id=meeting_id))
