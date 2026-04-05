"""Worker de geração de assets 3D com Blender."""

import asyncio

import dramatiq
from sqlalchemy import select

from app.database import make_session_factory
from app.models.asset import Asset, AssetType
from app.models.project import Project
from app.services.blender_fabricator import fabricate_3d_asset
from app.workers import broker  # noqa: F401


@dramatiq.actor(queue_name="blender", max_retries=2, time_limit=300_000)
def run_blender(project_id: int) -> None:
    asyncio.run(_run_blender(project_id))


async def _run_blender(project_id: int) -> None:
    async with make_session_factory()() as db:
        result = await db.execute(select(Project).where(Project.id == project_id))
        project = result.scalar_one_or_none()
        if not project:
            return

        gameplay_graph = project.gameplay_graph or {}
        models_needed = gameplay_graph.get("models_3d", [])

        for model_def in models_needed:
            name = model_def.get("name", "model")
            description = model_def.get("description", name)

            try:
                asset_type = model_def.get("type", "prop")
                style = model_def.get("style", "low_poly")
                url = await fabricate_3d_asset(project_id, name, description, asset_type=asset_type, style=style)
                if url:
                    asset = Asset(
                        project_id=project_id,
                        type=AssetType.model,
                        name=name,
                        url=url,
                        meta={"source": "blender", "format": "glb", "asset_type": asset_type, "style": style},
                    )
                    db.add(asset)
            except Exception as e:
                print(f"[blender] Erro no modelo '{name}' projeto {project_id}: {e}")

        await db.commit()
