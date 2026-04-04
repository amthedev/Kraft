"""Worker de geração de pixel art."""

import asyncio

import dramatiq
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.asset import Asset, AssetType
from app.models.project import Project
from app.services.pixel_forge import plan_pixel_asset, save_pixel_asset
from app.workers import broker  # noqa: F401


@dramatiq.actor(queue_name="pixel", max_retries=3)
def run_pixel(project_id: int) -> None:
    asyncio.run(_run_pixel(project_id))


async def _run_pixel(project_id: int) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Project).where(Project.id == project_id))
        project = result.scalar_one_or_none()
        if not project:
            return

        art_bible = project.art_bible or {}
        assets_to_generate = art_bible.get("assets", [])

        for asset_def in assets_to_generate:
            name = asset_def.get("name", "sprite")
            description = asset_def.get("description", name)

            try:
                spec = await plan_pixel_asset(description, art_bible)
                # Aqui chamaria modelo de imagem externo; por ora registra asset planejado
                asset = Asset(
                    project_id=project_id,
                    type=AssetType.sprite,
                    name=name,
                    meta=spec,
                )
                db.add(asset)

            except Exception as e:
                print(f"[pixel] Erro gerando asset '{name}' no projeto {project_id}: {e}")

        await db.commit()
