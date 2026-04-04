from datetime import datetime

from pydantic import BaseModel

from app.models.project import MessageRole, ProjectStatus


class ProjectCreate(BaseModel):
    name: str
    description: str | None = None
    genre: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    genre: str | None = None


class ProjectOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    name: str
    description: str | None
    genre: str | None
    status: ProjectStatus
    gameplay_graph: dict | None
    scene_graph: dict | None
    art_bible: dict | None
    narrative_graph: dict | None
    economy_graph: dict | None
    created_at: datetime
    updated_at: datetime


class MessageCreate(BaseModel):
    content: str


class MessageOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    project_id: int
    role: MessageRole
    content: str
    action_triggered: str | None
    created_at: datetime
