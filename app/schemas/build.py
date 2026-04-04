from datetime import datetime

from pydantic import BaseModel

from app.models.build import BuildStatus


class BuildOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    project_id: int
    version: int
    status: BuildStatus
    web_url: str | None
    zip_url: str | None
    logs: str | None
    created_at: datetime
