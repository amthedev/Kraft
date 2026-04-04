"""Worker de build — exporta projeto Godot para Web."""

import asyncio

import dramatiq
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.build import BuildStatus, ProjectBuild
from app.models.project import Project, ProjectStatus
from app.services.build_runner import build_and_upload
from app.workers import broker  # noqa: F401


@dramatiq.actor(queue_name="build", max_retries=2, time_limit=600_000)
def run_build(build_id: int) -> None:
    asyncio.run(_run_build(build_id))


async def _run_build(build_id: int) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(ProjectBuild).where(ProjectBuild.id == build_id))
        build = result.scalar_one_or_none()
        if not build:
            return

        build.status = BuildStatus.running
        await db.commit()

        # Atualiza status do projeto
        result = await db.execute(select(Project).where(Project.id == build.project_id))
        project = result.scalar_one_or_none()
        if project:
            project.status = ProjectStatus.building
            await db.commit()

        try:
            web_url, zip_url = await build_and_upload(build.project_id, build.id)
            build.status = BuildStatus.success
            build.web_url = web_url
            build.zip_url = zip_url
            if project:
                project.status = ProjectStatus.built

        except Exception as e:
            build.status = BuildStatus.failed
            build.logs = str(e)
            if project:
                project.status = ProjectStatus.error
            print(f"[build] Erro no build {build_id}: {e}")

        finally:
            await db.commit()
