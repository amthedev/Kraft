"""
Blender Fabricator — geração de assets 3D avançados com IA.

Gera via GPT-4.1 scripts Python completos para Blender 4.x (bpy API) que criam:
- Personagens com armature, rigging e ações de animação
- Ambientes procedurais (terreno, vegetação, edificações)
- Props e objetos interativos com UVs corretas
- Materiais PBR completos (Principled BSDF)
"""

import asyncio
import json
import tempfile
from pathlib import Path

import openai

from app.config import settings
from app.services.storage import upload_asset

BLENDER_SYSTEM = """Você é um especialista sênior em Blender 4.x Python API (bpy) para jogos AAA.
Gere scripts Python completos e funcionais usando APENAS bpy — sem importações externas.

REGRAS TÉCNICAS:
- Sempre comece limpando a cena: bpy.ops.object.select_all(action='SELECT') + bpy.ops.object.delete()
- Use bpy.data.objects, bpy.data.meshes, bpy.data.materials diretamente (mais robusto que ops)
- Para PBR materials: use nodes Principled BSDF com roughness, metallic, base_color corretos
- Exporte com: bpy.ops.export_scene.gltf(filepath='/tmp/kraft_output.glb', export_format='GLB')
- Para personagens COM RIGGING:
  * Crie Armature com bones hierárquicos (Root > Hips > Spine > Chest > Head; Hips > Thigh_L/R > Shin_L/R > Foot_L/R; Chest > UpperArm_L/R > Forearm_L/R > Hand_L/R)
  * Adicione vertex groups no mesh com mesmo nome dos bones
  * Crie pelo menos 3 actions: 'idle' (pose T), 'walk' (ciclo de 24 frames), 'attack' (swing de 12 frames)
  * Use bpy.ops.object.modifier_add(type='ARMATURE') para vincular armature ao mesh
- Para ambientes:
  * Use bmesh para geometria procedural (terreno com noise, árvores com particle system)
  * Adicione empties como spawn points, portals, trigger zones (com custom properties)
  * Use collections para organizar: "Environment", "Props", "Lights", "SpawnPoints"
- Para props interativos:
  * Marque o origin no centro de massa (bpy.ops.object.origin_set(type='ORIGIN_CENTER_OF_MASS'))
  * Adicione custom property 'interactable': True
  * Adicione collision shape simplificada como filho (Empty com escala de hitbox)

ESTILOS SUPORTADOS:
- 'realistic': alta poly, PBR completo, displacement maps
- 'low_poly': faceted shading (shade flat), cores flat sem textura, 500-2000 tris
- 'stylized': intermediário, silhueta expressiva, texturas hand-painted
- 'pixel_3d': voxel-like, cubic geometry, sem smooth shading

Retorne APENAS o código Python, sem markdown, sem explicações.
"""

ENVIRONMENT_SYSTEM = """Você é um artista técnico especializado em ambientes de mundo aberto para Blender 4.x.
Gere scripts Python bpy para criar ambientes massivos e detalhados.

REGRAS:
- Crie terreno usando bmesh + noise procedural
- Adicione biomas com vertex paint (cor por altitude/slope)
- Crie assets de vegetação modulares (árvore, arbusto, grama) como linked libraries
- Adicione pontos de interesse como Empties com custom properties
- Use particle systems para distribuição de vegetação
- Lighting: sun lamp para dia, HDRI para reflexos, point lights para interiores
- Exporte com bpy.ops.export_scene.gltf(filepath='/tmp/kraft_output.glb', export_format='GLB', export_lights=True)

Retorne APENAS o código Python, sem markdown.
"""


async def generate_blender_script(
    asset_description: str,
    asset_type: str = "prop",
    style: str = "low_poly",
) -> str:
    """Usa GPT-4.1 para gerar o script Python do Blender."""
    client = openai.AsyncOpenAI(api_key=settings.openai_api_key)

    # Escolhe prompt baseado no tipo de asset
    system = ENVIRONMENT_SYSTEM if asset_type in ("environment", "terrain", "region") else BLENDER_SYSTEM

    # Instrução específica por tipo
    type_hints = {
        "character": "INCLUA OBRIGATORIAMENTE: armature completo com hierarquia de bones, vertex groups, 3 actions (idle/walk/attack). Export com animations.",
        "vehicle": "INCLUA: chassis, rodas com rotação correta (origin no centro), suspensão como bones, LOD simple (export 2 meshes: high e low).",
        "building": "INCLUA: estrutura modular (paredes, teto, piso como objetos separados), portas/janelas como objetos filhos com custom prop 'door'/'window', interior vazio navegável.",
        "weapon": "INCLUA: malha detalhada, UVs corretas para texture painting, origin na empunhadura (grip point), socket point para attach na mão.",
        "environment": "INCLUA: terreno procedural com pelo menos 3 biomas via vertex color, 5 tipos de vegetação com particle systems, pontos de interesse como Empties.",
        "prop": "INCLUA: UVs limpas, origin centralizado, LOD mesh simplificada como filho, custom property 'physics': 'rigid_body'.",
    }

    hint = type_hints.get(asset_type, type_hints["prop"])

    user_msg = (
        f"Crie o seguinte asset 3D:\n"
        f"Descrição: {asset_description}\n"
        f"Tipo: {asset_type}\n"
        f"Estilo visual: {style}\n"
        f"Instrução especial: {hint}\n\n"
        f"Gere o script Python completo para Blender 4.x."
    )

    response = await client.chat.completions.create(
        model="gpt-4.1",
        max_tokens=8192,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ],
    )

    raw = response.choices[0].message.content or ""
    # Remove markdown se o modelo incluir mesmo com instrução
    if "```python" in raw:
        raw = raw.split("```python")[1].split("```")[0].strip()
    elif "```" in raw:
        raw = raw.split("```")[1].split("```")[0].strip()
    return raw


async def run_blender_script(script: str) -> bytes | None:
    """Executa o script no Blender headless e retorna o .glb gerado."""
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False, encoding="utf-8") as f:
        f.write(script)
        script_path = f.name

    output_path = "/tmp/kraft_output.glb"

    try:
        proc = await asyncio.create_subprocess_exec(
            settings.blender_binary,
            "--background",
            "--python", script_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=180)

        if proc.returncode != 0:
            raise RuntimeError(f"Blender error: {stderr.decode()}")

        glb_path = Path(output_path)
        if glb_path.exists():
            return glb_path.read_bytes()
        return None
    finally:
        Path(script_path).unlink(missing_ok=True)


async def fabricate_3d_asset(
    project_id: int,
    asset_name: str,
    description: str,
    asset_type: str = "prop",
    style: str = "low_poly",
) -> str | None:
    """Pipeline completo: gera script → executa Blender → salva → retorna URL."""
    script = await generate_blender_script(description, asset_type, style)
    glb_bytes = await run_blender_script(script)

    if not glb_bytes:
        return None

    key = f"projects/{project_id}/assets/models/{asset_name}.glb"
    url = await upload_asset(key, glb_bytes, content_type="model/gltf-binary")
    return url
