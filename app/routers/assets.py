from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models.asset import Asset
from app.models.project import Project
from app.models.user import User
from app.schemas.asset import AssetOut
from app.services.storage import get_asset_url

router = APIRouter(prefix="/api/assets", tags=["assets"])


async def _get_asset_with_auth(asset_id: int, db: AsyncSession, current_user: User) -> Asset:
    """Busca asset verificando que o usuário é dono do projeto pai."""
    result = await db.execute(
        select(Asset).join(Project, Asset.project_id == Project.id).where(
            Asset.id == asset_id,
            Project.user_id == current_user.id,
        )
    )
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset não encontrado")
    return asset


@router.get("/{project_id}", response_model=list[AssetOut])
async def list_assets(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Project).where(Project.id == project_id, Project.user_id == current_user.id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Projeto não encontrado")

    result = await db.execute(
        select(Asset).where(Asset.project_id == project_id).order_by(Asset.created_at)
    )
    return result.scalars().all()


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asset(
    asset_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    asset = await _get_asset_with_auth(asset_id, db, current_user)
    await db.delete(asset)
    await db.commit()


@router.get("/{asset_id}/download")
async def download_asset(
    asset_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    asset = await _get_asset_with_auth(asset_id, db, current_user)
    if not asset.url:
        raise HTTPException(status_code=404, detail="Asset sem URL de download")

    from app.config import settings
    public_prefix = settings.storage_public_url.rstrip("/") + "/"
    key = asset.url.replace(public_prefix, "") if asset.url.startswith(public_prefix) else asset.url

    url = await get_asset_url(key)
    return {"url": url, "name": asset.name, "type": asset.type}
