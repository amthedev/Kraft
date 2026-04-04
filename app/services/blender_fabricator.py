"""
Blender Fabricator — gera modelos 3D usando Python API do Blender.

Fluxo:
1. Claude gera script Python para o Blender (usa bpy)
2. Script é executado em subprocess headless
3. Blender exporta .glb
4. Asset é salvo no storage
"""

import asyncio
import json
import subprocess
import tempfile
from pathlib import Path

import anthropic

from app.config import settings
from app.services.storage import upload_asset

BLENDER_SYSTEM = """Você é um especialista em Blender Python API (bpy).
Gere um script Python completo que:
1. Limpa a cena default do Blender
2. Cria o modelo 3D descrito
3. Aplica materiais básicos
4. Exporta para /tmp/kraft_output.glb

O modelo deve ser low-poly, adequado para jogos.
Use apenas bpy — não importe bibliotecas externas.
Retorne apenas o código Python, sem explicações.
"""


async def generate_blender_script(asset_description: str, style: str = "low-poly game asset") -> str:
    """Usa Claude para gerar o script Python do Blender."""
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    response = await client.messages.create(
        model="claude-opus-4-6",
        max_tokens=4096,
        system=BLENDER_SYSTEM,
        messages=[{"role": "user", "content": f"Crie: {asset_description}\nEstilo: {style}"}],
    )

    raw = response.content[0].text
    # Remove markdown se presente
    if "```python" in raw:
        raw = raw.split("```python")[1].split("```")[0].strip()
    elif "```" in raw:
        raw = raw.split("```")[1].split("```")[0].strip()
    return raw


async def run_blender_script(script: str) -> bytes | None:
    """Executa o script no Blender headless e retorna o .glb gerado."""
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
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
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)

        if proc.returncode != 0:
            raise RuntimeError(f"Blender error: {stderr.decode()}")

        glb_path = Path(output_path)
        if glb_path.exists():
            return glb_path.read_bytes()
        return None
    finally:
        Path(script_path).unlink(missing_ok=True)


async def fabricate_3d_asset(project_id: int, asset_name: str, description: str) -> str | None:
    """Pipeline completo: gera script → executa Blender → salva → retorna URL."""
    script = await generate_blender_script(description)
    glb_bytes = await run_blender_script(script)

    if not glb_bytes:
        return None

    key = f"projects/{project_id}/assets/models/{asset_name}.glb"
    url = await upload_asset(key, glb_bytes, content_type="model/gltf-binary")
    return url
