"""Worker de geração de pixel art com DALL-E 3."""

import asyncio

import dramatiq
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.asset import Asset, AssetType
from app.models.project import Project
from app.services.pixel_forge import generate_full_asset
from app.workers import broker  # noqa: F401


@dramatiq.actor(queue_name="pixel", max_retries=2, time_limit=600_000)
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
            asset_type_str = asset_def.get("type", "sprite")

            # Mapeia tipo do art_bible para AssetType
            type_map = {
                "character": AssetType.sprite,
                "sprite": AssetType.sprite,
                "tileset": AssetType.tileset,
                "background": AssetType.scene,
                "ui": AssetType.ui,
                "effect": AssetType.sprite,
                "icon": AssetType.ui,
                "portrait": AssetType.sprite,
            }
            asset_type = type_map.get(asset_type_str, AssetType.sprite)

            try:
                url, spec = await generate_full_asset(
                    project_id=project_id,
                    asset_name=name,
                    asset_description=description,
                    art_bible=art_bible,
                )

                asset = Asset(
                    project_id=project_id,
                    type=asset_type,
                    name=name,
                    url=url,
                    meta={
                        **spec,
                        "generated_by": "dall-e-3",
                        "frames": spec.get("frames", 1),
                        "pixel_size": spec.get("pixel_size", "64x64"),
                    },
                )
                db.add(asset)
                await db.flush()

            except Exception as e:
                print(f"[pixel] Erro gerando asset '{name}' no projeto {project_id}: {e}")

        await db.commit()
