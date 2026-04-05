"""
Codegen Godot — gera GDScript e cenas .tscn em módulos para jogos massivos.

Gera 7 módulos sequencialmente, cada um com uma chamada dedicada ao GPT-4.1.
Suporta dimensão 2D (pixel art + TileMap) e 3D (open world + CharacterBody3D).
"""

import json
from pathlib import Path

import openai

from app.config import settings

# ── Prompts base ────────────────────────────────────────────────────────────────

_BASE_3D = """Você é um engenheiro sênior de Godot 4 especializado em jogos AAA 3D massivos.
Gere código GDScript 4.x de alta qualidade para o módulo solicitado.
Use APENAS GDScript — nunca C#.
Retorne JSON: { "files": { "<caminho relativo>": "<conteúdo completo do arquivo>" } }
Regras gerais:
- Godot 4 syntax: @onready, @export, super(), signal, etc.
- Todos os paths relativos à raiz do projeto (sem res://)
- Inclua comentários nos sistemas complexos
- Para mundos abertos: use SceneTree streaming com WorldEnvironment
- Para NPCs: use NavigationAgent3D + StateMachine pattern
"""

_BASE_2D = """Você é um engenheiro sênior de Godot 4 especializado em jogos 2D pixel art.
Gere código GDScript 4.x de alta qualidade para o módulo solicitado.
Use APENAS GDScript — nunca C#.
Retorne JSON: { "files": { "<caminho relativo>": "<conteúdo completo do arquivo>" } }
Regras gerais:
- Godot 4 syntax: @onready, @export, super(), signal, etc.
- NUNCA use Node3D, CharacterBody3D, Camera3D, Area3D, NavigationAgent3D, Label3D
- Use SEMPRE: Node2D, CharacterBody2D, Camera2D, Area2D, NavigationAgent2D, Label
- Todos os paths relativos à raiz do projeto (sem res://)
- Sprites animados: use AnimationPlayer com Sprite2D (não AnimationTree 3D)
- Mapas de tiles: use TileMap com TileSet
"""

# ── Módulos 3D ──────────────────────────────────────────────────────────────────

_MODULE_PROMPTS_3D = {
    "core": _BASE_3D + """
MÓDULO: Core / Fundação 3D
Gere os arquivos fundamentais:
- project.godot (configurado para export Web, renderer Vulkan/Forward+)
- autoload/GameManager.gd (singleton: estado global, save/load, referências globais)
- autoload/EventBus.gd (barramento de eventos com sinais tipados)
- autoload/AudioManager.gd (música, SFX, camadas de audio, fade)
- autoload/SaveSystem.gd (serialize/deserialize estado do mundo em JSON)
- default_env.tres (WorldEnvironment com sky procedural, SSAO, glow suave)

IMPORTANTE no project.godot:
- Inclua: config/features=PackedStringArray("4.3", "Forward Plus")
- rendering/renderer/rendering_method="forward_plus"
- NÃO inclua run/main_scene (será definido pelo sistema)
""",

    "world": _BASE_3D + """
MÓDULO: World / Mundo Aberto 3D
Gere o sistema de mundo massivo:
- world/WorldMap.tscn — cena raiz do mundo 3D. OBRIGATÓRIO incluir estes nós filhos:
    [node name="DirectionalLight3D" type="DirectionalLight3D"]
    rotation_degrees = Vector3(-45, -30, 0)
    light_energy = 1.2
    shadow_enabled = true
    [node name="PlayerSpawn" type="Node3D"]  (posição onde o player nasce)
    [node name="TerrainRoot" type="Node3D"]  (filho onde o TerrainGenerator adiciona meshes)
    [node name="WeatherSystem" type="Node3D" parent="."]
    script = ExtResource("WeatherSystem.gd")
- world/TerrainGenerator.gd — gera terreno procedural com biomas via FastNoiseLite.
    DEVE criar StandardMaterial3D com vertex_color_use_as_albedo=true e atribuir ao MeshInstance3D.
    Exemplo: var mat = StandardMaterial3D.new(); mat.vertex_color_use_as_albedo = true; mesh_instance.material_override = mat
- world/SceneStreamer.gd — carrega/descarrega regiões; procura Player em get_tree().get_first_node_in_group("player")
- world/BiomeManager.gd — determina bioma por posição (noise-based)
- world/WeatherSystem.gd — ciclo dia/noite: atualiza DirectionalLight3D energy/color e WorldEnvironment
- world/PointOfInterest.gd — Area3D base para cidades, ruínas com spawn de NPCs
- world/RegionData.gd — Resource com campos: region_name, biome, npcs, music_track

LEMBRE: WorldMap.tscn NÃO deve referenciar Player.tscn diretamente — o player é instanciado pelo GameManager.
""",

    "player": _BASE_3D + """
MÓDULO: Player / Jogador 3D
Gere o sistema completo do jogador:
- player/Player.tscn — CharacterBody3D com:
    - MeshInstance3D (capsule mesh como placeholder)
    - CollisionShape3D (CapsuleShape3D)
    - SpringArm3D com Camera3D (terceira pessoa)
    - Area3D (InteractionArea para detectar objetos próximos)
    - add_to_group("player") no _ready()
- player/PlayerController.gd — movimento 3D: WASD, sprint (Shift), crouch (C), gravidade
- player/PlayerCamera.gd — controla SpringArm3D: rotação com mouse, zoom scroll, lock-on (Tab)
- player/InteractionSystem.gd — RayCast3D detecta interativos, mostra prompt UI via EventBus
- player/InventorySystem.gd — itens, peso, equip/unequip, emite signal inventory_changed
- player/StatsComponent.gd — HP, stamina, XP, level; emite sinais health_changed, level_up
""",

    "npc": _BASE_3D + """
MÓDULO: NPC / Personagens 3D
Gere o sistema de NPCs do mundo:
- npc/NPC.tscn — CharacterBody3D com NavigationAgent3D, AnimationPlayer, Area3D (detecção)
- npc/NPCController.gd — estados: IDLE, PATROL, FOLLOW, FLEE, ATTACK, TALK
- npc/AIStateMachine.gd — máquina de estados genérica com transições condicionais
- npc/ScheduleSystem.gd — rotina diária por horário: usa Time.get_time_dict_from_system()
- npc/FactionSystem.gd — relações facções, reputação do jogador (0-100 por facção)
- npc/DialogueSystem.gd — carrega DialogueData Resource, exibe via EventBus signal show_dialogue
- npc/MerchantComponent.gd — inventário de loja, preços dinâmicos
- npc/BossController.gd — extends NPCController, fases de combate por HP%
- npc/AnimalController.gd — extends NPCController, comportamento fauna
""",

    "quest": _BASE_3D + """
MÓDULO: Quest / Sistema de Missões
Gere o sistema completo de quests:
- quest/QuestManager.gd — autoload, rastreia quests ativas/completas/falhas
- quest/QuestData.gd — Resource: id, title, description, objectives: Array[Objective], rewards: Dictionary
- quest/Objective.gd — Resource: type (kill/collect/talk/reach), target, count_required, count_current
- quest/QuestTrigger.gd — Area3D que inicia quest ao entrar
- quest/QuestMarker.gd — Node3D com Label3D flutuante e seta no HUD apontando para objetivo
- quest/RewardSystem.gd — distribui XP, items, gold, reputação ao completar
- quest/JournalUI.tscn — CanvasLayer com lista de quests, objetivos, mapa
- quest/WorldEvent.gd — eventos randômicos com timer: emboscada, comerciante, festival
""",

    "combat": _BASE_3D + """
MÓDULO: Combat / Sistema de Combate 3D
Gere o sistema de combate avançado:
- combat/CombatSystem.gd — gerencia combates, sequência, bloqueio, esquiva com i-frames
- combat/WeaponBase.gd — Resource base: damage, range, attack_speed, animation_name
- combat/MeleeWeapon.gd — extends WeaponBase: Area3D hitbox, combo counter, stagger
- combat/RangedWeapon.gd — extends WeaponBase: instancia Projectile, reload_time
- combat/HealthSystem.gd — Component Node: max_hp, current_hp, armor; sinais damaged, died
- combat/HitboxComponent.gd — Area3D com collision layers configurados, emite hit(damage, attacker)
- combat/DamageNumber.gd — Label3D que flutua para cima com Tween e some após 1s
- combat/StatusEffect.gd — Resource: type, duration, tick_damage; aplicado por CombatSystem
""",

    "ui": _BASE_3D + """
MÓDULO: UI / Interface 3D
Gere toda a interface do jogo:
- ui/HUD.tscn — CanvasLayer com: barra HP (TextureProgressBar), stamina, minimap placeholder, crosshair
- ui/Minimap.gd — SubViewport com Camera3D aérea, ícones de POI como Control nodes
- ui/Inventory.tscn — PopupPanel com GridContainer de slots, arrastar/soltar, tooltips
- ui/ShopUI.tscn — PopupPanel com lista de itens, preço, botão comprar/vender
- ui/DialogueUI.tscn — CanvasLayer com PanelContainer: portrait (TextureRect), nome, texto animado, botões de opção
- ui/PauseMenu.tscn — CanvasLayer com VBoxContainer: salvar, carregar, opções, sair
- ui/MapUI.tscn — CanvasLayer fullscreen com TextureRect (mapa), marcadores, zoom
- ui/QuestNotification.gd — AnimationPlayer mostra/esconde panel de notificação
- ui/LoadingScreen.tscn — CanvasLayer com ProgressBar e Label de dica
""",
}

# ── Módulos 2D ──────────────────────────────────────────────────────────────────

_MODULE_PROMPTS_2D = {
    "core": _BASE_2D + """
MÓDULO: Core / Fundação 2D
Gere os arquivos fundamentais para jogo 2D:
- project.godot — configurado para renderer Compatibility (2D), sem Vulkan:
    config/features=PackedStringArray("4.3", "GL Compatibility")
    rendering/renderer/rendering_method="gl_compatibility"
    display/window/size/viewport_width=640
    display/window/size/viewport_height=360
    display/window/stretch/mode="canvas_items"
    NÃO inclua run/main_scene
- autoload/GameManager.gd — singleton: estado global, cena atual, save/load
- autoload/EventBus.gd — sinais tipados para comunicação desacoplada
- autoload/AudioManager.gd — música, SFX, fade
- autoload/SaveSystem.gd — salva/carrega em JSON com FileAccess
""",

    "world": _BASE_2D + """
MÓDULO: World / Mundo 2D com TileMap
Gere o sistema de mundo 2D:
- world/TileWorld.tscn — cena raiz do mundo 2D. DEVE conter:
    [node name="TileWorld" type="Node2D"]
    [node name="ParallaxBackground" type="ParallaxBackground" parent="."]
    [node name="ParallaxLayer_Far" type="ParallaxLayer" parent="ParallaxBackground"]
      motion_scale = Vector2(0.1, 0.1)
    [node name="ParallaxLayer_Mid" type="ParallaxLayer" parent="ParallaxBackground"]
      motion_scale = Vector2(0.4, 0.4)
    [node name="TileMap" type="TileMap" parent="."]
    [node name="Camera2D" type="Camera2D" parent="."]
    [node name="WorldLight" type="DirectionalLight2D" parent="."]
      energy = 1.0
    script = ExtResource("TileWorldManager.gd")
- world/TileWorldManager.gd — controla câmera (segue jogador), zona de carregamento, dia/noite com CanvasModulate
- world/TileGenerator.gd — gera TileMap programaticamente com noise: cada bioma tem tile_id diferente
- world/ParallaxManager.gd — controla layers de parallax baseado em Camera2D.position
- world/PointOfInterest2D.gd — Area2D base para zonas especiais (cidade, dungeon)
- world/WeatherSystem2D.gd — CanvasModulate + GPUParticles2D para chuva/neve
""",

    "player": _BASE_2D + """
MÓDULO: Player / Jogador 2D
Gere o sistema completo do jogador 2D:
- player/Player.tscn — CharacterBody2D com:
    - Sprite2D (placeholder com região de sprite sheet)
    - CollisionShape2D (RectangleShape2D)
    - Camera2D (position_smoothing_enabled=true, zoom=Vector2(3,3))
    - Area2D (InteractionArea)
    - AnimationPlayer com animações: idle, walk_left, walk_right, jump, attack
    - add_to_group("player") no _ready()
- player/PlayerController.gd — movimento 2D: Arrow/WASD, pulo (Space), sprint
    Usa move_and_slide(); gravidade com ProjectSettings.get("physics/2d/default_gravity")
- player/PlayerAnimationController.gd — troca animações baseado em velocity e estado
- player/InteractionSystem2D.gd — Area2D overlap detecta NPCs/objetos, emite show_prompt
- player/InventorySystem.gd — mesma lógica do 3D (sem dependências de dimensão)
- player/StatsComponent.gd — HP, stamina, XP, level; emite sinais health_changed, level_up
""",

    "npc": _BASE_2D + """
MÓDULO: NPC / Personagens 2D
Gere o sistema de NPCs 2D:
- npc/NPC.tscn — CharacterBody2D com Sprite2D, AnimationPlayer, NavigationAgent2D, Area2D
- npc/NPCController.gd — estados: IDLE, PATROL, FOLLOW, ATTACK, TALK
    Usa NavigationAgent2D para pathfinding 2D
- npc/AIStateMachine.gd — máquina de estados genérica (reutilizável por qualquer NPC)
- npc/ScheduleSystem.gd — rotina diária por horário
- npc/FactionSystem.gd — relações facções, reputação do jogador
- npc/DialogueSystem.gd — carrega DialogueData, exibe via EventBus signal show_dialogue
- npc/MerchantComponent.gd — inventário de loja
- npc/EnemyController.gd — extends NPCController, AI de combate 2D com Raycast2D para linha de visão
""",

    "quest": _BASE_2D + """
MÓDULO: Quest / Sistema de Missões 2D
Gere o sistema completo de quests (independente de dimensão):
- quest/QuestManager.gd — autoload, rastreia quests ativas/completas/falhas
- quest/QuestData.gd — Resource: id, title, objectives: Array[Objective], rewards: Dictionary
- quest/Objective.gd — Resource: type, target, count_required, count_current
- quest/QuestTrigger2D.gd — Area2D que inicia quest ao entrar
- quest/QuestMarker2D.gd — Node2D com Label flutuante e seta no HUD
- quest/RewardSystem.gd — distribui XP, items, currency
- quest/JournalUI.tscn — CanvasLayer com lista de quests e objetivos
- quest/WorldEvent2D.gd — eventos randômicos com timer
""",

    "combat": _BASE_2D + """
MÓDULO: Combat / Sistema de Combate 2D
Gere o sistema de combate 2D:
- combat/CombatSystem.gd — gerencia combates, combo, bloqueio, knockback 2D
- combat/WeaponBase.gd — Resource base: damage, knockback, attack_animation
- combat/MeleeWeapon2D.gd — extends WeaponBase: Area2D hitbox, combo, stagger
- combat/Projectile2D.gd — RigidBody2D que voa e aplica dano ao colidir
- combat/HealthSystem.gd — Component: max_hp, current_hp; sinais damaged, died
- combat/HitboxComponent2D.gd — Area2D com layers de colisão, emite hit(damage, attacker)
- combat/DamageLabel.gd — Label que flutua para cima com Tween e some após 1s
- combat/StatusEffect.gd — Resource: poison, burn, slow com duração e tick
""",

    "ui": _BASE_2D + """
MÓDULO: UI / Interface 2D
Gere toda a interface do jogo 2D (CanvasLayer = já é 2D):
- ui/HUD.tscn — CanvasLayer com: barra HP (TextureProgressBar), stamina, moedas, notificações
- ui/Inventory.tscn — PopupPanel com GridContainer de slots, tooltips
- ui/ShopUI.tscn — PopupPanel com lista de itens e botões
- ui/DialogueUI.tscn — CanvasLayer com PanelContainer: portrait, nome, texto animado, opções
- ui/PauseMenu.tscn — CanvasLayer com VBoxContainer: salvar, carregar, opções, sair
- ui/MapUI.tscn — CanvasLayer com TextureRect (minimap), marcadores
- ui/QuestNotification.gd — AnimationPlayer mostra notificação de quest
- ui/LoadingScreen.tscn — CanvasLayer com ProgressBar e Label de dica
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
    dimension: str = "3d",
) -> dict[str, str]:
    """Gera todos os arquivos do projeto Godot em 7 módulos sequenciais."""
    prompts = _MODULE_PROMPTS_2D if dimension == "2d" else _MODULE_PROMPTS_3D
    all_files: dict[str, str] = {}

    # Contextos por módulo — cada um recebe apenas o subconjunto relevante
    module_contexts = {
        "core": {
            "name": gameplay_graph.get("name", "Kraft Game"),
            "genre": gameplay_graph.get("genre", ""),
            "dimension": dimension,
            "systems": gameplay_graph.get("systems", []),
        },
        "world": {
            "world_graph": world_graph or {},
            "scene_graph": scene_graph or {},
            "dimension": dimension,
        },
        "player": {
            "player": (character_graph or {}).get("player", {}),
            "mechanics": gameplay_graph.get("mechanics", []),
            "dimension": dimension,
        },
        "npc": {
            "npcs": (character_graph or {}).get("npcs", []),
            "factions": (character_graph or {}).get("factions", []),
            "dialogue_graph": dialogue_graph or {},
            "dimension": dimension,
        },
        "quest": {
            "quest_graph": quest_graph or {},
            "world_events": (world_graph or {}).get("world_events", []),
        },
        "combat": {
            "entities": gameplay_graph.get("entities", []),
            "mechanics": gameplay_graph.get("mechanics", []),
            "dimension": dimension,
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
                        {"role": "system", "content": prompts[module_name]},
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


# ── Cena principal mínima (fallback) ────────────────────────────────────────────

_MAIN_SCENE_3D = """\
[gd_scene load_steps=3 format=3]

[ext_resource type="PackedScene" path="res://world/WorldMap.tscn" id="1"]
[ext_resource type="PackedScene" path="res://player/Player.tscn" id="2"]

[node name="Main" type="Node3D"]

[node name="World" parent="." instance=ExtResource("1")]

[node name="Player" parent="." instance=ExtResource("2")]
position = Vector3(0, 2, 0)
"""

_MAIN_SCENE_2D = """\
[gd_scene load_steps=3 format=3]

[ext_resource type="PackedScene" path="res://world/TileWorld.tscn" id="1"]
[ext_resource type="PackedScene" path="res://player/Player.tscn" id="2"]

[node name="Main" type="Node2D"]

[node name="World" parent="." instance=ExtResource("1")]

[node name="Player" parent="." instance=ExtResource("2")]
position = Vector2(320, 180)
"""


def write_project_files(project_id: int, files: dict[str, str], dimension: str = "3d") -> Path:
    """Salva os arquivos gerados no diretório de trabalho."""
    project_dir = Path(settings.projects_workdir) / str(project_id) / "godot"
    project_dir.mkdir(parents=True, exist_ok=True)

    for relative_path, content in files.items():
        file_path = project_dir / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")

    _ensure_main_scene(project_dir, dimension)
    _patch_world_scene(project_dir, dimension)
    return project_dir


def _ensure_main_scene(project_dir: Path, dimension: str = "3d") -> None:
    """Garante main scene válida e run/main_scene no project.godot."""
    if dimension == "2d":
        candidates = ["main.tscn", "Main.tscn", "world/TileWorld.tscn", "player/Player.tscn"]
        fallback_content = _MAIN_SCENE_2D
    else:
        candidates = ["main.tscn", "Main.tscn", "world/WorldMap.tscn", "player/Player.tscn"]
        fallback_content = _MAIN_SCENE_3D

    main_scene = None
    for c in candidates:
        if (project_dir / c).exists():
            main_scene = c
            break

    if not main_scene:
        main_path = project_dir / "main.tscn"
        main_path.write_text(fallback_content, encoding="utf-8")
        main_scene = "main.tscn"

    project_cfg = project_dir / "project.godot"
    if project_cfg.exists():
        content = project_cfg.read_text(encoding="utf-8")
        lines = [ln for ln in content.splitlines() if "run/main_scene" not in ln]
        result = []
        for line in lines:
            result.append(line)
            if line.strip() == "[application]":
                result.append(f'run/main_scene="res://{main_scene}"')
        project_cfg.write_text("\n".join(result) + "\n", encoding="utf-8")
    else:
        renderer = "gl_compatibility" if dimension == "2d" else "forward_plus"
        project_cfg.write_text(
            f'config_version=5\n\n[application]\nrun/main_scene="res://{main_scene}"\n\n'
            f'[rendering]\nrenderer/rendering_method="{renderer}"\n',
            encoding="utf-8",
        )


def _patch_world_scene(project_dir: Path, dimension: str = "3d") -> None:
    """
    Garante que a cena do mundo 3D tem DirectionalLight3D.
    Fallback programático caso o GPT-4.1 tenha esquecido.
    """
    if dimension != "3d":
        return

    world_tscn = project_dir / "world" / "WorldMap.tscn"
    if not world_tscn.exists():
        return

    content = world_tscn.read_text(encoding="utf-8")
    if "DirectionalLight3D" in content:
        return  # já tem luz

    # Injeta nó de luz antes do último [node] ou no final
    light_node = (
        '\n[node name="Sun" type="DirectionalLight3D" parent="."]\n'
        'rotation_degrees = Vector3(-45, -30, 0)\n'
        'light_energy = 1.2\n'
        'shadow_enabled = true\n'
    )
    # Insere antes do último bloco de nó ou no final
    if "[node name=" in content:
        insert_pos = content.rfind("[node name=")
        content = content[:insert_pos] + light_node + "\n" + content[insert_pos:]
    else:
        content += light_node

    world_tscn.write_text(content, encoding="utf-8")
