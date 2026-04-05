"""add dimension column to projects

Revision ID: 003_add_dimension
Revises: 002_add_extended_graphs
Create Date: 2026-04-05
"""

from alembic import op
import sqlalchemy as sa

revision = "003_add_dimension"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("dimension", sa.String(8), nullable=False, server_default="3d"),
    )


def downgrade() -> None:
    op.drop_column("projects", "dimension")
