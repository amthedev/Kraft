"""
Pixel Forge — pipeline de geração de pixel art.

Dois modos:
1. PIXEL-A-PIXEL (2D): GPT-4.1 gera JSON com paleta + índices por pixel → Pillow monta PNG real
2. DALL-E (3D / UI): gera imagem 1024×1024, quantiza paleta para aparência pixel art

Fluxo principal: generate_full_asset(project_id, name, description, art_bible, dimension)
"""

import io
import json
from pathlib import Path

import httpx
import openai
from PIL import Image

from app.config import settings
from app.services.storage import upload_asset

# ── System prompts ──────────────────────────────────────────────────────────────

PIXEL_JSON_SYSTEM = """Você é um artista de pixel art especializado em jogos retro 2D.
Gere pixel art de alta qualidade em formato JSON estruturado.

FORMATO DE SAÍDA (JSON estrito):
{
  "width": <int: 16|32|48|64>,
  "height": <int: 16|32|48|64>,
  "palette": ["#RRGGBB", ...],  // max 32 cores, hex com #
  "frames": [
    {
      "label": "<nome da animação>",
      "pixels": [[<idx>, <idx>, ...], ...]  // array 2D: [linha][coluna], índice na palette
    }
  ]
}

REGRAS DE ARTE:
- Use paletas limitadas e coesas (16-32 cores max)
- Silhueta clara e reconhecível mesmo em baixa resolução
- Outline escuro para separar figura do fundo (pixel de cor escura na borda)
- Personagens: tamanho 32x32 ou 48x48, múltiplos frames (idle, walk, attack)
- Tilesets: 16x16 ou 32x32, 1 frame, padrão repetível sem borda óbvia
- Backgrounds: 64x64, 1 frame, com variação visual
- UI/ícones: 16x16 ou 32x32, 1 frame, leitura clara
- Cada frame DEVE ter exatamente width*height pixels (height linhas de width colunas)
- Índices devem ser válidos (0 a len(palette)-1)
"""

PIXEL_PLAN_SYSTEM = """Você é um diretor de arte de pixel art para jogos retro 2D.
A partir da descrição do asset e do art_bible, retorne JSON com especificações:
{
  "prompt_description": "<descrição detalhada do que o asset deve parecer>",
  "width": <16|32|48|64>,
  "height": <16|32|48|64>,
  "frame_labels": ["idle", "walk_1", "walk_2"],
  "palette_mood": "<descrição da paleta: ex 'tons terrosos quentes, medieval'>",
  "style_notes": "<notas de estilo: ex '16-bit SNES, outline preto, sombreamento flat'>",
  "layer": "character|sprite|tileset|background|ui|icon"
}
"""

DALLE_PIXEL_SYSTEM = """Você é um diretor de arte de pixel art.
A partir da descrição do asset e art_bible, retorne JSON com prompt para DALL-E 3:
{
  "prompt": "<prompt ultra-detalhado para DALL-E 3 gerando pixel art>",
  "dalle_size": "1024x1024",
  "pixel_size": "<WxH final ex: 64x64>",
  "frames": <int>,
  "frame_labels": ["idle", ...],
  "style": "<16-bit SNES RPG | 8-bit NES | 32-bit PSX>",
  "layer": "character|sprite|tileset|background|ui|icon"
}
"""


# ── Pipeline pixel-a-pixel (2D) ─────────────────────────────────────────────────

async def _plan_pixel_asset(description: str, art_bible: dict | None) -> dict:
    """Planeja especificações do asset (tamanho, frames, paleta, estilo)."""
    context = f"Art Bible: {json.dumps(art_bible or {})}\n\nAsset: {description}"
    async with openai.AsyncOpenAI(api_key=settings.openai_api_key) as client:
        resp = await client.chat.completions.create(
            model="gpt-4.1-mini",
            max_tokens=512,
            messages=[
                {"role": "system", "content": PIXEL_PLAN_SYSTEM},
                {"role": "user", "content": context},
            ],
            response_format={"type": "json_object"},
        )
    try:
        return json.loads(resp.choices[0].message.content)
    except Exception:
        return {"width": 32, "height": 32, "frame_labels": ["idle"], "layer": "sprite"}


async def generate_pixel_art_json(
    description: str,
    art_bible: dict | None,
    width: int,
    height: int,
    frame_labels: list[str],
    palette_mood: str = "",
    style_notes: str = "",
) -> dict | None:
    """Pede ao GPT-4.1 que gere pixel art completo pixel-a-pixel em JSON."""
    user_msg = (
        f"Crie pixel art para: {description}\n"
        f"Tamanho: {width}x{height} pixels\n"
        f"Frames: {frame_labels}\n"
        f"Paleta: {palette_mood}\n"
        f"Estilo: {style_notes}\n"
        f"Art Bible: {json.dumps(art_bible or {})}\n\n"
        f"Gere o JSON completo com paleta e todos os frames."
    )

    async with openai.AsyncOpenAI(api_key=settings.openai_api_key) as client:
        resp = await client.chat.completions.create(
            model="gpt-4.1",
            max_tokens=8192,
            messages=[
                {"role": "system", "content": PIXEL_JSON_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            response_format={"type": "json_object"},
        )

    try:
        data = json.loads(resp.choices[0].message.content)
        # Valida estrutura mínima
        if "palette" not in data or "frames" not in data:
            return None
        return data
    except Exception:
        return None


def _hex_to_rgba(hex_color: str) -> tuple[int, int, int, int]:
    h = hex_color.lstrip("#")
    if len(h) == 6:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return (r, g, b, 255)
    return (0, 0, 0, 255)


def render_pixel_art_from_json(data: dict) -> bytes | None:
    """Constrói PNG sprite sheet a partir do JSON pixel-a-pixel."""
    try:
        palette = [_hex_to_rgba(c) for c in data["palette"]]
        frames = data["frames"]
        w = int(data["width"])
        h = int(data["height"])
        n_frames = len(frames)

        # Sprite sheet: todos os frames lado a lado horizontalmente
        sheet = Image.new("RGBA", (w * n_frames, h), (0, 0, 0, 0))

        for fi, frame in enumerate(frames):
            frame_img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            rows = frame.get("pixels", [])
            for y, row in enumerate(rows[:h]):
                for x, idx in enumerate(row[:w]):
                    if isinstance(idx, int) and 0 <= idx < len(palette):
                        frame_img.putpixel((x, y), palette[idx])
            sheet.paste(frame_img, (fi * w, 0))

        out = io.BytesIO()
        sheet.save(out, format="PNG")
        return out.getvalue()
    except Exception:
        return None


# ── Pipeline DALL-E (3D / UI / fallback) ────────────────────────────────────────

async def _plan_dalle_asset(description: str, art_bible: dict | None) -> dict:
    context = f"Art Bible: {json.dumps(art_bible or {})}\n\nAsset: {description}"
    async with openai.AsyncOpenAI(api_key=settings.openai_api_key) as client:
        resp = await client.chat.completions.create(
            model="gpt-4.1-mini",
            max_tokens=1024,
            messages=[
                {"role": "system", "content": DALLE_PIXEL_SYSTEM},
                {"role": "user", "content": context},
            ],
            response_format={"type": "json_object"},
        )
    try:
        return json.loads(resp.choices[0].message.content)
    except Exception:
        return {
            "prompt": description,
            "dalle_size": "1024x1024",
            "pixel_size": "64x64",
            "frames": 1,
            "frame_labels": ["idle"],
            "style": "pixel art",
            "layer": "sprite",
        }


async def _generate_dalle_image(prompt: str, size: str = "1024x1024") -> bytes | None:
    valid_sizes = {"1024x1024", "1792x1024", "1024x1792"}
    dalle_size = size if size in valid_sizes else "1024x1024"

    async with openai.AsyncOpenAI(api_key=settings.openai_api_key) as client:
        resp = await client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size=dalle_size,
            quality="hd",
            style="vivid",
            n=1,
        )

    image_url = resp.data[0].url
    async with httpx.AsyncClient(timeout=60) as http:
        r = await http.get(image_url)
        r.raise_for_status()
        return r.content


def _pixelate_image(image_bytes: bytes, pixel_size: str, palette_colors: int = 32) -> bytes:
    """
    Converte imagem para pixel art via:
    1. Resize pequeno (destrava pixels grandes)
    2. Quantiza paleta (dithering Floyd-Steinberg)
    3. Resize final com NEAREST
    """
    try:
        w, h = (int(x) for x in pixel_size.split("x"))
    except (ValueError, AttributeError):
        w, h = 64, 64

    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")

    # Passo intermediário para evitar artefatos
    mid_scale = 4
    img_mid = img.resize((w * mid_scale, h * mid_scale), Image.LANCZOS)

    # Quantiza paleta para dar aparência pixel art (sem transparência no quantize)
    img_rgb = img_mid.convert("RGB")
    img_quantized = img_rgb.quantize(colors=palette_colors, dither=Image.Dither.FLOYDSTEINBERG)
    img_rgb_back = img_quantized.convert("RGB")

    # Resize final pixel art
    img_final = img_rgb_back.resize((w, h), Image.NEAREST)
    img_rgba = img_final.convert("RGBA")

    out = io.BytesIO()
    img_rgba.save(out, format="PNG")
    return out.getvalue()


# ── Entry point principal ────────────────────────────────────────────────────────

async def generate_full_asset(
    project_id: int,
    asset_name: str,
    asset_description: str,
    art_bible: dict | None = None,
    dimension: str = "3d",
) -> tuple[str | None, dict]:
    """
    Gera um asset visual completo e salva no storage.
    - dimension="2d": pipeline pixel-a-pixel via GPT-4.1 JSON
    - dimension="3d": pipeline DALL-E 3 + quantização de paleta
    Retorna (url, spec_dict).
    """
    if dimension == "2d":
        return await _generate_pixel_art_asset(project_id, asset_name, asset_description, art_bible)
    else:
        return await _generate_dalle_asset(project_id, asset_name, asset_description, art_bible)


async def _generate_pixel_art_asset(
    project_id: int,
    asset_name: str,
    asset_description: str,
    art_bible: dict | None,
) -> tuple[str | None, dict]:
    """Pipeline pixel-a-pixel GPT-4.1 para jogos 2D."""
    # 1. Planejar especificações
    spec = await _plan_pixel_asset(asset_description, art_bible)

    width = int(spec.get("width", 32))
    height = int(spec.get("height", 32))
    frame_labels = spec.get("frame_labels", ["idle"])
    palette_mood = spec.get("palette_mood", "")
    style_notes = spec.get("style_notes", "16-bit pixel art")
    layer = spec.get("layer", "sprite")

    # 2. Gerar pixel art via GPT-4.1
    pixel_data = await generate_pixel_art_json(
        asset_description, art_bible, width, height, frame_labels, palette_mood, style_notes
    )

    if pixel_data:
        png_bytes = render_pixel_art_from_json(pixel_data)
    else:
        png_bytes = None

    # 3. Fallback: DALL-E + pixelate se GPT falhou
    if not png_bytes:
        dalle_spec = await _plan_dalle_asset(asset_description, art_bible)
        dalle_prompt = f"pixel art, retro 2D game sprite, {asset_description}, {dalle_spec.get('style', '16-bit')}, transparent background, clear silhouette"
        raw_bytes = await _generate_dalle_image(dalle_prompt)
        if raw_bytes:
            png_bytes = _pixelate_image(raw_bytes, f"{width}x{height}")

    if not png_bytes:
        return None, spec

    # 4. Upload
    safe_name = asset_name.replace("/", "_").replace(" ", "_")
    key = f"projects/{project_id}/assets/{layer}s/{safe_name}.png"
    url = await upload_asset(key, png_bytes, content_type="image/png")

    return url, {**spec, "generated_by": "gpt-4.1-pixel", "frames": len(frame_labels), "pixel_size": f"{width}x{height}"}


async def _generate_dalle_asset(
    project_id: int,
    asset_name: str,
    asset_description: str,
    art_bible: dict | None,
) -> tuple[str | None, dict]:
    """Pipeline DALL-E 3 para jogos 3D (texturas, UI, portraits)."""
    spec = await _plan_dalle_asset(asset_description, art_bible)

    dalle_prompt = spec.get("prompt", asset_description)
    pixel_size = spec.get("pixel_size", "64x64")
    frame_labels = spec.get("frame_labels", ["idle"])
    layer = spec.get("layer", "sprite")
    n_frames = len(frame_labels)

    if n_frames <= 1:
        raw = await _generate_dalle_image(dalle_prompt)
        if not raw:
            return None, spec
        png_bytes = _pixelate_image(raw, pixel_size)
    else:
        # Gera frames separados e monta sprite sheet
        try:
            w, h = (int(x) for x in pixel_size.split("x"))
        except (ValueError, AttributeError):
            w, h = 64, 64

        sheet = Image.new("RGBA", (w * n_frames, h), (0, 0, 0, 0))
        for i, label in enumerate(frame_labels):
            frame_prompt = f"{dalle_prompt}, animation frame: {label}"
            raw = await _generate_dalle_image(frame_prompt)
            if raw:
                frame_bytes = _pixelate_image(raw, pixel_size)
                frame_img = Image.open(io.BytesIO(frame_bytes)).convert("RGBA")
                sheet.paste(frame_img, (i * w, 0))

        out = io.BytesIO()
        sheet.save(out, format="PNG")
        png_bytes = out.getvalue()

    safe_name = asset_name.replace("/", "_").replace(" ", "_")
    key = f"projects/{project_id}/assets/{layer}s/{safe_name}.png"
    url = await upload_asset(key, png_bytes, content_type="image/png")

    return url, {**spec, "generated_by": "dall-e-3", "frames": n_frames, "pixel_size": pixel_size}
