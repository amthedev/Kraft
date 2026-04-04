from datetime import datetime

from pydantic import BaseModel

from app.models.asset import AssetType


class AssetOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    project_id: int
    type: AssetType
    name: str
    url: str | None
    meta: dict | None
    created_at: datetime
