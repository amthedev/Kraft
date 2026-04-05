"""Add extended IR graphs for massive open world games

Revision ID: 002
Revises: 001
Create Date: 2026-04-05
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("world_graph", JSONB, nullable=True))
    op.add_column("projects", sa.Column("character_graph", JSONB, nullable=True))
    op.add_column("projects", sa.Column("quest_graph", JSONB, nullable=True))
    op.add_column("projects", sa.Column("dialogue_graph", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "dialogue_graph")
    op.drop_column("projects", "quest_graph")
    op.drop_column("projects", "character_graph")
    op.drop_column("projects", "world_graph")
