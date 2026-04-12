"""SQLAlchemy models for Quorum."""
from __future__ import annotations

import enum
import math
from datetime import date, datetime, timedelta

from flask_login import UserMixin
from sqlalchemy import CheckConstraint, UniqueConstraint
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db, login_manager
from .utils import now_eastern


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Role(str, enum.Enum):
    admin = "admin"
    chair = "chair"
    vice_chair = "vice_chair"
    secretary = "secretary"
    treasurer = "treasurer"
    member = "member"
    # Bylaws-aligned roles (Phase B)
    pastor = "pastor"
    deacon = "deacon"
    trustee = "trustee"
    assistant_treasurer = "assistant_treasurer"


class BoardRole(str, enum.Enum):
    """Role a user holds on a specific board."""
    pastor = "pastor"
    deacon = "deacon"
    trustee = "trustee"
    secretary = "secretary"
    treasurer = "treasurer"
    assistant_treasurer = "assistant_treasurer"
    member = "member"


class MeetingType(str, enum.Enum):
    regular = "regular"
    special = "special"
    annual = "annual"
    emergency = "emergency"
    # Bylaws-specific types (Phase A)
    annual_business = "annual_business"
    special_business = "special_business"


class MeetingStatus(str, enum.Enum):
    scheduled = "scheduled"
    in_progress = "in_progress"
    adjourned = "adjourned"
    cancelled = "cancelled"


class MeetingStage(str, enum.Enum):
    not_started = "not_started"
    call_to_order = "call_to_order"
    roll_call = "roll_call"
    minutes_approval = "minutes_approval"
    reports = "reports"
    unfinished_business = "unfinished_business"
    new_business = "new_business"
    announcements = "announcements"
    adjourned = "adjourned"
    # Annual-business assembly stages (Phase C — Bylaws Art VII)
    devotional = "devotional"
    minutes_reading = "minutes_reading"
    treasurer_report = "treasurer_report"
    committee_reports = "committee_reports"
    elections = "elections"
    adjournment = "adjournment"


class RsvpStatus(str, enum.Enum):
    yes = "yes"
    no = "no"
    maybe = "maybe"
    no_response = "no_response"


class AgendaCategory(str, enum.Enum):
    call_to_order = "call_to_order"
    roll_call = "roll_call"
    minutes_approval = "minutes_approval"
    report = "report"
    unfinished_business = "unfinished_business"
    new_business = "new_business"
    announcement = "announcement"
    adjournment = "adjournment"


class AgendaItemStatus(str, enum.Enum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    skipped = "skipped"


class MotionType(str, enum.Enum):
    main = "main"
    amendment = "amendment"
    substitute_amendment = "substitute_amendment"
    table = "table"
    postpone = "postpone"
    call_question = "call_question"
    adjourn = "adjourn"
    recess = "recess"
    point_of_order = "point_of_order"
    # Supermajority motion types (Phase C — Bylaws)
    bylaw_amendment = "bylaw_amendment"           # 2/3 — Bylaws Art IX
    property_transfer = "property_transfer"       # 2/3 — Bylaws Art VI §2
    pastor_election = "pastor_election"           # 2/3 — Bylaws Art II §1


class MotionStatus(str, enum.Enum):
    proposed = "proposed"
    seconded = "seconded"
    debating = "debating"
    voting = "voting"
    passed = "passed"
    failed = "failed"
    withdrawn = "withdrawn"
    tabled = "tabled"


class MotionResult(str, enum.Enum):
    passed = "passed"
    failed = "failed"


class MajorityRule(str, enum.Enum):
    simple = "simple"
    two_thirds = "two_thirds"


class VoteMethod(str, enum.Enum):
    voice = "voice"
    roll_call = "roll_call"


class VoteChoice(str, enum.Enum):
    yes = "yes"
    no = "no"
    abstain = "abstain"


class MinutesEntryType(str, enum.Enum):
    stage_change = "stage_change"
    attendance = "attendance"
    agenda_item = "agenda_item"
    motion_made = "motion_made"
    motion_seconded = "motion_seconded"
    motion_amended = "motion_amended"
    motion_voted = "motion_voted"
    motion_withdrawn = "motion_withdrawn"
    report_presented = "report_presented"
    announcement = "announcement"
    chair_note = "chair_note"
    adjournment = "adjournment"


class ReportType(str, enum.Enum):
    treasurer = "treasurer"
    committee = "committee"
    pastor = "pastor"
    other = "other"


class TermStatus(str, enum.Enum):
    """Status of a board officer's service term."""
    active = "active"
    completed = "completed"
    resigned = "resigned"
    removed = "removed"


# Term-limit rules keyed by BoardRole value.  Roles not listed here
# (pastor, secretary, member) have no term limits and are not tracked.
TERM_RULES: dict[str, dict] = {
    "deacon":              {"term_years": 3, "max_consecutive": 1, "cooldown_years": 1},
    "trustee":             {"term_years": 3, "max_consecutive": 1, "cooldown_years": 1},
    "treasurer":           {"term_years": 2, "max_consecutive": 3, "cooldown_years": 1},
    "assistant_treasurer": {"term_years": 2, "max_consecutive": 2, "cooldown_years": 1},
}


# ---------------------------------------------------------------------------
# Mixins
# ---------------------------------------------------------------------------


class TimestampMixin:
    created_at = db.Column(
        db.DateTime, nullable=False, default=now_eastern
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=now_eastern,
        onupdate=now_eastern,
    )


# ---------------------------------------------------------------------------
# Core models
# ---------------------------------------------------------------------------


class User(UserMixin, TimestampMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    full_name = db.Column(db.String(255), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(
        db.Enum(Role, native_enum=False),
        nullable=False,
        default=Role.member,
    )
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    is_voting_member = db.Column(db.Boolean, nullable=False, default=True)
    # Bylaws Art III §5 — tracks active membership for quorum denominator.
    # Secretary toggles this during membership roll revisions.
    is_active_member = db.Column(db.Boolean, nullable=False, default=True)
    # Constitution Art VII §2.5 — no two members of the same immediate
    # family may serve on the same board.  Free-text grouping field.
    family_group = db.Column(db.String(100), nullable=True)
    committees = db.Column(db.String(500), nullable=False, default="")

    # Relationships
    attendances = db.relationship(
        "MeetingAttendance", back_populates="user", cascade="all, delete-orphan"
    )
    board_memberships = db.relationship(
        "BoardMembership", back_populates="user", cascade="all, delete-orphan"
    )
    service_terms = db.relationship(
        "ServiceTerm", back_populates="user", cascade="all, delete-orphan"
    )
    motions_made = db.relationship(
        "Motion", foreign_keys="Motion.maker_id", back_populates="maker"
    )
    motions_seconded = db.relationship(
        "Motion", foreign_keys="Motion.seconder_id", back_populates="seconder"
    )
    votes = db.relationship(
        "Vote", back_populates="user", cascade="all, delete-orphan"
    )
    uploaded_attachments = db.relationship(
        "Attachment", back_populates="uploaded_by"
    )
    submitted_reports = db.relationship(
        "Report",
        foreign_keys="Report.submitted_by_id",
        back_populates="submitted_by",
    )

    # Password helpers
    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    # Role helpers
    def has_role(self, *roles: Role | str) -> bool:
        wanted = {r.value if isinstance(r, Role) else r for r in roles}
        return self.role.value in wanted

    @property
    def is_officer(self) -> bool:
        return self.role in {
            Role.admin,
            Role.chair,
            Role.vice_chair,
            Role.secretary,
            Role.treasurer,
            Role.pastor,
            Role.deacon,
            Role.trustee,
            Role.assistant_treasurer,
        }

    @property
    def committees_list(self) -> list[str]:
        return [c.strip() for c in (self.committees or "").split(",") if c.strip()]

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User {self.email} {self.role.value}>"


@login_manager.user_loader
def _load_user(user_id: str):  # pragma: no cover - also wired in app factory
    return db.session.get(User, int(user_id))


# ---------------------------------------------------------------------------
# Board governance (Phase B — Bylaws alignment)
# ---------------------------------------------------------------------------


class Board(TimestampMixin, db.Model):
    """A governing body: Assembly, Board of Deacons, Board of Admin."""
    __tablename__ = "boards"

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(50), unique=True, nullable=False)
    display_name = db.Column(db.String(100), nullable=False)

    memberships = db.relationship(
        "BoardMembership", back_populates="board", cascade="all, delete-orphan"
    )
    meetings = db.relationship("Meeting", back_populates="board")
    service_terms = db.relationship("ServiceTerm", back_populates="board")

    @property
    def voting_member_count(self) -> int:
        return sum(1 for m in self.memberships if m.is_voting)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Board {self.slug}>"


class BoardMembership(TimestampMixin, db.Model):
    """Many-to-many: User <-> Board with a role on that board."""
    __tablename__ = "board_memberships"
    __table_args__ = (
        UniqueConstraint("board_id", "user_id", name="uq_board_membership"),
    )

    id = db.Column(db.Integer, primary_key=True)
    board_id = db.Column(
        db.Integer, db.ForeignKey("boards.id"), nullable=False
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False
    )
    role_on_board = db.Column(
        db.Enum(BoardRole, native_enum=False),
        nullable=False,
        default=BoardRole.member,
    )
    is_voting = db.Column(db.Boolean, nullable=False, default=True)
    started_at = db.Column(db.DateTime, nullable=True)
    ended_at = db.Column(db.DateTime, nullable=True)

    board = db.relationship("Board", back_populates="memberships")
    user = db.relationship("User", back_populates="board_memberships")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<BoardMembership board={self.board_id} user={self.user_id}>"


def seed_boards() -> list[Board]:
    """Insert the three canonical boards if they don't exist.

    Called during ``flask create-admin`` and migrations.
    """
    slugs = {
        "assembly": "Assembly",
        "board_of_deacons": "Board of Deacons",
        "board_of_administration": "Board of Administration",
    }
    boards = []
    for slug, name in slugs.items():
        existing = Board.query.filter_by(slug=slug).first()
        if existing:
            boards.append(existing)
        else:
            b = Board(slug=slug, display_name=name)
            db.session.add(b)
            boards.append(b)
    db.session.flush()
    return boards


class ServiceTerm(TimestampMixin, db.Model):
    """One term of service on a board in a specific elected role."""
    __tablename__ = "service_terms"
    __table_args__ = (
        UniqueConstraint(
            "board_id", "user_id", "role_on_board", "term_start",
            name="uq_service_term",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    board_id = db.Column(
        db.Integer, db.ForeignKey("boards.id"), nullable=False
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False
    )
    role_on_board = db.Column(
        db.Enum(BoardRole, native_enum=False), nullable=False
    )

    # Link to the annual business meeting where the election occurred.
    elected_at_meeting_id = db.Column(
        db.Integer, db.ForeignKey("meetings.id"), nullable=True
    )

    term_start = db.Column(db.Date, nullable=False)
    term_end = db.Column(db.Date, nullable=False)
    # Set when the term ends early (resignation / removal).
    actual_end = db.Column(db.Date, nullable=True)

    term_number = db.Column(db.Integer, nullable=False, default=1)
    status = db.Column(
        db.Enum(TermStatus, native_enum=False),
        nullable=False,
        default=TermStatus.active,
    )
    notes = db.Column(db.Text, nullable=False, default="")

    # Relationships
    board = db.relationship("Board", back_populates="service_terms")
    user = db.relationship("User", back_populates="service_terms")
    elected_at_meeting = db.relationship("Meeting")

    @property
    def effective_end(self) -> date:
        """The date this term actually ends/ended."""
        return self.actual_end or self.term_end

    @property
    def is_current(self) -> bool:
        """True if the term is active and today falls within it."""
        today = date.today()
        return (
            self.status == TermStatus.active
            and self.term_start <= today <= self.term_end
        )

    @property
    def days_remaining(self) -> int | None:
        """Days until term_end.  None if term is not active."""
        if not self.is_current:
            return None
        return (self.term_end - date.today()).days

    @property
    def months_remaining(self) -> int | None:
        """Approximate months remaining (for UI display)."""
        days = self.days_remaining
        if days is None:
            return None
        return max(0, days // 30)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<ServiceTerm {self.user_id} "
            f"{self.role_on_board.value} #{self.term_number}>"
        )


# ---------------------------------------------------------------------------
# Service-term helper functions
# ---------------------------------------------------------------------------


def compute_term_start(meeting_scheduled_start: datetime) -> date:
    """First day of the month after the meeting's scheduled_start.

    Annual business meeting in January → term starts February 1.
    """
    sd = meeting_scheduled_start
    if sd.month == 12:
        return date(sd.year + 1, 1, 1)
    return date(sd.year, sd.month + 1, 1)


def compute_term_end(term_start: date, role_value: str) -> date:
    """term_start + term_length_years, last day of preceding month.

    E.g. Feb 1 2026 + 2 years → Jan 31 2028.
    """
    rules = TERM_RULES.get(role_value)
    if rules is None:
        raise ValueError(f"No term rules for role '{role_value}'")
    years = rules["term_years"]
    end_year = term_start.year + years
    return date(end_year, term_start.month, 1) - timedelta(days=1)


def count_consecutive_terms(
    user_id: int, board_id: int, role_value: str
) -> int:
    """Count consecutive completed/active terms for this user+board+role,
    working backward from the most recent."""
    terms = (
        ServiceTerm.query
        .filter_by(user_id=user_id, board_id=board_id, role_on_board=BoardRole(role_value))
        .filter(ServiceTerm.status.in_([TermStatus.active, TermStatus.completed]))
        .order_by(ServiceTerm.term_start.desc())
        .all()
    )
    if not terms:
        return 0
    count = 1
    for i in range(len(terms) - 1):
        current = terms[i]
        previous = terms[i + 1]
        gap = (current.term_start - previous.effective_end).days
        if gap <= 60:  # allow small gaps for month boundaries
            count += 1
        else:
            break
    return count


def cooldown_end_date(
    user_id: int, board_id: int, role_value: str
) -> date | None:
    """If the user has served max consecutive terms, return the date
    they become eligible again.  None if no cooldown applies."""
    rules = TERM_RULES.get(role_value)
    if rules is None:
        return None
    consecutive = count_consecutive_terms(user_id, board_id, role_value)
    if consecutive < rules["max_consecutive"]:
        return None
    last_term = (
        ServiceTerm.query
        .filter_by(
            user_id=user_id, board_id=board_id,
            role_on_board=BoardRole(role_value),
        )
        .filter(ServiceTerm.status.in_([TermStatus.active, TermStatus.completed]))
        .order_by(ServiceTerm.term_start.desc())
        .first()
    )
    if last_term is None:
        return None
    cooldown_years = rules["cooldown_years"]
    end = last_term.effective_end
    return date(end.year + cooldown_years, end.month, end.day)


def is_eligible_for_term(
    user_id: int, board_id: int, role_value: str
) -> tuple[bool, str]:
    """Check whether a user is eligible to be elected/re-elected.

    Returns ``(eligible, reason)`` tuple.
    """
    rules = TERM_RULES.get(role_value)
    if rules is None:
        return True, "No term limits for this role"
    cd_end = cooldown_end_date(user_id, board_id, role_value)
    if cd_end and date.today() < cd_end:
        months_left = max(0, (cd_end - date.today()).days // 30)
        return False, f"In cooldown until {cd_end.strftime('%B %Y')} ({months_left} months)"
    return True, "Eligible"


class Meeting(TimestampMixin, db.Model):
    __tablename__ = "meetings"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    # Phase B: every meeting belongs to a board (nullable for migration backfill).
    board_id = db.Column(
        db.Integer, db.ForeignKey("boards.id"), nullable=True
    )
    meeting_type = db.Column(
        db.Enum(MeetingType, native_enum=False),
        nullable=False,
        default=MeetingType.regular,
    )
    scheduled_start = db.Column(db.DateTime, nullable=False)
    scheduled_end = db.Column(db.DateTime, nullable=True)
    location = db.Column(db.String(255), nullable=False, default="")

    status = db.Column(
        db.Enum(MeetingStatus, native_enum=False),
        nullable=False,
        default=MeetingStatus.scheduled,
    )
    current_stage = db.Column(
        db.Enum(MeetingStage, native_enum=False),
        nullable=False,
        default=MeetingStage.not_started,
    )

    current_agenda_item_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "agenda_items.id",
            name="fk_meeting_current_agenda",
            use_alter=True,
        ),
        nullable=True,
    )
    current_motion_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "motions.id",
            name="fk_meeting_current_motion",
            use_alter=True,
        ),
        nullable=True,
    )

    called_to_order_at = db.Column(db.DateTime, nullable=True)
    adjourned_at = db.Column(db.DateTime, nullable=True)

    minutes_approved_at = db.Column(db.DateTime, nullable=True)
    minutes_approved_by_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=True
    )

    created_by_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False
    )
    # Bylaws Art I §2 — acting chair when the Pastor is absent.
    acting_chair_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=True
    )

    # Archive support — admins can archive meetings to hide from normal views.
    is_archived = db.Column(db.Boolean, nullable=False, default=False)
    archived_at = db.Column(db.DateTime, nullable=True)
    archived_by_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=True
    )

    # Relationships
    board = db.relationship("Board", back_populates="meetings")
    created_by = db.relationship("User", foreign_keys=[created_by_id])
    acting_chair = db.relationship("User", foreign_keys=[acting_chair_id])
    archived_by = db.relationship("User", foreign_keys=[archived_by_id])
    minutes_approved_by = db.relationship(
        "User", foreign_keys=[minutes_approved_by_id]
    )
    attendances = db.relationship(
        "MeetingAttendance",
        back_populates="meeting",
        cascade="all, delete-orphan",
    )
    agenda_items = db.relationship(
        "AgendaItem",
        back_populates="meeting",
        cascade="all, delete-orphan",
        foreign_keys="AgendaItem.meeting_id",
        order_by="AgendaItem.order_index",
    )
    motions = db.relationship(
        "Motion",
        back_populates="meeting",
        cascade="all, delete-orphan",
        foreign_keys="Motion.meeting_id",
    )
    minutes_entries = db.relationship(
        "MinutesEntry",
        back_populates="meeting",
        cascade="all, delete-orphan",
        order_by="MinutesEntry.sequence",
    )
    reports = db.relationship("Report", back_populates="meeting")
    attachments = db.relationship(
        "Attachment",
        back_populates="meeting",
        foreign_keys="Attachment.meeting_id",
    )

    current_agenda_item = db.relationship(
        "AgendaItem", foreign_keys=[current_agenda_item_id], post_update=True
    )
    current_motion = db.relationship(
        "Motion", foreign_keys=[current_motion_id], post_update=True
    )

    # Derived properties
    @property
    def present_count(self) -> int:
        return sum(1 for a in self.attendances if a.is_present)

    @property
    def voting_member_count(self) -> int:
        return sum(
            1
            for a in self.attendances
            if a.user is not None and a.user.is_voting_member
        )

    @property
    def is_assembly_meeting(self) -> bool:
        """True for congregational business meetings (annual or special)."""
        return self.meeting_type in {
            MeetingType.annual_business,
            MeetingType.special_business,
        }

    @property
    def board_voting_member_count(self) -> int:
        """Count voting members via board membership if board is set.

        Falls back to the attendance-based count when the board has no
        memberships yet (backwards compat during Phase B migration).
        """
        if self.board is not None:
            count = self.board.voting_member_count
            if count > 0:
                return count
        return self.voting_member_count

    @property
    def quorum_threshold(self) -> int:
        if self.is_assembly_meeting:
            # Constitution Art VIII §4: one-third of active members.
            active = User.query.filter_by(is_active_member=True).count()
            return math.ceil(active / 3) if active > 0 else 1
        # Bylaws Art I §§2-3: majority of board members.
        voters = self.board_voting_member_count
        return (voters // 2) + 1

    @property
    def all_members_notified(self) -> bool:
        """True when every attendance row has a non-null notified_at.

        Bylaws Art I §§2-3: board meeting quorum requires all members
        to have been notified.
        """
        return all(a.notified_at is not None for a in self.attendances)

    @property
    def unnotified_count(self) -> int:
        """Number of attendance rows without a notified_at timestamp."""
        return sum(1 for a in self.attendances if a.notified_at is None)

    @property
    def has_quorum(self) -> bool:
        if self.is_assembly_meeting:
            # For assembly meetings, count all present attendees.
            return self.present_count >= self.quorum_threshold
        # Bylaws Art I §§2-3: board meeting quorum requires all
        # members to have been notified.
        if not self.all_members_notified:
            return False
        # For board meetings, count present *voting* members.
        present_voting = sum(
            1
            for a in self.attendances
            if a.is_present and a.user is not None and a.user.is_voting_member
        )
        return present_voting >= self.quorum_threshold

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Meeting {self.id} {self.title}>"


class MeetingAttendance(TimestampMixin, db.Model):
    __tablename__ = "meeting_attendances"
    __table_args__ = (
        UniqueConstraint("meeting_id", "user_id", name="uq_attendance_meeting_user"),
    )

    id = db.Column(db.Integer, primary_key=True)
    meeting_id = db.Column(
        db.Integer, db.ForeignKey("meetings.id"), nullable=False
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False
    )
    rsvp_status = db.Column(
        db.Enum(RsvpStatus, native_enum=False),
        nullable=False,
        default=RsvpStatus.no_response,
    )
    is_present = db.Column(db.Boolean, nullable=False, default=False)
    arrived_at = db.Column(db.DateTime, nullable=True)
    departed_at = db.Column(db.DateTime, nullable=True)
    # Bylaws Art I §§2-3 — board meeting quorum requires all members notified.
    notified_at = db.Column(db.DateTime, nullable=True)

    meeting = db.relationship("Meeting", back_populates="attendances")
    user = db.relationship("User", back_populates="attendances")


class AgendaItem(TimestampMixin, db.Model):
    __tablename__ = "agenda_items"

    id = db.Column(db.Integer, primary_key=True)
    meeting_id = db.Column(
        db.Integer, db.ForeignKey("meetings.id"), nullable=False
    )
    order_index = db.Column(db.Integer, nullable=False, default=0)
    category = db.Column(
        db.Enum(AgendaCategory, native_enum=False),
        nullable=False,
        default=AgendaCategory.new_business,
    )
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=False, default="")
    is_confidential = db.Column(db.Boolean, nullable=False, default=False)
    presenter_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    status = db.Column(
        db.Enum(AgendaItemStatus, native_enum=False),
        nullable=False,
        default=AgendaItemStatus.pending,
    )

    meeting = db.relationship(
        "Meeting",
        back_populates="agenda_items",
        foreign_keys=[meeting_id],
    )
    presenter = db.relationship("User", foreign_keys=[presenter_id])
    attachments = db.relationship(
        "Attachment",
        back_populates="agenda_item",
        foreign_keys="Attachment.agenda_item_id",
    )


class Motion(TimestampMixin, db.Model):
    __tablename__ = "motions"

    id = db.Column(db.Integer, primary_key=True)
    meeting_id = db.Column(
        db.Integer, db.ForeignKey("meetings.id"), nullable=False
    )
    agenda_item_id = db.Column(
        db.Integer, db.ForeignKey("agenda_items.id"), nullable=True
    )
    parent_motion_id = db.Column(
        db.Integer, db.ForeignKey("motions.id"), nullable=True
    )

    motion_type = db.Column(
        db.Enum(MotionType, native_enum=False),
        nullable=False,
        default=MotionType.main,
    )
    # Constitution Art VIII §6 — deacons-only vote at Board of Admin meetings.
    deacons_only = db.Column(db.Boolean, nullable=False, default=False)
    text = db.Column(db.Text, nullable=False)
    maker_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    seconder_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    status = db.Column(
        db.Enum(MotionStatus, native_enum=False),
        nullable=False,
        default=MotionStatus.proposed,
    )
    yes_count = db.Column(db.Integer, nullable=False, default=0)
    no_count = db.Column(db.Integer, nullable=False, default=0)
    abstain_count = db.Column(db.Integer, nullable=False, default=0)

    result = db.Column(
        db.Enum(MotionResult, native_enum=False), nullable=True
    )
    requires_majority = db.Column(
        db.Enum(MajorityRule, native_enum=False),
        nullable=False,
        default=MajorityRule.simple,
    )
    vote_method = db.Column(
        db.Enum(VoteMethod, native_enum=False),
        nullable=False,
        default=VoteMethod.voice,
    )
    voted_at = db.Column(db.DateTime, nullable=True)

    meeting = db.relationship(
        "Meeting", back_populates="motions", foreign_keys=[meeting_id]
    )
    agenda_item = db.relationship("AgendaItem", foreign_keys=[agenda_item_id])
    maker = db.relationship(
        "User", foreign_keys=[maker_id], back_populates="motions_made"
    )
    seconder = db.relationship(
        "User", foreign_keys=[seconder_id], back_populates="motions_seconded"
    )
    amendments = db.relationship(
        "Motion",
        backref=db.backref("parent_motion", remote_side=[id]),
        foreign_keys=[parent_motion_id],
    )
    votes = db.relationship(
        "Vote", back_populates="motion", cascade="all, delete-orphan"
    )

    def recount(self) -> None:
        """Recompute vote tallies from individual Vote rows.

        For voice / show-of-hands votes the tallies are entered manually
        by the chair, so this method is a no-op.

        For deacons-only motions (Constitution Art VIII §6), only votes
        from users with pastor/deacon board membership are counted.
        """
        if self.vote_method == VoteMethod.voice:
            return
        yes = no = abstain = 0
        for v in self.votes:
            # Filter out ineligible votes on deacons-only motions.
            if self.deacons_only and self.meeting and self.meeting.board_id:
                membership = BoardMembership.query.filter_by(
                    user_id=v.user_id, board_id=self.meeting.board_id
                ).first()
                if not membership or membership.role_on_board not in (
                    BoardRole.pastor, BoardRole.deacon
                ):
                    continue
            if v.choice == VoteChoice.yes:
                yes += 1
            elif v.choice == VoteChoice.no:
                no += 1
            else:
                abstain += 1
        self.yes_count = yes
        self.no_count = no
        self.abstain_count = abstain

    def compute_result(self) -> MotionResult:
        """Compute pass/fail using the motion's majority rule.

        Abstentions do not count toward the yes/no total.
        """
        total = self.yes_count + self.no_count
        if total == 0:
            return MotionResult.failed
        if self.requires_majority == MajorityRule.two_thirds:
            return (
                MotionResult.passed
                if self.yes_count * 3 >= total * 2 and self.yes_count > 0
                else MotionResult.failed
            )
        return (
            MotionResult.passed
            if self.yes_count > self.no_count
            else MotionResult.failed
        )


class Vote(TimestampMixin, db.Model):
    __tablename__ = "votes"
    __table_args__ = (
        UniqueConstraint("motion_id", "user_id", name="uq_vote_motion_user"),
    )

    id = db.Column(db.Integer, primary_key=True)
    motion_id = db.Column(
        db.Integer, db.ForeignKey("motions.id"), nullable=False
    )
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    choice = db.Column(
        db.Enum(VoteChoice, native_enum=False), nullable=False
    )
    cast_at = db.Column(db.DateTime, nullable=False, default=now_eastern)

    motion = db.relationship("Motion", back_populates="votes")
    user = db.relationship("User", back_populates="votes")


class MinutesEntry(TimestampMixin, db.Model):
    __tablename__ = "minutes_entries"

    id = db.Column(db.Integer, primary_key=True)
    meeting_id = db.Column(
        db.Integer, db.ForeignKey("meetings.id"), nullable=False
    )
    sequence = db.Column(db.Integer, nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=now_eastern)
    entry_type = db.Column(
        db.Enum(MinutesEntryType, native_enum=False), nullable=False
    )
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    related_motion_id = db.Column(
        db.Integer, db.ForeignKey("motions.id"), nullable=True
    )
    related_agenda_item_id = db.Column(
        db.Integer, db.ForeignKey("agenda_items.id"), nullable=True
    )
    text = db.Column(db.Text, nullable=False)
    is_confidential = db.Column(db.Boolean, nullable=False, default=False)
    is_edited = db.Column(db.Boolean, nullable=False, default=False)

    meeting = db.relationship("Meeting", back_populates="minutes_entries")
    actor = db.relationship("User", foreign_keys=[actor_id])
    related_motion = db.relationship("Motion", foreign_keys=[related_motion_id])
    related_agenda_item = db.relationship(
        "AgendaItem", foreign_keys=[related_agenda_item_id]
    )


class Report(TimestampMixin, db.Model):
    __tablename__ = "reports"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    report_type = db.Column(
        db.Enum(ReportType, native_enum=False),
        nullable=False,
        default=ReportType.committee,
    )
    committee = db.Column(db.String(100), nullable=False, default="")
    content = db.Column(db.Text, nullable=False, default="")
    submitted_by_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False
    )
    meeting_id = db.Column(
        db.Integer, db.ForeignKey("meetings.id"), nullable=True
    )
    period_start = db.Column(db.Date, nullable=True)
    period_end = db.Column(db.Date, nullable=True)
    submitted_at = db.Column(
        db.DateTime, nullable=False, default=now_eastern
    )
    approved_at = db.Column(db.DateTime, nullable=True)
    approved_by_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=True
    )

    # Archive support — admins can archive reports to hide from normal views.
    is_archived = db.Column(db.Boolean, nullable=False, default=False)
    archived_at = db.Column(db.DateTime, nullable=True)
    archived_by_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=True
    )

    submitted_by = db.relationship(
        "User", foreign_keys=[submitted_by_id], back_populates="submitted_reports"
    )
    approved_by = db.relationship("User", foreign_keys=[approved_by_id])
    archived_by = db.relationship("User", foreign_keys=[archived_by_id])
    meeting = db.relationship("Meeting", back_populates="reports")
    attachments = db.relationship(
        "Attachment",
        back_populates="report",
        foreign_keys="Attachment.report_id",
    )


class AdminAction(db.Model):
    """Audit log of every admin action in the system."""
    __tablename__ = "admin_actions"

    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False
    )
    action = db.Column(db.String(100), nullable=False)
    target_type = db.Column(db.String(50), nullable=False)
    target_id = db.Column(db.Integer, nullable=True)
    detail = db.Column(db.Text, nullable=False, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=now_eastern)

    admin = db.relationship("User", foreign_keys=[admin_id])

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AdminAction {self.action} by user {self.admin_id}>"


class Attachment(TimestampMixin, db.Model):
    __tablename__ = "attachments"
    __table_args__ = (
        CheckConstraint(
            "(CASE WHEN meeting_id IS NULL THEN 0 ELSE 1 END"
            " + CASE WHEN agenda_item_id IS NULL THEN 0 ELSE 1 END"
            " + CASE WHEN report_id IS NULL THEN 0 ELSE 1 END) = 1",
            name="ck_attachment_single_parent",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False, unique=True)
    original_filename = db.Column(db.String(255), nullable=False)
    mime_type = db.Column(db.String(100), nullable=False, default="")
    size_bytes = db.Column(db.Integer, nullable=False, default=0)
    sha256 = db.Column(db.String(64), nullable=True)

    uploaded_by_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False
    )
    uploaded_at = db.Column(db.DateTime, nullable=False, default=now_eastern)

    meeting_id = db.Column(
        db.Integer, db.ForeignKey("meetings.id"), nullable=True
    )
    agenda_item_id = db.Column(
        db.Integer, db.ForeignKey("agenda_items.id"), nullable=True
    )
    report_id = db.Column(
        db.Integer, db.ForeignKey("reports.id"), nullable=True
    )

    uploaded_by = db.relationship(
        "User", back_populates="uploaded_attachments"
    )
    meeting = db.relationship(
        "Meeting", back_populates="attachments", foreign_keys=[meeting_id]
    )
    agenda_item = db.relationship(
        "AgendaItem", back_populates="attachments", foreign_keys=[agenda_item_id]
    )
    report = db.relationship(
        "Report", back_populates="attachments", foreign_keys=[report_id]
    )


# ---------------------------------------------------------------------------
# Meeting Templates
# ---------------------------------------------------------------------------


class MeetingTemplate(TimestampMixin, db.Model):
    """A reusable agenda template for creating meetings."""
    __tablename__ = "meeting_templates"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False, default="")
    meeting_type = db.Column(
        db.Enum(MeetingType, native_enum=False), nullable=True
    )
    created_by_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False
    )

    created_by = db.relationship("User")
    items = db.relationship(
        "MeetingTemplateItem",
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="MeetingTemplateItem.order_index",
    )


class MeetingTemplateItem(db.Model):
    """One agenda item within a meeting template."""
    __tablename__ = "meeting_template_items"

    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(
        db.Integer, db.ForeignKey("meeting_templates.id"), nullable=False
    )
    order_index = db.Column(db.Integer, nullable=False, default=0)
    category = db.Column(
        db.Enum(AgendaCategory, native_enum=False), nullable=False
    )
    title = db.Column(db.String(300), nullable=False)
    description = db.Column(db.Text, nullable=False, default="")
    is_confidential = db.Column(db.Boolean, nullable=False, default=False)

    template = db.relationship("MeetingTemplate", back_populates="items")


# ---------------------------------------------------------------------------
# Document Repository
# ---------------------------------------------------------------------------


class DocumentCategory(str, enum.Enum):
    bylaws = "bylaws"
    constitution = "constitution"
    policy = "policy"
    standing_rules = "standing_rules"
    form = "form"
    other = "other"


class Document(TimestampMixin, db.Model):
    """A governance document (bylaws, constitution, policy, etc.)."""
    __tablename__ = "documents"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(300), nullable=False)
    category = db.Column(
        db.Enum(DocumentCategory, native_enum=False), nullable=False
    )
    content = db.Column(db.Text, nullable=False, default="")
    current_version = db.Column(db.Integer, nullable=False, default=1)
    updated_by_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False
    )

    updated_by = db.relationship("User")
    versions = db.relationship(
        "DocumentVersion",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentVersion.version.desc()",
    )


class DocumentVersion(TimestampMixin, db.Model):
    """A historical version of a document."""
    __tablename__ = "document_versions"

    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(
        db.Integer, db.ForeignKey("documents.id"), nullable=False
    )
    version = db.Column(db.Integer, nullable=False)
    content = db.Column(db.Text, nullable=False, default="")
    change_summary = db.Column(db.String(500), nullable=False, default="")
    edited_by_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False
    )

    document = db.relationship("Document", back_populates="versions")
    edited_by = db.relationship("User")
