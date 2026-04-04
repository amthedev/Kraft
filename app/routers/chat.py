import json

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.config import settings
from app.database import AsyncSessionLocal, get_db
from app.models.project import MessageRole, Project, ProjectMessage
from app.models.user import User
from app.schemas.project import MessageCreate, MessageOut
from app.services.ai_orchestrator import orchestrate

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.get("/{project_id}/messages", response_model=list[MessageOut])
async def get_messages(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Project).where(Project.id == project_id, Project.user_id == current_user.id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Projeto não encontrado")

    result = await db.execute(
        select(ProjectMessage).where(ProjectMessage.project_id == project_id).order_by(ProjectMessage.created_at)
    )
    return result.scalars().all()


@router.post("/{project_id}/messages", response_model=MessageOut)
async def send_message(
    project_id: int,
    data: MessageCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Project).where(Project.id == project_id, Project.user_id == current_user.id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")

    # Salva mensagem do usuário
    user_msg = ProjectMessage(project_id=project_id, role=MessageRole.user, content=data.content)
    db.add(user_msg)
    await db.commit()
    await db.refresh(user_msg)

    # Dispara orquestração em background (enfileira workers)
    await orchestrate(project, data.content, db)

    return user_msg


@router.websocket("/{project_id}/ws")
async def chat_ws(project_id: int, websocket: WebSocket, token: str = Query(default="")):
    """WebSocket para atualizações em tempo real do projeto (progresso de geração)."""
    try:
        payload = jwt.decode(token, settings.app_secret_key, algorithms=[settings.jwt_algorithm])
        int(payload.get("sub", 0))
    except (JWTError, ValueError):
        await websocket.close(code=4001)
        return

    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)

            async with AsyncSessionLocal() as db:
                result = await db.execute(select(Project).where(Project.id == project_id))
                project = result.scalar_one_or_none()
                if not project:
                    await websocket.send_json({"error": "Projeto não encontrado"})
                    break

                # Enfileira orquestração e responde com status
                content = msg.get("content", "")
                user_msg = ProjectMessage(project_id=project_id, role=MessageRole.user, content=content)
                db.add(user_msg)
                await db.commit()

                await orchestrate(project, content, db)
                await websocket.send_json({"status": "queued", "message_id": user_msg.id})

    except WebSocketDisconnect:
        pass
