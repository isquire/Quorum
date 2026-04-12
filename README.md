# Quorum

A collaborative web application for the **Connection Church Board of Administration** to schedule meetings, build agendas, run meetings live under **Robert's Rules of Order**, record minutes automatically, and archive minutes and reports.

## Features

- **Live meeting cockpit** — the chair drives meetings through the standard RRO order of business (call to order → roll call → minutes approval → reports → unfinished business → new business → announcements → adjournment)
- **Full motion lifecycle** — make, second, amend, debate, vote, close; per-member vote tracking with yes/no/abstain tallies and pass/fail results (simple majority or two-thirds)
- **Automatic minute-logging** — every parliamentary action is recorded as a timestamped minutes entry, reviewable and exportable as plain text
- **Quorum monitoring** — live badge showing present voting members vs. the quorum threshold; turns green when quorum is met
- **Agenda management** — add, reorder, and assign presenters to agenda items
- **Reports archive** — treasurer and committee reports with markdown content, linked to meetings, chair-approved
- **File attachments** — attach PDFs and office documents to meetings, agenda items, or reports; stored on a Docker-managed volume
- **Role-based access** — admin, chair, vice-chair, secretary, treasurer, member
- **Local-first** — Flask + SQLite, no external services required

## Tech stack

- Python 3.12, Flask 3
- SQLAlchemy + SQLite (via Flask-SQLAlchemy)
- Flask-Login, Flask-WTF, Flask-Migrate
- Bootstrap 5 + HTMX (served via CDN in the base template)
- Gunicorn in production
- Docker Compose

## Running with Docker Compose (recommended)

1. Copy the environment template and fill in a real secret key:
   ```sh
   cp .env.example .env
   python -c "import secrets; print(secrets.token_hex(32))"  # paste into SECRET_KEY
   ```
2. Build and start:
   ```sh
   docker compose build
   docker compose up -d
   ```
   The entrypoint runs `flask db upgrade` automatically before starting gunicorn.
3. Create the initial admin user:
   ```sh
   docker compose exec web flask create-admin
   ```
4. Visit `http://localhost:8000/auth/login` and sign in.

Data lives on two named Docker volumes: `quorum_db` (SQLite) and `quorum_uploads` (attachments).

## Running locally (for development)

```sh
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export FLASK_APP=wsgi.py
export FLASK_CONFIG=dev
export SECRET_KEY=dev

flask db upgrade
flask create-admin
flask run --host 0.0.0.0 --port 8000
```

## Running the tests

```sh
pytest
```

The test suite covers auth, meeting creation, the motion lifecycle (propose → second → vote → result), quorum arithmetic, and file uploads.

## Project layout

```
app/
├── __init__.py          # Flask app factory
├── extensions.py        # db, login_manager, migrate, csrf singletons
├── models.py            # all SQLAlchemy models
├── rro.py               # Robert's Rules state machine
├── minutes_logger.py    # centralized minutes-entry helpers
├── permissions.py       # role-required decorators
├── cli.py               # flask create-admin, flask init-db
├── auth/                # login / logout / change password
├── main/                # dashboard
├── users/               # admin-only user CRUD
├── meetings/            # meeting CRUD + live_routes (the chair's cockpit)
├── agendas/             # agenda items
├── minutes/             # archive, approval, text export
├── reports/             # treasurer / committee reports
├── attachments/         # file upload / download
├── templates/           # Jinja2 templates
└── static/              # CSS / JS

config.py                # DevConfig / ProdConfig / TestConfig
wsgi.py                  # gunicorn entry point
Dockerfile
docker-compose.yml
docker-entrypoint.sh     # runs migrations, then gunicorn
migrations/              # Alembic
tests/                   # pytest suite
```

## How a meeting runs

1. A chair creates a meeting and builds an agenda with items categorized under the RRO order of business.
2. At meeting time, the chair clicks **Start meeting** — this sets the meeting to `in_progress` at the `call_to_order` stage and appends a "called to order" minutes entry.
3. The chair/secretary marks members present. The quorum badge turns green once the threshold is met.
4. The chair clicks **Advance stage** to move through the order of business. Each transition is logged.
5. During reports / unfinished business / new business, any voting member can **Make a motion**. Another voting member (not the maker) can **Second** it. The chair then clicks **Open vote**.
6. Each voting member casts Yes / No / Abstain. The chair clicks **Close vote** — the result is computed using simple or two-thirds majority and logged to the minutes with the full tally.
7. Amendments follow the same flow but are nested under their parent motion; the innermost amendment is voted first.
8. The chair clicks **Adjourn** to end the meeting. The minutes timeline is now immutable (secretary can still edit entries before chair approval).
9. At the next meeting, the chair approves the prior minutes — the `minutes_approval` stage has a button for this.

## License

Private project for Connection Church Board of Administration.
