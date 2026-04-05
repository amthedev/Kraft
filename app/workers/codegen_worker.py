"""Worker de geração de código Godot."""

import asyncio

import dramatiq
from sqlalchemy import select

from app.database import make_session_factory
from app.models.project import Project, ProjectStatus
from app.services.codegen_godot import generate_godot_project, write_project_files
from app.workers import broker  # noqa: F401 — inicializa broker


@dramatiq.actor(queue_name="codegen", max_retries=3)
def run_codegen(project_id: int) -> None:
    asyncio.run(_run_codegen(project_id))


async def _run_codegen(project_id: int) -> None:
    async with make_session_factory()() as db:
        result = await db.execute(select(Project).where(Project.id == project_id))
        project = result.scalar_one_or_none()
        if not project:
            return

        project.status = ProjectStatus.generating
        await db.commit()

        try:
            files = await generate_godot_project(
                project_id,
                project.gameplay_graph or {},
                project.scene_graph,
                world_graph=project.world_graph,
                character_graph=project.character_graph,
                quest_graph=project.quest_graph,
                dialogue_graph=project.dialogue_graph,
                art_bible=project.art_bible,
            )

            if files:
                write_project_files(project_id, files)
                project.status = ProjectStatus.ready
            else:
                project.status = ProjectStatus.error

        except Exception as e:
            project.status = ProjectStatus.error
            print(f"[codegen] Erro no projeto {project_id}: {e}")
        finally:
            await db.commit()
