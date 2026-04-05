"""
Pixel Forge — pipeline completo de geração de pixel art com DALL-E 3.

Etapas:
1. GPT-4.1-mini planeja especificações (tamanho, frames, estilo, prompt)
2. DALL-E 3 gera imagem real de alta qualidade
3. Pillow pós-processa: redimensiona para pixel grid correto, converte RGBA
4. Para personagens: monta sprite sheet com múltiplos frames colados horizontalmente
5. Salva e retorna URL via storage
"""

import io
import json
from pathlib import Path

import httpx
import openai
from PIL import Image

from app.config import settings
from app.services.storage import upload_asset


PIXEL_SYSTEM = """Você é um diretor de arte especializado em pixel art para jogos AAA.
Você planeja assets visuais para jogos massivos com centenas de personagens e cenários.

A partir do art_bible e da descrição do asset, retorne JSON:
{
  "prompt": "<prompt ultra-detalhado para DALL-E 3 gerando pixel art>",
  "negative_prompt": "<o que evitar>",
  "dalle_size": "1024x1024",
  "pixel_size": "64x64",
  "frames": 4,
  "frame_labels": ["idle", "walk", "run", "attack"],
  "style": "16-bit SNES RPG",
  "palette_hint": "<paleta sugerida ex: earth tones, neon, pastel>",
  "layer": "character|sprite|tileset|background|ui|effect|icon|portrait"
}

Regras para o prompt DALL-E:
- Sempre mencione: pixel art, [style], isometric/side-view/top-down conforme o tipo
- Para personagens: inclua poses, roupas, armas, expressão, lighting
- Para tilesets: inclua padrão repetível, bordas, variações (grass tile, stone tile, water)
- Para backgrounds: inclua atmosfera, paralaxe, profundidade
- Seja extremamente específico: "16-bit pixel art, side-scrolling, knight warrior with silver armor..."
- dalle_size deve ser sempre 1024x1024 (DALL-E 3 só aceita quadrados ou 1792x1024)
- pixel_size: tamanho FINAL do sprite após resize (32x32, 48x48, 64x64, 128x128, 256x256)
- frames: número de frames da animação (1 para estáticos, 4-8 para personagens, 1 para tilesets)
"""


async def plan_pixel_asset(asset_description: str, art_bible: dict | None) -> dict:
    """Planeja especificações do asset com GPT-4.1-mini."""
    context = f"Art Bible: {json.dumps(art_bible or {})}\n\nAsset: {asset_description}"

    async with openai.AsyncOpenAI(api_key=settings.openai_api_key) as client:
        response = await client.chat.completions.create(
            model="gpt-4.1-mini",
            max_tokens=1024,
            messages=[
                {"role": "system", "content": PIXEL_SYSTEM},
                {"role": "user", "content": context},
            ],
            response_format={"type": "json_object"},
        )

    try:
        return json.loads(response.choices[0].message.content)
    except (json.JSONDecodeError, AttributeError):
        return {
            "prompt": asset_description,
            "dalle_size": "1024x1024",
            "pixel_size": "64x64",
            "frames": 1,
            "frame_labels": ["idle"],
            "style": "16-bit pixel art",
            "layer": "sprite",
        }


async def generate_pixel_image(prompt: str, size: str = "1024x1024") -> bytes | None:
    """Gera imagem real com DALL-E 3 e retorna bytes PNG."""
    # DALL-E 3 aceita: 1024x1024, 1792x1024, 1024x1792
    valid_sizes = {"1024x1024", "1792x1024", "1024x1792"}
    dall_e_size = size if size in valid_sizes else "1024x1024"

    async with openai.AsyncOpenAI(api_key=settings.openai_api_key) as client:
        response = await client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size=dall_e_size,
            quality="hd",
            style="vivid",
            n=1,
        )

    image_url = response.data[0].url
    async with httpx.AsyncClient(timeout=60) as http:
        r = await http.get(image_url)
        r.raise_for_status()
        return r.content


def resize_to_pixel_grid(image_bytes: bytes, pixel_size: str) -> bytes:
    """Redimensiona para o grid de pixel correto usando NEAREST (preserva pixels)."""
    try:
        w, h = (int(x) for x in pixel_size.split("x"))
    except (ValueError, AttributeError):
        w, h = 64, 64

    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    img = img.resize((w, h), Image.NEAREST)

    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def build_sprite_sheet(frames_bytes: list[bytes]) -> bytes:
    """Combina múltiplos frames em sprite sheet horizontal."""
    if not frames_bytes:
        return b""

    images = [Image.open(io.BytesIO(b)).convert("RGBA") for b in frames_bytes]
    w, h = images[0].size
    sheet = Image.new("RGBA", (w * len(images), h), (0, 0, 0, 0))

    for i, img in enumerate(images):
        sheet.paste(img, (i * w, 0))

    out = io.BytesIO()
    sheet.save(out, format="PNG")
    return out.getvalue()


async def generate_full_asset(
    project_id: int,
    asset_name: str,
    asset_description: str,
    art_bible: dict | None,
) -> tuple[str | None, dict]:
    """
    Pipeline completo:
    1. Planeja com GPT-4.1-mini
    2. Gera imagem(ns) com DALL-E 3
    3. Faz resize para pixel grid
    4. Monta sprite sheet se múltiplos frames
    5. Salva no storage
    Retorna (url, spec)
    """
    spec = await plan_pixel_asset(asset_description, art_bible)

    frames = spec.get("frames", 1)
    pixel_size = spec.get("pixel_size", "64x64")
    dalle_size = spec.get("dalle_size", "1024x1024")
    prompt = spec.get("prompt", asset_description)
    layer = spec.get("layer", "sprite")
    frame_labels = spec.get("frame_labels", [f"frame_{i}" for i in range(frames)])

    if frames <= 1:
        # Asset estático — 1 imagem
        raw_bytes = await generate_pixel_image(prompt, dalle_size)
        if not raw_bytes:
            return None, spec
        final_bytes = resize_to_pixel_grid(raw_bytes, pixel_size)
    else:
        # Sprite sheet — gera cada frame separado com descrição da pose
        frame_bytes_list = []
        for i, label in enumerate(frame_labels[:frames]):
            frame_prompt = f"{prompt} — animation frame: {label}, frame {i+1} of {frames}"
            raw = await generate_pixel_image(frame_prompt, dalle_size)
            if raw:
                frame_bytes_list.append(resize_to_pixel_grid(raw, pixel_size))

        if not frame_bytes_list:
            return None, spec

        if len(frame_bytes_list) == 1:
            final_bytes = frame_bytes_list[0]
        else:
            final_bytes = build_sprite_sheet(frame_bytes_list)

    key = f"projects/{project_id}/assets/{layer}s/{asset_name}.png"
    url = await upload_asset(key, final_bytes, content_type="image/png")
    return url, spec


# ── Funções legadas (mantidas para compatibilidade) ────────────────────────────

async def save_pixel_asset(project_id: int, asset_name: str, image_bytes: bytes) -> str:
    key = f"projects/{project_id}/assets/sprites/{asset_name}.png"
    return await upload_asset(key, image_bytes, content_type="image/png")


def normalize_sprite(image_bytes: bytes, width: int, height: int) -> bytes:
    return resize_to_pixel_grid(image_bytes, f"{width}x{height}")
