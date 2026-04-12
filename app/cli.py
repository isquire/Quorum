"""Flask CLI commands."""
from __future__ import annotations

import click
from flask import Flask

from .extensions import db
from .models import Role, User


def register(app: Flask) -> None:
    @app.cli.command("create-admin")
    @click.option("--email", prompt=True)
    @click.option("--name", prompt="Full name")
    @click.option(
        "--password",
        prompt=True,
        hide_input=True,
        confirmation_prompt=True,
    )
    @click.option("--force", is_flag=True, default=False)
    def create_admin(email: str, name: str, password: str, force: bool):
        """Create the initial admin user."""
        existing_admin = User.query.filter_by(role=Role.admin).first()
        if existing_admin and not force:
            click.echo(
                f"Admin user already exists ({existing_admin.email}). "
                "Use --force to create another."
            )
            return

        if User.query.filter_by(email=email).first():
            click.echo(f"User with email {email} already exists.")
            return

        user = User(
            email=email,
            full_name=name,
            role=Role.admin,
            is_active=True,
            is_voting_member=True,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f"Created admin user: {email}")

    @app.cli.command("init-db")
    def init_db():
        """Create all tables (useful for dev without migrations)."""
        db.create_all()
        click.echo("Database tables created.")
