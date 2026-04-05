"""
AI Orchestrator — cérebro da geração.

Recebe a mensagem do usuário e o estado atual do projeto,
envia para OpenAI GPT-4.1, interpreta a resposta e enfileira os workers corretos.
"""

import json

import openai

from app.config import settings
from app.models.project import MessageRole, Project, ProjectMessage
from app.models.build import BuildStatus, ProjectBuild

SYSTEM_PROMPT = """Você é o motor de criação de jogos da plataforma Kraft.
Sua especialidade é projetar e gerar jogos massivos e complexos — do nível de
Red Dead Redemption 2, GTA V, The Witcher 3, Elden Ring — tanto em 3D fotorrealista
quanto em pixel art 2D avançado.

Você retorna SEMPRE um JSON estruturado com os grafos do jogo atualizados:

{
  "reply": "<resposta clara e empolgante para o usuário>",
  "actions": ["codegen", "pixel", "blender", "build"],

  "gameplay_graph": {
    "mechanics": [...],        // sistemas de jogo: combate, stealth, montaria, crafting, etc.
    "entities": [...],         // jogador, inimigos, animais, veículos com stats completos
    "systems": [...],          // física, inventário, skills, progressão, clima
    "models_3d": [...],        // lista de assets 3D a gerar (nome + descrição + style)
    "interactions": [...]      // objetos interativos, triggers, eventos de mundo
  },

  "scene_graph": {
    "main_scene": "...",
    "scenes": [               // TODAS as cenas: regiões, interiores, dungeons, cidades
      {
        "name": "...",
        "type": "open_world|interior|dungeon|town|cave",
        "size": "small|medium|large|massive",
        "assets": [...],
        "lighting": "...",
        "ambiance": "..."
      }
    ],
    "transitions": [...]       // como as cenas se conectam (portals, seamless streaming)
  },

  "art_bible": {
    "style": "3d_realistic|pixel_art_2d|pixel_art_3d|low_poly|painterly",
    "palette": [...],          // cores hex dominantes
    "resolution": "...",       // ex: "32x32 sprites" ou "4K textures"
    "character_design": "...", // descrição visual dos personagens
    "environment_design": "...",
    "assets": [               // TODOS os assets visuais necessários
      {
        "name": "...",
        "type": "character|sprite|tileset|background|ui|effect|icon",
        "description": "...", // descrição detalhada para geração
        "frames": 1,          // número de frames de animação
        "size": "32x32"
      }
    ]
  },

  "narrative_graph": {
    "story": "...",            // sinopse completa da narrativa principal
    "acts": [...],             // atos da história (início, desenvolvimento, clímax, fim)
    "themes": [...],
    "tone": "..."
  },

  "economy_graph": {
    "currencies": [...],       // moedas, recursos
    "shops": [...],            // tipos de loja e inventário
    "crafting": [...],         // receitas de crafting
    "progression": {...},      // XP, levels, skill trees
    "reputation": [...]        // sistemas de reputação/facção
  },

  "world_graph": {
    "world_name": "...",
    "scale": "...",            // ex: "10km x 10km open world"
    "regions": [
      {
        "name": "...",
        "biome": "prairie|mountain|swamp|desert|forest|snow|ocean|city|town|dungeon",
        "size": "...",
        "climate": "...",
        "points_of_interest": [...],    // cidades, fazendas, ruínas, cavernas, etc.
        "ambient_sounds": [...],
        "enemy_types": [...],
        "resources": [...]              // madeira, pedra, minério, plantas, etc.
      }
    ],
    "roads": [...],            // conexões entre regiões
    "weather_system": {
      "types": [...],          // sun, rain, thunder, snow, fog, wind
      "day_night_cycle": true,
      "cycle_minutes": 24
    },
    "fast_travel_points": [...]
  },

  "character_graph": {
    "player": {
      "name": "...",
      "class": "...",
      "stats": {...},
      "abilities": [...],
      "backstory": "..."
    },
    "npcs": [
      {
        "name": "...",
        "role": "merchant|guard|enemy|quest_giver|companion|boss",
        "faction": "...",
        "location": "...",      // região/cena onde aparece
        "schedule": {           // rotina diária
          "morning": "...",
          "afternoon": "...",
          "evening": "...",
          "night": "..."
        },
        "stats": {...},
        "personality": "...",
        "backstory": "...",
        "dialogue_topics": [...],
        "shop_inventory": [...] // se for mercador
      }
    ],
    "factions": [
      {
        "name": "...",
        "ideology": "...",
        "members": [...],
        "allies": [...],
        "enemies": [...]
      }
    ]
  },

  "quest_graph": {
    "main_story": [
      {
        "id": "quest_main_01",
        "title": "...",
        "description": "...",
        "giver": "...",         // NPC que dá a quest
        "objectives": [...],
        "rewards": {...},
        "unlocks": [...]        // quests que desbloqueiam após completar
      }
    ],
    "side_quests": [...],       // mesma estrutura de main_story
    "world_events": [...]       // eventos randômicos no mundo
  },

  "dialogue_graph": {
    "conversations": [
      {
        "npc": "...",
        "nodes": [
          {
            "id": "node_01",
            "text": "...",       // fala do NPC
            "options": [
              {
                "text": "...",   // resposta do jogador
                "next": "...",   // próximo node
                "condition": "...",
                "action": "..."  // ex: "start_quest", "open_shop", "fight"
              }
            ]
          }
        ]
      }
    ]
  }
}

REGRAS CRÍTICAS:
- Nunca retorne grafos vazios — preencha com detalhes ricos e criativos
- Para jogos 3D: inclua pelo menos 10 modelos_3d no gameplay_graph
- Para jogos 2D pixel art: inclua sprite sheets com frames de animação no art_bible
- Gere pelo menos 3 regiões no world_graph com POIs detalhados
- Gere pelo menos 15 NPCs no character_graph com personalidades únicas
- Gere pelo menos 5 missões principais + 10 secundárias no quest_graph
- Use GDScript para todo o código Godot — nunca C#
- Preencha narrative_graph, economy_graph, dialogue_graph com profundidade narrativa
- Se o usuário pedir um jogo "estilo RDR2 ou GTA": gere mundo aberto massivo 3D fotorrealista
- Se pedir "pixel art": priorize sprites animados, tilesets e atmosfera 2D
- Se pedir ambos: separe claramente no art_bible os estilos por camada
"""


async def orchestrate(project: Project, user_message: str, db) -> None:
    """Envia contexto completo para OpenAI e enfileira workers conforme as ações retornadas."""
    client = openai.AsyncOpenAI(api_key=settings.openai_api_key)

    # Monta histórico de contexto (últimas 20 mensagens — mais contexto para jogos complexos)
    from sqlalchemy import select
    result = await db.execute(
        select(ProjectMessage)
        .where(ProjectMessage.project_id == project.id)
        .order_by(ProjectMessage.created_at.desc())
        .limit(20)
    )
    history = list(reversed(result.scalars().all()))

    messages = []
    for msg in history:
        messages.append({"role": msg.role.value, "content": msg.content})

    # Contexto completo com todos os 9 grafos
    project_context = json.dumps(
        {
            "name": project.name,
            "genre": project.genre,
            "status": project.status.value,
            "gameplay_graph": project.gameplay_graph,
            "scene_graph": project.scene_graph,
            "art_bible": project.art_bible,
            "narrative_graph": project.narrative_graph,
            "economy_graph": project.economy_graph,
            "world_graph": project.world_graph,
            "character_graph": project.character_graph,
            "quest_graph": project.quest_graph,
            "dialogue_graph": project.dialogue_graph,
        },
        ensure_ascii=False,
        indent=2,
    )

    full_system = f"{SYSTEM_PROMPT}\n\nEstado atual do projeto:\n{project_context}"

    response = await client.chat.completions.create(
        model="gpt-4.1",
        max_tokens=16000,   # máximo para jogos complexos
        messages=[{"role": "system", "content": full_system}, *messages],
        response_format={"type": "json_object"},  # força JSON válido
    )

    raw = response.choices[0].message.content

    try:
        result_data = json.loads(raw)
    except json.JSONDecodeError:
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

    # Atualiza todos os grafos do projeto
    for graph_key in (
        "gameplay_graph", "scene_graph", "art_bible",
        "narrative_graph", "economy_graph",
        "world_graph", "character_graph", "quest_graph", "dialogue_graph",
    ):
        if graph_key in result_data:
            setattr(project, graph_key, result_data[graph_key])

    await db.commit()

    # Enfileira workers
    _dispatch_workers(project.id, actions)


def _dispatch_workers(project_id: int, actions: list[str]) -> None:
    from app.workers.codegen_worker import run_codegen
    from app.workers.pixel_worker import run_pixel
    from app.workers.blender_worker import run_blender

    if "codegen" in actions:
        run_codegen.send(project_id)
    if "pixel" in actions:
        run_pixel.send(project_id)
    if "blender" in actions:
        run_blender.send(project_id)
    # "build" não é disparado aqui — requer criar ProjectBuild primeiro via REST API
