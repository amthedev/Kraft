"""
Build Runner — exporta o projeto Godot para Web usando Godot headless.

Fluxo:
1. Copia projeto gerado para diretório de trabalho
2. Executa: godot --headless --export-release "Web" <output>
3. Faz upload do build para storage
4. Retorna URL do build web
"""

import asyncio
import shutil
import zipfile
from pathlib import Path

from app.config import settings
from app.services.storage import upload_asset, _storage_configured

WEB_EXPORT_PRESET = """\
[preset.0]
name="Web"
platform="Web"
runnable=true
dedicated_server=false
custom_features=""
export_filter="all_resources"
include_filter=""
exclude_filter=""
export_path="./export/web/index.html"
patches=PackedStringArray()
mode=0
"""


def prepare_export_preset(project_dir: Path) -> None:
    """Cria export_presets.cfg para export Web."""
    preset_path = project_dir / "export_presets.cfg"
    preset_path.write_text(WEB_EXPORT_PRESET, encoding="utf-8")

    export_dir = project_dir / "export" / "web"
    export_dir.mkdir(parents=True, exist_ok=True)


async def run_godot_export(project_dir: Path) -> Path | None:
    """Executa Godot headless para exportar o projeto para Web."""
    prepare_export_preset(project_dir)
    export_path = project_dir / "export" / "web" / "index.html"

    proc = await asyncio.create_subprocess_exec(
        settings.godot_binary,
        "--headless",
        "--export-release", "Web",
        str(export_path),
        "--path", str(project_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(project_dir),
    )

    _, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)

    if proc.returncode != 0:
        raise RuntimeError(f"Godot export error: {stderr.decode()}")

    web_dir = project_dir / "export" / "web"
    if not export_path.exists():
        return None
    return web_dir


async def build_and_upload(project_id: int, build_id: int) -> tuple[str | None, str | None]:
    """
    Exporta o projeto para Web e ZIP, faz upload e retorna (web_url, zip_url).
    """
    project_dir = Path(settings.projects_workdir) / str(project_id) / "godot"

    if not project_dir.exists():
        raise FileNotFoundError(f"Projeto não encontrado em {project_dir}")

    # Export Web
    web_dir = await run_godot_export(project_dir)
    web_url = None
    if web_dir and web_dir.exists():
        for file in web_dir.rglob("*"):
            if file.is_file():
                key = f"builds/{project_id}/{build_id}/web/{file.relative_to(web_dir)}"
                content_type = _guess_content_type(file.suffix)
                local_or_remote = await upload_asset(key, file.read_bytes(), content_type=content_type)

        if _storage_configured():
            web_url = f"{settings.storage_public_url}/builds/{project_id}/{build_id}/web/index.html"
        else:
            web_url = f"/uploads/builds/{project_id}/{build_id}/web/index.html"

    # Export ZIP do projeto Godot
    zip_url = None
    zip_path = Path(settings.projects_workdir) / str(project_id) / f"project_{build_id}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in project_dir.rglob("*"):
            if file.is_file() and "export" not in str(file):
                zf.write(file, file.relative_to(project_dir))

    zip_bytes = zip_path.read_bytes()
    zip_key = f"builds/{project_id}/{build_id}/project.zip"
    await upload_asset(zip_key, zip_bytes, content_type="application/zip")

    if _storage_configured():
        zip_url = f"{settings.storage_public_url}/{zip_key}"
    else:
        zip_url = f"/uploads/{zip_key}"

    return web_url, zip_url


def _guess_content_type(suffix: str) -> str:
    types = {
        ".html": "text/html",
        ".js": "application/javascript",
        ".wasm": "application/wasm",
        ".pck": "application/octet-stream",
        ".png": "image/png",
        ".ico": "image/x-icon",
    }
    return types.get(suffix.lower(), "application/octet-stream")
