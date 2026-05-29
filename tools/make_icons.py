"""Generate the PWA / iOS home-screen icons for 생두 레이더.

A green-coffee radar mark: a coffee bean at the center of a radar sweep,
on a deep coffee-green field. Renders one 1024px master, then downsamples.

Run:  python tools/make_icons.py   ->   web/icons/*.png
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "web" / "icons"
S = 1024
CX, CY = S // 2, int(S * 0.46)

GREEN_TOP = (21, 81, 47)
GREEN_BOT = (8, 36, 22)
ACCENT = (78, 194, 122)
BEAN = (222, 238, 214)
BEAN_EDGE = (150, 196, 156)
CREASE = (47, 110, 70)


def vertical_gradient(size, top, bot):
    img = Image.new("RGB", (size, size), top)
    px = img.load()
    for y in range(size):
        t = y / (size - 1)
        r = round(top[0] + (bot[0] - top[0]) * t)
        g = round(top[1] + (bot[1] - top[1]) * t)
        b = round(top[2] + (bot[2] - top[2]) * t)
        for x in range(size):
            px[x, y] = (r, g, b)
    return img


def draw_master() -> Image.Image:
    base = vertical_gradient(S, GREEN_TOP, GREEN_BOT).convert("RGBA")
    overlay = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)

    # radar rings
    for radius, alpha in ((392, 70), (288, 90), (184, 110)):
        d.ellipse(
            [CX - radius, CY - radius, CX + radius, CY + radius],
            outline=ACCENT + (alpha,), width=7,
        )

    # radar sweep wedge (fades along the angle)
    sweep = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    sd = ImageDraw.Draw(sweep)
    start, end = -78, -18
    steps = 26
    for i in range(steps):
        a0 = start + (end - start) * i / steps
        a1 = start + (end - start) * (i + 1) / steps
        alpha = int(120 * (i / steps))  # brighter toward the leading edge
        sd.pieslice([CX - 392, CY - 392, CX + 392, CY + 392], a1, a0 + 0.6,
                    fill=ACCENT + (alpha,))
    overlay = Image.alpha_composite(overlay, sweep)
    d = ImageDraw.Draw(overlay)
    # leading edge line
    lead = math.radians(-18)
    d.line([CX, CY, CX + 392 * math.cos(lead), CY + 392 * math.sin(lead)],
           fill=ACCENT + (200,), width=8)

    base = Image.alpha_composite(base, overlay)

    # coffee bean on its own layer, then rotate
    bw, bh = 360, 520
    bean = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
    bd = ImageDraw.Draw(bean)
    bd.ellipse([10, 10, bw - 10, bh - 10], fill=BEAN, outline=BEAN_EDGE, width=10)
    # center crease: a soft S-curve down the long axis
    pts = []
    for i in range(0, 101):
        t = i / 100
        y = 60 + (bh - 120) * t
        x = bw / 2 + 46 * math.sin(t * math.pi * 2 - math.pi / 2)
        pts.append((x, y))
    bd.line(pts, fill=CREASE, width=16, joint="curve")

    bean = bean.rotate(33, expand=True, resample=Image.BICUBIC)
    bx = CX - bean.width // 2
    by = CY - bean.height // 2
    base.alpha_composite(bean, (bx, by))

    return base


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    master = draw_master()

    # maskable: same art but inset into a safe zone (content within ~80%)
    maskable = Image.new("RGBA", (S, S), GREEN_BOT + (255,))
    scaled = master.resize((int(S * 0.78), int(S * 0.78)), Image.LANCZOS)
    off = (S - scaled.width) // 2
    maskable.alpha_composite(scaled, (off, off))

    targets = {
        "icon-512.png": master.resize((512, 512), Image.LANCZOS),
        "icon-192.png": master.resize((192, 192), Image.LANCZOS),
        "apple-touch-icon.png": master.resize((180, 180), Image.LANCZOS),
        "icon-maskable-512.png": maskable.resize((512, 512), Image.LANCZOS),
    }
    for name, img in targets.items():
        img.convert("RGBA").save(OUT / name)
        print("wrote", OUT / name)


if __name__ == "__main__":
    main()
