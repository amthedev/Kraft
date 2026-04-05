"""Initial schema — all tables

Revision ID: 001
Revises:
Create Date: 2026-04-04
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Enums com create_type=False — os tipos são criados manualmente via DO blocks
# para serem idempotentes; o SQLAlchemy não deve criá-los de novo.
_userplan = PgEnum("free", "starter", "pro", "studio", name="userplan", create_type=False)
_projectstatus = PgEnum("draft", "generating", "ready", "building", "built", "error", name="projectstatus", create_type=False)
_messagerole = PgEnum("user", "assistant", "system", name="messagerole", create_type=False)
_buildstatus = PgEnum("queued", "running", "success", "failed", name="buildstatus", create_type=False)
_assettype = PgEnum("sprite", "tileset", "model", "ui", "sfx", "music", "shader", "script", "scene", name="assettype", create_type=False)
_itemstatus = PgEnum("draft", "published", "suspended", name="itemstatus", create_type=False)
_licensetype = PgEnum("personal", "commercial", "open_source", name="licensetype", create_type=False)


def upgrade() -> None:
    conn = op.get_bind()

    # ── Enums (idempotentes) ────────────────────────────────────────────────────
    for stmt in [
        "DO $$ BEGIN CREATE TYPE userplan AS ENUM ('free', 'starter', 'pro', 'studio'); EXCEPTION WHEN duplicate_object THEN NULL; END $$",
        "DO $$ BEGIN CREATE TYPE projectstatus AS ENUM ('draft', 'generating', 'ready', 'building', 'built', 'error'); EXCEPTION WHEN duplicate_object THEN NULL; END $$",
        "DO $$ BEGIN CREATE TYPE messagerole AS ENUM ('user', 'assistant', 'system'); EXCEPTION WHEN duplicate_object THEN NULL; END $$",
        "DO $$ BEGIN CREATE TYPE buildstatus AS ENUM ('queued', 'running', 'success', 'failed'); EXCEPTION WHEN duplicate_object THEN NULL; END $$",
        "DO $$ BEGIN CREATE TYPE assettype AS ENUM ('sprite', 'tileset', 'model', 'ui', 'sfx', 'music', 'shader', 'script', 'scene'); EXCEPTION WHEN duplicate_object THEN NULL; END $$",
        "DO $$ BEGIN CREATE TYPE itemstatus AS ENUM ('draft', 'published', 'suspended'); EXCEPTION WHEN duplicate_object THEN NULL; END $$",
        "DO $$ BEGIN CREATE TYPE licensetype AS ENUM ('personal', 'commercial', 'open_source'); EXCEPTION WHEN duplicate_object THEN NULL; END $$",
    ]:
        conn.execute(sa.text(stmt))

    # ── users ──────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("username", sa.String(64), nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("plan", _userplan, nullable=False, server_default="free"),
        sa.Column("credits", sa.Integer, nullable=False, server_default="100"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_username", "users", ["username"])

    # ── projects ───────────────────────────────────────────────────────────────
    op.create_table(
        "projects",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("genre", sa.String(64)),
        sa.Column("status", _projectstatus, nullable=False, server_default="draft"),
        sa.Column("gameplay_graph", JSONB),
        sa.Column("scene_graph", JSONB),
        sa.Column("art_bible", JSONB),
        sa.Column("narrative_graph", JSONB),
        sa.Column("economy_graph", JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index("ix_projects_user_id", "projects", ["user_id"])

    # ── project_messages ───────────────────────────────────────────────────────
    op.create_table(
        "project_messages",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", _messagerole, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("action_triggered", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_project_messages_project_id", "project_messages", ["project_id"])

    # ── project_builds ─────────────────────────────────────────────────────────
    op.create_table(
        "project_builds",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("status", _buildstatus, nullable=False, server_default="queued"),
        sa.Column("web_url", sa.String(512)),
        sa.Column("zip_url", sa.String(512)),
        sa.Column("logs", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_project_builds_project_id", "project_builds", ["project_id"])

    # ── assets ─────────────────────────────────────────────────────────────────
    op.create_table(
        "assets",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", _assettype, nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("url", sa.String(512)),
        sa.Column("meta", JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_assets_project_id", "assets", ["project_id"])

    # ── marketplace_items ──────────────────────────────────────────────────────
    op.create_table(
        "marketplace_items",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("seller_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(128), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("price", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("license", _licensetype, nullable=False, server_default="personal"),
        sa.Column("status", _itemstatus, nullable=False, server_default="draft"),
        sa.Column("downloads", sa.Integer, nullable=False, server_default="0"),
        sa.Column("rating", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("cover_url", sa.String(512)),
        sa.Column("demo_url", sa.String(512)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_marketplace_items_seller_id", "marketplace_items", ["seller_id"])

    # ── marketplace_sales ──────────────────────────────────────────────────────
    op.create_table(
        "marketplace_sales",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("item_id", sa.Integer, sa.ForeignKey("marketplace_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("buyer_id", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("amount", sa.Float, nullable=False),
        sa.Column("commission", sa.Float, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_marketplace_sales_item_id", "marketplace_sales", ["item_id"])


def downgrade() -> None:
    op.drop_table("marketplace_sales")
    op.drop_table("marketplace_items")
    op.drop_table("assets")
    op.drop_table("project_builds")
    op.drop_table("project_messages")
    op.drop_table("projects")
    op.drop_table("users")

    conn = op.get_bind()
    for typ in ("licensetype", "itemstatus", "assettype", "buildstatus", "messagerole", "projectstatus", "userplan"):
        conn.execute(sa.text(f"DROP TYPE IF EXISTS {typ}"))
