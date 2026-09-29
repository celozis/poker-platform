"""Club owners: an admin's role, admin or owner.

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-29

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Everyone logging in to the admin panel until now is an admin.
    op.add_column(
        "admins", sa.Column("role", sa.String(10), nullable=False, server_default="admin")
    )
    op.alter_column("admins", "role", server_default=None)


def downgrade() -> None:
    op.drop_column("admins", "role")
