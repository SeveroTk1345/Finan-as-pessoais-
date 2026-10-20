"""Gera os ícones do PWA (preto e branco). Uso: python scripts/gerar_icones.py

Requer Pillow. Os PNGs gerados ficam versionados em frontend/public/icons.
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parents[1] / "frontend" / "public" / "icons"
SIZES = {"icon-192.png": 192, "icon-512.png": 512, "apple-touch-icon.png": 180, "maskable-512.png": 512}


def draw(size: int, maskable: bool) -> Image.Image:
    img = Image.new("RGB", (size, size), "#111111")
    d = ImageDraw.Draw(img)
    # Símbolo simples: "R$" branco centralizado; maskable deixa margem de segurança.
    scale = 0.36 if maskable else 0.46
    font = None
    for candidate in ["DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]:
        try:
            font = ImageFont.truetype(candidate, int(size * scale))
            break
        except OSError:
            continue
    font = font or ImageFont.load_default()
    text = "R$"
    box = d.textbbox((0, 0), text, font=font)
    w, h = box[2] - box[0], box[3] - box[1]
    d.text(((size - w) / 2 - box[0], (size - h) / 2 - box[1]), text, fill="#ffffff", font=font)
    return img


OUT.mkdir(parents=True, exist_ok=True)
for name, size in SIZES.items():
    draw(size, name.startswith("maskable")).save(OUT / name, optimize=True)
    print("gerado", name)
