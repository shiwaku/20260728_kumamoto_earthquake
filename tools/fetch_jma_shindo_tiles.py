#!/usr/bin/env python3
"""気象庁の推計震度分布図（250mメッシュ）を静的な XYZ タイルとして取り込む。

配信のかたち
------------
気象庁は推計震度分布図を、**1次地域メッシュごとの PNG 画像**として配信している。

    索引: https://www.jma.go.jp/bosai/estimated_intensity_map/data/list.json
    画像: https://www.jma.go.jp/bosai/estimated_intensity_map/data/<url>/<1次メッシュ4桁>.png

索引の各要素が1つの地震に対応し、`url`（例 `202607281627_741`）と、
画像が存在する1次メッシュの一覧 `mesh_num`、範囲 `bounds`、
震度階級ごとのメッシュ数 `rank_cnt` を持つ。
PNG は1枚 800×800px で、1次メッシュ（緯度2/3度 × 経度1度）を覆う。

`Access-Control-Allow-Origin: *` が付くのでブラウザから直接読むこともできるが、

- MapLibre の image ソースは4隅をメルカトル平面上で線形に張るため、
  緯度2/3度ぶんの緯度方向の歪み（100m前後）が出る
- 17枚を17個のソースとして並べる形になり、レイヤー定義が煩雑になる

ので、GDAL で正しく再投影してタイルに焼き、他のレイヤーと同じ raster として扱う。

描かれている震度
----------------
画像は**震度4以上だけ**を塗っている（実測: 震度1〜3の公式色は1画素も含まれない）。
索引の `rank_cnt` には震度0〜3のメッシュ数も入っているが、画像には出てこない。
弱い揺れまで面で見たい場合はこのデータでは足りない。

使い方
------
    python3 tools/fetch_jma_shindo_tiles.py                       # 既定イベント
    python3 tools/fetch_jma_shindo_tiles.py --event 202607281627_741
    python3 tools/fetch_jma_shindo_tiles.py --list                # 索引から候補を表示
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://www.jma.go.jp/bosai/estimated_intensity_map/data"
LIST_URL = f"{BASE}/list.json"

# 令和8年熊本地震の本震: 2026-07-28 16:27 熊本県熊本地方 M7.1 最大震度7
DEFAULT_EVENT = "202607281627_741"

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "viewer" / "public" / "data" / "jma_shindo"

ZOOM_MIN, ZOOM_MAX = 5, 11

# 配信 PNG に焼かれている気象庁の震度階級色（実測）。震度4以上しか塗られていない。
JMA_CLASS_COLORS: dict[str, str] = {
    "震度4": "#fae696",
    "震度5弱": "#ffe600",
    "震度5強": "#ff9900",
    "震度6弱": "#ff2800",
    "震度6強": "#a50021",
    "震度7": "#b40068",
}

# 防災科研 J-RISQ の推計震度配色（GetLegendGraphic の実物から採色）のうち、
# 気象庁の図にある震度4以上に対応する分。
JRISQ_CLASS_COLORS: dict[str, str] = {
    "震度4": "#1e973d",
    "震度5弱": "#96d050",
    "震度5強": "#f7f618",
    "震度6弱": "#faaa46",
    "震度6強": "#f45178",
    "震度7": "#950d05",
}

PALETTES = {"jma": JMA_CLASS_COLORS, "jrisq": JRISQ_CLASS_COLORS}


def _rgb(hex_: str) -> tuple[int, int, int]:
    return tuple(int(hex_[i : i + 2], 16) for i in (1, 3, 5))  # type: ignore[return-value]


def recolor(img, palette: str):
    """階級色を別のパレットへ置き換える。

    配信 PNG は境界がアンチエイリアスされていて中間色を数百種持つため、
    完全一致の置換では縁だけ元の色が残る。各画素を気象庁の階級色のうち
    最も近いものへ割り当ててから置き換える（＝再分類）。
    アンチエイリアスはこれで失われるが、階級図としてはそのほうが正しい。
    """
    import numpy as np

    # 距離は int32 で計算する。int16 だと 255^2 × 3 = 195,075 が上限 32,767 を超えて
    # 巻き上がり、最近傍がでたらめになる（実際にそれで階級の分布が逆転した）。
    src = np.array([_rgb(h) for h in JMA_CLASS_COLORS.values()], dtype=np.int32)
    dst = np.array([_rgb(PALETTES[palette][k]) for k in JMA_CLASS_COLORS], dtype=np.uint8)

    a = np.array(img, dtype=np.uint8)
    rgb = a[:, :, :3].astype(np.int32)
    alpha = a[:, :, 3]
    # 各画素と6階級色の距離 → 最近傍の添字
    d = ((rgb[:, :, None, :] - src[None, None, :, :]) ** 2).sum(axis=3)
    idx = d.argmin(axis=2)
    out = np.dstack([dst[idx], alpha])
    # 透明画素は色を持たせない（縁に色が滲まないように）
    out[alpha == 0] = 0
    from PIL import Image

    return Image.fromarray(out, mode="RGBA")


def primary_mesh_bounds(code: str) -> tuple[float, float, float, float]:
    """1次地域メッシュコード（4桁）の範囲 (西, 南, 東, 北)。

    上2桁が緯度×1.5、下2桁が経度-100。1区画は緯度2/3度 × 経度1度。
    """
    lat = int(code[:2]) / 1.5
    lon = 100 + int(code[2:])
    return lon, lat, lon + 1.0, lat + 2.0 / 3.0


def fetch(url: str, dest: Path) -> None:
    with urllib.request.urlopen(url, timeout=120) as res:
        dest.write_bytes(res.read())


def load_index() -> list[dict]:
    with urllib.request.urlopen(LIST_URL, timeout=60) as res:
        return json.loads(res.read())


def run(cmd: list[str]) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(" ".join(cmd), file=sys.stderr)
        print(r.stdout[-2000:], file=sys.stderr)
        print(r.stderr[-2000:], file=sys.stderr)
        raise SystemExit(f"失敗: {cmd[0]}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--event", default=DEFAULT_EVENT, help="索引の url フィールドの値")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--list", action="store_true", help="索引から震度5弱以上の地震を並べて終了")
    ap.add_argument("--keep-work", action="store_true", help="中間ファイルを残す")
    ap.add_argument(
        "--palette",
        choices=sorted(PALETTES),
        default="jrisq",
        help="震度階級の配色。jma=気象庁のまま / jrisq=防災科研 J-RISQ の配色に置き換える（既定）",
    )
    args = ap.parse_args()

    index = load_index()

    if args.list:
        print(f"{'url':<20} {'発生時刻':<20} {'M':>4} {'最大計測震度':>7}  震央")
        for e in index:
            h = e.get("hypo", {})
            if (h.get("maxi") or 0) < 4.5:
                continue
            print(f"{e.get('url',''):<20} {h.get('at',''):<20} {h.get('mag',''):>4} {h.get('maxi',''):>7}  {h.get('epi','')}")
        return 0

    ev = next((e for e in index if e.get("url") == args.event), None)
    if ev is None:
        print(f"索引に {args.event} が無い（--list で確認できる）", file=sys.stderr)
        return 1

    hypo = ev.get("hypo", {})
    meshes: list[str] = ev.get("mesh_num", [])
    print(f"対象: {args.event}")
    print(f"  {hypo.get('at')} {hypo.get('epi')} M{hypo.get('mag')} 最大計測震度 {hypo.get('maxi')}")
    print(f"  1次メッシュ {len(meshes)}区画  範囲 {ev.get('bounds')}")
    print(f"  配色: {args.palette}" + ("（気象庁のまま）" if args.palette == "jma" else "（防災科研 J-RISQ の配色へ再分類）"))

    out = Path(args.out)
    if out.exists():
        shutil.rmtree(out)
    out.parent.mkdir(parents=True, exist_ok=True)

    from PIL import Image

    work = Path(tempfile.mkdtemp(prefix="jma-shindo-"))
    tifs: list[Path] = []
    for m in meshes:
        png = work / f"{m}.png"
        fetch(f"{BASE}/{args.event}/{m}.png", png)
        # 配信 PNG は 8bit パレットと 16bit RGBA が混在している。
        # そのまま VRT にまとめると band 構成が揃わず gdal2tiles が受け付けないので、
        # まず 8bit RGBA に正規化する。
        rgba = work / f"{m}_rgba.png"
        with Image.open(png) as im:
            mode = im.mode
            norm = im.convert("RGBA")
            if args.palette != "jma":
                norm = recolor(norm, args.palette)
            norm.save(rgba)
        w, s, e, n = primary_mesh_bounds(m)
        tif = work / f"{m}.tif"
        # 測地情報を与える。-a_ullr は左上→右下の順。
        run([
            "gdal_translate", "-q",
            "-a_srs", "EPSG:4326",
            "-a_ullr", str(w), str(n), str(e), str(s),
            str(rgba), str(tif),
        ])
        tifs.append(tif)
        print(f"  {m}: {png.stat().st_size:>9,} B ({mode})  → 経度 {w}〜{e} / 緯度 {s:.4f}〜{n:.4f}")

    vrt = work / "mosaic.vrt"
    run(["gdalbuildvrt", "-q", str(vrt), *[str(t) for t in tifs]])

    # 震度の階級色をぼかさないよう最近傍で縮小する（平均だと凡例に無い中間色が出る）
    print(f"\ngdal2tiles z{ZOOM_MIN}-{ZOOM_MAX} …")
    run([
        "gdal2tiles.py", "-q",
        "--xyz",
        "-z", f"{ZOOM_MIN}-{ZOOM_MAX}",
        "-r", "near",
        "-w", "none",
        str(vrt), str(out),
    ])

    pngs = sorted(out.rglob("*.png"))
    total = sum(p.stat().st_size for p in pngs)
    zooms = sorted({int(p.parent.parent.name) for p in pngs})
    print(f"完了: {len(pngs):,} タイル / {total:,} B  ズーム {zooms}")

    meta = {
        "source": "気象庁 推計震度分布図（250mメッシュ）",
        "source_url": "https://www.jma.go.jp/bosai/map.html",
        "index_url": LIST_URL,
        "event": args.event,
        "hypo": hypo,
        "mesh_num": meshes,
        "bounds": ev.get("bounds"),
        "rank_cnt": ev.get("rank_cnt"),
        "palette": args.palette,
        "palette_colors": PALETTES[args.palette],
        "note": (
            "1次メッシュごとの800×800px PNG を GDAL で再投影してタイル化したもの。"
            "画像は震度4以上だけを塗っており、震度1〜3は rank_cnt にはあるが描かれない。"
            + (
                ""
                if args.palette == "jma"
                else "配色は各画素を気象庁の階級色の最近傍へ再分類してから"
                "防災科研 J-RISQ の配色に置き換えている（値は気象庁のまま）。"
            )
        ),
        "zoom": [ZOOM_MIN, ZOOM_MAX],
        "tiles": len(pngs),
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (out / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"metadata: {(out / 'metadata.json').relative_to(ROOT)}")

    if not args.keep_work:
        shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
