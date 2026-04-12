# CLAUDE.md

Project-specific instructions for Claude Code working on the Quorum app.

## Rules

- **Update the user guide after every change.** Whenever a feature is added, modified, or removed, update `app/templates/main/guide.html` to reflect the change. The guide is the primary documentation for church officers using the app. If a new section is needed, add it and update the table of contents sidebar. If an existing section is affected, revise it. Never ship a feature without a corresponding guide update.

- **Tell the user whether a migration is needed.** After every change, clearly state whether the user needs to run a database migration on their deployment. If a new migration file was created (in `migrations/versions/`), tell the user to run `docker compose exec web flask db upgrade`. If only code/templates changed with no schema changes, explicitly say "No migration needed." Never leave this ambiguous.

## Project overview

Quorum is a Flask web app for running church board meetings under Robert's Rules of Order, built for Connection Church (Tri-City Assembly of God). It tracks meetings, agendas, motions, votes, minutes, reports, and board service terms.

## Stack

- Python 3.12, Flask, SQLAlchemy + SQLite, Flask-Login, Flask-WTF, Flask-Migrate, Bootstrap 5, HTMX
- Tests: pytest + pytest-flask, in-memory SQLite (`TestConfig`)
- Deploy: Docker Compose with Gunicorn

## Key directories

- `app/` — Flask app with blueprints: `auth`, `main`, `users`, `meetings`, `agendas`, `minutes`, `reports`, `attachments`, `boards`
- `app/meetings/live_routes.py` — live meeting cockpit (motions, voting, stages)
- `app/models.py` — all SQLAlchemy models, enums, and service-term helpers
- `app/rro.py` — Robert's Rules state machine (stage sequences, allowed motions)
- `app/minutes_logger.py` — auto-generates minutes entries for every parliamentary action
- `app/templates/main/guide.html` — user guide (must be kept in sync with features)
- `migrations/versions/` — Alembic migrations
- `tests/` — pytest test suite

## Testing

Run `python -m pytest tests/ -x -q` before committing. All tests must pass.

## Governance model

Three bodies with different quorum rules:
- **Assembly** (congregational): 1/3 of active members (Constitution Art VIII §4)
- **Board of Deacons**: majority, all notified (Bylaws Art I §2)
- **Board of Administration**: majority, all notified (Bylaws Art I §3)

Term-tracked positions: Deacon (3yr/max 1), Trustee (3yr/max 1), Treasurer (2yr/max 3), Asst Treasurer (2yr/max 2). All have 1-year cooldown after max consecutive terms.
