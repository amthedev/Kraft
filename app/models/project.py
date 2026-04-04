import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ProjectStatus(str, enum.Enum):
    draft = "draft"
    generating = "generating"
    ready = "ready"
    building = "building"
    built = "built"
    error = "error"


class MessageRole(str, enum.Enum):
    user = "user"
    assistant = "assistant"
    system = "system"


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    genre: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[ProjectStatus] = mapped_column(Enum(ProjectStatus), default=ProjectStatus.draft, nullable=False)

    # IR aberto — grafo semântico do jogo
    gameplay_graph: Mapped[dict | None] = mapped_column(JSONB)
    scene_graph: Mapped[dict | None] = mapped_column(JSONB)
    art_bible: Mapped[dict | None] = mapped_column(JSONB)
    narrative_graph: Mapped[dict | None] = mapped_column(JSONB)
    economy_graph: Mapped[dict | None] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="projects")  # noqa: F821
    messages: Mapped[list["ProjectMessage"]] = relationship(back_populates="project", cascade="all, delete-orphan", order_by="ProjectMessage.created_at")
    builds: Mapped[list["ProjectBuild"]] = relationship(back_populates="project", cascade="all, delete-orphan")  # noqa: F821
    assets: Mapped[list["Asset"]] = relationship(back_populates="project", cascade="all, delete-orphan")  # noqa: F821
    marketplace_item: Mapped["MarketplaceItem | None"] = relationship(back_populates="project")  # noqa: F821


class ProjectMessage(Base):
    __tablename__ = "project_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[MessageRole] = mapped_column(Enum(MessageRole), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    action_triggered: Mapped[str | None] = mapped_column(String(64))  # ex: "codegen", "build", "pixel"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped["Project"] = relationship(back_populates="messages")
