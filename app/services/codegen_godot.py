"""
Codegen Godot — gera GDScript e cenas .tscn a partir do IR do projeto.
"""

import json
import os
from pathlib import Path

import anthropic

from app.config import settings

CODEGEN_SYSTEM = """Você é um gerador de código Godot 4.
A partir do grafo de jogo fornecido, gere:
1. Todos os arquivos GDScript necessários (.gd)
2. Cenas principais (.tscn) com a estrutura de nós
3. Um project.godot configurado para export Web

Retorne um JSON no formato:
{
  "files": {
    "project.godot": "<conteúdo>",
    "main.tscn": "<conteúdo>",
    "scripts/player.gd": "<conteúdo>",
    ...
  }
}

Regras críticas:
- Use APENAS GDScript (sem C#)
- Godot 4 syntax (@onready, @export, etc.)
- Estrutura de nós compatível com export Web
- Todos os paths relativos ao root do projeto
"""


async def generate_godot_project(project_id: int, gameplay_graph: dict, scene_graph: dict | None) -> dict[str, str]:
    """Gera todos os arquivos do projeto Godot e retorna dict {path: conteúdo}."""
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    context = json.dumps(
        {"gameplay_graph": gameplay_graph, "scene_graph": scene_graph},
        ensure_ascii=False,
        indent=2,
    )

    response = await client.messages.create(
        model="claude-opus-4-6",
        max_tokens=8192,
        system=CODEGEN_SYSTEM,
        messages=[{"role": "user", "content": f"Gere o projeto Godot para:\n{context}"}],
    )

    raw = response.content[0].text
    try:
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        data = json.loads(raw)
        return data.get("files", {})
    except (json.JSONDecodeError, IndexError):
        return {}


def write_project_files(project_id: int, files: dict[str, str]) -> Path:
    """Salva os arquivos gerados no diretório de trabalho."""
    project_dir = Path(settings.projects_workdir) / str(project_id) / "godot"
    project_dir.mkdir(parents=True, exist_ok=True)

    for relative_path, content in files.items():
        file_path = project_dir / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")

    return project_dir
