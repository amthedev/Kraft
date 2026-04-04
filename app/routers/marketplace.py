from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.models.marketplace import ItemStatus, MarketplaceItem, MarketplaceSale
from app.models.project import Project
from app.models.user import User
from app.schemas.marketplace import MarketplaceItemCreate, MarketplaceItemOut

router = APIRouter(prefix="/api/marketplace", tags=["marketplace"])


def _to_item_out(item: MarketplaceItem) -> MarketplaceItemOut:
    data = MarketplaceItemOut.model_validate(item)
    data.seller_username = item.seller.username if item.seller else None
    return data


@router.get("", response_model=list[MarketplaceItemOut])
async def list_items(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(MarketplaceItem)
        .options(selectinload(MarketplaceItem.seller))
        .where(MarketplaceItem.status == ItemStatus.published)
        .order_by(MarketplaceItem.downloads.desc())
    )
    return [_to_item_out(item) for item in result.scalars().all()]


@router.post("/{project_id}/publish", response_model=MarketplaceItemOut, status_code=status.HTTP_201_CREATED)
async def publish_item(
    project_id: int,
    data: MarketplaceItemCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Project).where(Project.id == project_id, Project.user_id == current_user.id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")

    result = await db.execute(select(MarketplaceItem).where(MarketplaceItem.project_id == project_id))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Projeto já publicado na loja")

    item = MarketplaceItem(
        project_id=project_id,
        seller_id=current_user.id,
        status=ItemStatus.published,
        **data.model_dump(),
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.post("/{item_id}/buy", status_code=status.HTTP_201_CREATED)
async def buy_item(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(MarketplaceItem).where(MarketplaceItem.id == item_id, MarketplaceItem.status == ItemStatus.published))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item não encontrado")

    if item.seller_id == current_user.id:
        raise HTTPException(status_code=400, detail="Você não pode comprar seu próprio item")

    commission = item.price * settings.platform_commission_percent / 100
    sale = MarketplaceSale(item_id=item_id, buyer_id=current_user.id, amount=item.price, commission=commission)
    item.downloads += 1
    db.add(sale)
    await db.commit()
    return {"message": "Compra realizada com sucesso", "item_id": item_id}
