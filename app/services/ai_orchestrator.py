"""
AI Orchestrator — cérebro da geração.

Recebe a mensagem do usuário e o estado atual do projeto,
envia para Claude, interpreta a resposta e enfileira os workers corretos.
"""

import json

import anthropic

from app.config import settings
from app.models.project import MessageRole, Project, ProjectMessage
from app.models.build import BuildStatus, ProjectBuild

SYSTEM_PROMPT = """Você é o motor de criação de jogos da plataforma Kraft.
Sua tarefa é analisar a mensagem do usuário e retornar um JSON estruturado com:

{
  "reply": "<resposta amigável para o usuário>",
  "actions": ["codegen", "pixel", "blender", "build"],  // lista de ações a disparar
  "gameplay_graph": { ... },  // IR atualizado do jogo (omita se não mudar)
  "scene_graph": { ... },
  "art_bible": { ... }
}

Regras:
- "codegen" gera/atualiza GDScript e cenas Godot
- "pixel" gera sprites e tilesets 2D
- "blender" gera modelos 3D (só quando 3D for necessário)
- "build" exporta o projeto para Web (só quando o código estiver pronto)
- Sempre inclua "reply" com uma resposta clara ao usuário
- Use GDScript — nunca C#
- O gameplay_graph deve refletir TODA a lógica do jogo em JSONB aberto
"""


async def orchestrate(project: Project, user_message: str, db) -> None:
    """Envia contexto para Claude e enfileira workers conforme as ações retornadas."""
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    # Monta histórico de contexto (últimas 10 mensagens)
    from sqlalchemy import select
    result = await db.execute(
        select(ProjectMessage)
        .where(ProjectMessage.project_id == project.id)
        .order_by(ProjectMessage.created_at.desc())
        .limit(10)
    )
    history = list(reversed(result.scalars().all()))

    messages = []
    for msg in history:
        messages.append({"role": msg.role.value, "content": msg.content})

    # Contexto do projeto atual
    project_context = json.dumps(
        {
            "name": project.name,
            "genre": project.genre,
            "status": project.status.value,
            "gameplay_graph": project.gameplay_graph,
            "scene_graph": project.scene_graph,
            "art_bible": project.art_bible,
        },
        ensure_ascii=False,
        indent=2,
    )

    full_system = f"{SYSTEM_PROMPT}\n\nEstado atual do projeto:\n{project_context}"

    response = await client.messages.create(
        model="claude-opus-4-6",
        max_tokens=4096,
        system=full_system,
        messages=messages,
    )

    raw = response.content[0].text

    # Tenta extrair JSON da resposta
    try:
        # Claude às vezes envolve JSON em ```json ... ```
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()
        result_data = json.loads(raw)
    except (json.JSONDecodeError, IndexError):
        result_data = {"reply": raw, "actions": []}

    reply = result_data.get("reply", "Processando...")
    actions = result_data.get("actions", [])

    # Salva resposta do assistente
    assistant_msg = ProjectMessage(
        project_id=project.id,
        role=MessageRole.assistant,
        content=reply,
        action_triggered=",".join(actions) if actions else None,
    )
    db.add(assistant_msg)

    # Atualiza IR do projeto se Claude retornou novos grafos
    if "gameplay_graph" in result_data:
        project.gameplay_graph = result_data["gameplay_graph"]
    if "scene_graph" in result_data:
        project.scene_graph = result_data["scene_graph"]
    if "art_bible" in result_data:
        project.art_bible = result_data["art_bible"]

    await db.commit()

    # Enfileira workers
    _dispatch_workers(project.id, actions)


def _dispatch_workers(project_id: int, actions: list[str]) -> None:
    from app.workers.codegen_worker import run_codegen
    from app.workers.pixel_worker import run_pixel
    from app.workers.blender_worker import run_blender
    from app.workers.build_worker import run_build

    if "codegen" in actions:
        run_codegen.send(project_id)
    if "pixel" in actions:
        run_pixel.send(project_id)
    if "blender" in actions:
        run_blender.send(project_id)
    if "build" in actions:
        run_build.send(project_id)
