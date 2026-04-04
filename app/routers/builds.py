from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models.build import BuildStatus, ProjectBuild
from app.models.project import Project
from app.models.user import User
from app.schemas.build import BuildOut
from app.workers.build_worker import run_build

router = APIRouter(prefix="/api/builds", tags=["builds"])


@router.post("/{project_id}", response_model=BuildOut, status_code=202)
async def trigger_build(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Project).where(Project.id == project_id, Project.user_id == current_user.id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")

    # Calcula próxima versão
    result = await db.execute(
        select(ProjectBuild).where(ProjectBuild.project_id == project_id).order_by(ProjectBuild.version.desc())
    )
    last = result.scalars().first()
    version = (last.version + 1) if last else 1

    build = ProjectBuild(project_id=project_id, version=version, status=BuildStatus.queued)
    db.add(build)
    await db.commit()
    await db.refresh(build)

    run_build.send(build.id)
    return build


@router.get("/{project_id}", response_model=list[BuildOut])
async def list_builds(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Project).where(Project.id == project_id, Project.user_id == current_user.id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Projeto não encontrado")

    result = await db.execute(
        select(ProjectBuild).where(ProjectBuild.project_id == project_id).order_by(ProjectBuild.created_at.desc())
    )
    return result.scalars().all()


@router.get("/{project_id}/latest", response_model=BuildOut)
async def latest_build(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Project).where(Project.id == project_id, Project.user_id == current_user.id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Projeto não encontrado")

    result = await db.execute(
        select(ProjectBuild)
        .where(ProjectBuild.project_id == project_id)
        .order_by(ProjectBuild.created_at.desc())
    )
    build = result.scalars().first()
    if not build:
        raise HTTPException(status_code=404, detail="Nenhum build encontrado")
    return build
