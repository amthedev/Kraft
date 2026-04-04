from datetime import datetime

from pydantic import BaseModel

from app.models.marketplace import ItemStatus, LicenseType


class MarketplaceItemCreate(BaseModel):
    title: str
    description: str | None = None
    price: float = 0.0
    license: LicenseType = LicenseType.personal


class MarketplaceItemOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    project_id: int
    seller_id: int
    title: str
    description: str | None
    price: float
    license: LicenseType
    status: ItemStatus
    downloads: int
    rating: float
    cover_url: str | None
    demo_url: str | None
    seller_username: str | None = None
    created_at: datetime
