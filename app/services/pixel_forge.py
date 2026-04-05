"""
Pixel Forge — pipeline de geração e refinamento de pixel art.

Etapas:
1. Extrai intenção visual do art_bible
2. Gera prompt otimizado para o modelo de imagem
3. Pós-processa: padroniza tamanho, paleta, transparência
4. Salva e retorna URL via storage
"""

import io
import json
from pathlib import Path

import httpx
import openai
from PIL import Image

from app.config import settings
from app.services.storage import upload_asset


PIXEL_SYSTEM = """Você é um especialista em pixel art para jogos.
A partir do art_bible e da descrição do asset, gere:
1. Um prompt detalhado para geração de pixel art (para Stable Diffusion / DALL-E)
2. Especificações técnicas do asset

Retorne JSON:
{
  "prompt": "<prompt otimizado>",
  "negative_prompt": "<negative prompt>",
  "width": 32,
  "height": 32,
  "frames": 1,
  "style": "16-bit RPG"
}
"""


async def plan_pixel_asset(asset_description: str, art_bible: dict | None) -> dict:
    """Usa OpenAI para planejar o asset antes de gerar."""
    client = openai.AsyncOpenAI(api_key=settings.openai_api_key)

    context = f"Art Bible: {json.dumps(art_bible or {})}\n\nAsset: {asset_description}"

    response = await client.chat.completions.create(
        model="gpt-4.1-mini",
        max_tokens=1024,
        messages=[
            {"role": "system", "content": PIXEL_SYSTEM},
            {"role": "user", "content": context},
        ],
    )

    raw = response.choices[0].message.content
    try:
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        return json.loads(raw)
    except (json.JSONDecodeError, IndexError):
        return {"prompt": asset_description, "width": 32, "height": 32, "frames": 1}


def normalize_sprite(image_bytes: bytes, width: int, height: int) -> bytes:
    """Normaliza sprite: redimensiona, converte para RGBA, garante transparência."""
    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    img = img.resize((width, height), Image.NEAREST)  # NEAREST preserva pixels

    output = io.BytesIO()
    img.save(output, format="PNG")
    return output.getvalue()


async def save_pixel_asset(project_id: int, asset_name: str, image_bytes: bytes) -> str:
    """Salva asset normalizado e retorna URL pública."""
    key = f"projects/{project_id}/assets/sprites/{asset_name}.png"
    url = await upload_asset(key, image_bytes, content_type="image/png")
    return url
