"""
Codegen Godot — gera GDScript e cenas .tscn em módulos para jogos massivos.

Gera 7 módulos sequencialmente, cada um com uma chamada dedicada ao GPT-4.1.
Isso permite gerar 50.000+ tokens de código para jogos do nível de RDR2/GTA.
"""

import json
import os
from pathlib import Path

import openai

from app.config import settings

# ── Prompts base por módulo ────────────────────────────────────────────────────

_BASE = """Você é um engenheiro sênior de Godot 4 especializado em jogos AAA massivos.
Gere código GDScript 4.x de alta qualidade para o módulo solicitado.
Use APENAS GDScript — nunca C#.
Retorne JSON: { "files": { "<caminho>": "<conteúdo>" } }
Regras:
- Godot 4 syntax: @onready, @export, super(), SignalClass, etc.
- Todos os paths relativos à raiz do projeto
- Inclua docstrings e comentários nos sistemas complexos
- Para mundos abertos: use SceneTree streaming com WorldEnvironment
- Para NPCs: use NavigationAgent3D + StateMachine pattern
- Para diálogos: use Resource customizado (DialogueData)
"""

_MODULE_PROMPTS = {
    "core": _BASE + """
MÓDULO: Core / Fundação
Gere os arquivos fundamentais:
- project.godot (configurado para export Web e 3D)
- autoload/GameManager.gd (singleton: estado global, save/load)
- autoload/EventBus.gd (barramento de eventos com sinais tipados)
- autoload/AudioManager.gd (música, SFX, camadas de audio)
- autoload/SaveSystem.gd (serialize/deserialize estado do mundo)
- res://default_env.tres (WorldEnvironment com SDFGI, SSAO, glow)
""",

    "world": _BASE + """
MÓDULO: World / Mundo Aberto
Gere o sistema de mundo massivo:
- world/WorldMap.tscn (raiz do mundo, com TerrainGenerator e SceneStreamer)
- world/TerrainGenerator.gd (geração procedural de terreno com biomas via noise)
- world/SceneStreamer.gd (carrega/descarrega regiões dinamicamente baseado na posição do jogador)
- world/BiomeManager.gd (determina bioma por posição, retorna propriedades: vegetação, enemies, ambiance)
- world/WeatherSystem.gd (ciclo dia/noite, chuva, neve, névoa, trovão com partículas e AudioStream)
- world/PointOfInterest.gd (base para cidades, fazendas, ruínas — com spawn de NPCs e loot)
- world/RegionData.tres (Resource com dados de cada região)
""",

    "player": _BASE + """
MÓDULO: Player / Jogador
Gere o sistema completo do jogador:
- player/Player.tscn (CharacterBody3D com camera, mesh, hitbox, interaction area)
- player/PlayerController.gd (movimento 3D suave, sprint, crouch, swim, climb)
- player/PlayerCamera.gd (camera em terceira pessoa com spring arm, zoom, lock-on)
- player/InteractionSystem.gd (ray cast, detecção de objetos interativos, prompt UI)
- player/InventorySystem.gd (itens, peso, categorias, equip/unequip com sinal)
- player/StatsComponent.gd (HP, stamina, hunger, thirst, XP, level up, skill points)
- player/PlayerAnimationTree.gd (AnimationTree com blend spaces para locomoção e combate)
""",

    "npc": _BASE + """
MÓDULO: NPC / Personagens
Gere o sistema de NPCs do mundo:
- npc/NPC.tscn (CharacterBody3D com NavigationAgent3D, AnimationPlayer, InteractionArea)
- npc/NPCController.gd (estado base: idle, patrol, follow, flee, attack, converse)
- npc/AIStateMachine.gd (máquina de estados genérica com transições condicionais)
- npc/ScheduleSystem.gd (rotina diária por horário: work, eat, sleep, wander)
- npc/FactionSystem.gd (relações entre facções, reputação do jogador, hostilidade dinâmica)
- npc/DialogueSystem.gd (carrega DialogueData, executa árvore de diálogo, dispara ações)
- npc/MerchantComponent.gd (inventário de loja, preços dinâmicos, restock)
- npc/BossController.gd (extends NPCController, fases de combate, habilidades especiais)
- npc/AnimalController.gd (extends NPCController, comportamento de fauna: herbívoro/carnívoro)
""",

    "quest": _BASE + """
MÓDULO: Quest / Sistema de Missões
Gere o sistema completo de quests:
- quest/QuestManager.gd (autoload — rastreia quests ativas, completas, falhas)
- quest/QuestData.gd (Resource: id, title, description, objectives[], rewards{})
- quest/Objective.gd (Resource: type, target, count, current, completed)
- quest/QuestTrigger.gd (Area3D que inicia quests ao entrar na zona)
- quest/QuestMarker.gd (Node3D com ícone flutuante e seta de direção no HUD)
- quest/RewardSystem.gd (distribui XP, itens, currency, reputação ao completar quest)
- quest/JournalUI.tscn (interface do diário com lista de quests, objetivos, mapa)
- quest/WorldEvent.gd (eventos randômicos: emboscada, comerciante em apuros, festival)
""",

    "combat": _BASE + """
MÓDULO: Combat / Sistema de Combate
Gere o sistema de combate avançado:
- combat/CombatSystem.gd (gerencia combates, sequência de ataques, bloqueio, esquiva)
- combat/WeaponBase.gd (Resource base para armas: dano, alcance, velocidade, animação)
- combat/MeleeWeapon.gd (extends WeaponBase: hitbox física, combos, stagger)
- combat/RangedWeapon.gd (extends WeaponBase: projétil, trajetória balística, reload)
- combat/HealthSystem.gd (Component: HP, armor, resistências, morte, respawn)
- combat/HitboxComponent.gd (Area3D para detecção de dano com máscara de colisão)
- combat/DamageNumber.gd (Label3D flutuante com animação de popup)
- combat/CombatAnimator.gd (coordena AnimationTree durante combate)
- combat/StatusEffect.gd (Resource: poison, burn, slow, stun com duração e tick)
""",

    "ui": _BASE + """
MÓDULO: UI / Interface
Gere toda a interface do jogo:
- ui/HUD.tscn (CanvasLayer: barra de HP, stamina, minimap, crosshair, notificações)
- ui/Minimap.gd (SubViewport renderizando mundo de cima com ícones de POIs)
- ui/Inventory.tscn (grade de itens, arrastar/soltar, tooltips, comparação de stats)
- ui/ShopUI.tscn (loja com compra/venda, preview de item, balanço de moeda)
- ui/DialogueUI.tscn (caixa de diálogo com portrait do NPC, texto animado, opções)
- ui/PauseMenu.tscn (salvar, carregar, opções, sair)
- ui/MapUI.tscn (mapa do mundo com marcadores, zoom, fast travel)
- ui/QuestNotification.gd (popup animado ao receber/completar quest)
- ui/LoadingScreen.tscn (tela de carregamento com dica e barra de progresso)
""",
}


async def generate_godot_project(
    project_id: int,
    gameplay_graph: dict,
    scene_graph: dict | None,
    world_graph: dict | None = None,
    character_graph: dict | None = None,
    quest_graph: dict | None = None,
    dialogue_graph: dict | None = None,
    art_bible: dict | None = None,
) -> dict[str, str]:
    """Gera todos os arquivos do projeto Godot em 7 módulos sequenciais."""
    all_files: dict[str, str] = {}

    # Contextos por módulo — cada um recebe apenas o que é relevante
    module_contexts = {
        "core": {
            "name": gameplay_graph.get("name", "Kraft Game"),
            "genre": gameplay_graph.get("genre", ""),
            "systems": gameplay_graph.get("systems", []),
        },
        "world": {
            "world_graph": world_graph or {},
            "scene_graph": scene_graph or {},
        },
        "player": {
            "player": (character_graph or {}).get("player", {}),
            "mechanics": gameplay_graph.get("mechanics", []),
            "systems": gameplay_graph.get("systems", []),
        },
        "npc": {
            "npcs": (character_graph or {}).get("npcs", []),
            "factions": (character_graph or {}).get("factions", []),
            "dialogue_graph": dialogue_graph or {},
        },
        "quest": {
            "quest_graph": quest_graph or {},
            "world_events": (world_graph or {}).get("world_events", []),
        },
        "combat": {
            "entities": gameplay_graph.get("entities", []),
            "mechanics": gameplay_graph.get("mechanics", []),
        },
        "ui": {
            "art_bible": art_bible or {},
            "economy_systems": gameplay_graph.get("systems", []),
        },
    }

    async with openai.AsyncOpenAI(api_key=settings.openai_api_key) as client:
        for module_name, context in module_contexts.items():
            context_str = json.dumps(context, ensure_ascii=False, indent=2)
            user_msg = f"Contexto do projeto:\n{context_str}\n\nGere o módulo '{module_name}'."

            try:
                response = await client.chat.completions.create(
                    model="gpt-4.1",
                    max_tokens=8192,
                    messages=[
                        {"role": "system", "content": _MODULE_PROMPTS[module_name]},
                        {"role": "user", "content": user_msg},
                    ],
                    response_format={"type": "json_object"},
                )

                raw = response.choices[0].message.content
                data = json.loads(raw)
                module_files = data.get("files", {})
                all_files.update(module_files)

            except Exception:
                # Módulo falhou — continua com os demais
                pass

    return all_files


def write_project_files(project_id: int, files: dict[str, str]) -> Path:
    """Salva os arquivos gerados no diretório de trabalho."""
    project_dir = Path(settings.projects_workdir) / str(project_id) / "godot"
    project_dir.mkdir(parents=True, exist_ok=True)

    for relative_path, content in files.items():
        file_path = project_dir / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")

    return project_dir
