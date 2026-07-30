#!/usr/bin/env python3
"""ファビコン・アプリアイコンを生成する。

地図上の震央マーカー（赤い点＋白リング＋淡い赤のハロ）と同じモチーフにしている。
流用元プロジェクトのアイコンをそのまま置かないために用意したもので、
配色を変えたくなったら COLORS を触って再実行する。

    python3 tools/make_icons.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

OUT_DIR = Path(__file__).resolve().parent.parent / "viewer" / "public" / "icons"

DOT = (210, 0, 40, 255)
RING = (255, 255, 255, 245)
HALO = (210, 0, 40, 64)
PLATE = (255, 255, 255, 255)

# (ファイル名, 一辺px, 背景を白で塗るか)
# maskable と apple-touch は透過を扱えない/扱いが不揃いなので白地にする。
TARGETS = [
    ("favicon-32.png", 32, False),
    ("icon-192.png", 192, False),
    ("icon-512.png", 512, False),
    ("icon-maskable-512.png", 512, True),
    ("apple-touch-icon.png", 180, True),
]

# 描画は 8 倍で行ってから縮小し、縁を滑らかにする。
SS = 8


def draw_marker(size: int, plate: bool) -> Image.Image:
    n = size * SS
    im = Image.new("RGBA", (n, n), PLATE if plate else (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c = n / 2

    # maskable はセーフゾーン（中央80%）に収める必要があるため少し小さく描く
    scale = 0.68 if plate else 0.84
    r_halo = c * scale
    r_ring = r_halo * 0.62
    r_dot = r_halo * 0.44

    d.ellipse([c - r_halo, c - r_halo, c + r_halo, c + r_halo], fill=HALO)
    d.ellipse([c - r_ring, c - r_ring, c + r_ring, c + r_ring], fill=RING)
    d.ellipse([c - r_dot, c - r_dot, c + r_dot, c + r_dot], fill=DOT)

    return im.resize((size, size), Image.LANCZOS)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, size, plate in TARGETS:
        path = OUT_DIR / name
        draw_marker(size, plate).save(path)
        print(f"{path.relative_to(OUT_DIR.parent.parent.parent)}  {size}x{size}")


if __name__ == "__main__":
    main()
