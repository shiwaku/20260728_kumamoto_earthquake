#!/usr/bin/env python3
"""防災科研 J-RISQ の推計震度分布（WMS）を静的な XYZ タイルとして取り込む。

なぜ取り込むのか
----------------
J-RISQ の WMS は EPSG:3857 と https に対応しており、MapLibre の
`{bbox-epsg-3857}` 方式（https://maplibre.org/maplibre-gl-js/docs/examples/add-a-wms-source/）
でそのまま raster ソースにできる。しかしレスポンスに Access-Control-Allow-Origin が
無いため、GitHub Pages のような別オリジンからはブラウザに遮断される
（実測: 90リクエスト全失敗 / net::ERR_FAILED）。
そこで、対象レポートは確定済みのスナップショットであることを利用して、
あらかじめタイルに焼いてリポジトリへ同梱する。

ズーム計画
----------
推定震度1以上の範囲は 128.6-138.5E / 29.5-37.2N と広い（実測）。
ズームごとに範囲を変えると、高ズームで範囲外が空白に落ちる（ラスタタイルの 404 は
親タイルへフォールバックしない）ため、全域を単一の範囲・単一のズーム帯で焼く。
上限は z11。z11 は 1px ≒ 64m（北緯33度）で 250m メッシュを十分に解像でき、
それ以上は MapLibre のオーバーズームに任せられる。
空タイル（全透明）は書き出さないので、実際の枚数は計画枚数の3割程度になる。

使い方
------
    python3 tools/fetch_jrisq_tiles.py
    python3 tools/fetch_jrisq_tiles.py --triggerid R-... --report 0145 --ana 00001
"""

from __future__ import annotations

import argparse
import io
import json
import math
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

WMS_ENDPOINT = "https://www.j-risq.bosai.go.jp/report/wms"
WMS_LAYER = "GSI_M250"

# 既定の対象レポート: 2026/07/28 16:40:13 発表（Ver.8 最終報）
DEFAULT_REPORT = {"triggerid": "R-20260728162724", "report": "0145", "ana": "00001"}

# (最小ズーム, 最大ズーム, (西, 南, 東, 北))
# bbox は推定震度1以上の実測範囲（128.580-138.460E / 29.464-37.155N）に少し余裕を持たせた値。
ZOOM_PLAN = [
    (5, 11, (128.5, 29.4, 138.6, 37.3)),
]

R = 20037508.342789244
TILE = 256


def lonlat_to_merc(lon: float, lat: float) -> tuple[float, float]:
    x = lon * R / 180.0
    y = math.log(math.tan((90.0 + lat) * math.pi / 360.0)) / (math.pi / 180.0) * R / 180.0
    return x, y


def tile_x(lon: float, z: int) -> int:
    return int((lon + 180.0) / 360.0 * (2**z))


def tile_y(lat: float, z: int) -> int:
    return int((1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * (2**z))


def tile_bbox_3857(x: int, y: int, z: int) -> tuple[float, float, float, float]:
    """XYZ タイルの EPSG:3857 での bbox（西, 南, 東, 北）。"""
    span = 2 * R / (2**z)
    west = -R + x * span
    north = R - y * span
    return west, north - span, west + span, north


def wms_url(x: int, y: int, z: int, report: dict[str, str]) -> str:
    w, s, e, n = tile_bbox_3857(x, y, z)
    q = {
        "service": "WMS",
        "version": "1.1.1",
        "request": "GetMap",
        "layers": WMS_LAYER,
        "srs": "EPSG:3857",
        "bbox": f"{w},{s},{e},{n}",
        "width": str(TILE),
        "height": str(TILE),
        "transparent": "true",
        "format": "image/png",
        **report,
    }
    return f"{WMS_ENDPOINT}?{urllib.parse.urlencode(q)}"


def planned_tiles() -> list[tuple[int, int, int]]:
    out: list[tuple[int, int, int]] = []
    for zmin, zmax, (w, s, e, n) in ZOOM_PLAN:
        for z in range(zmin, zmax + 1):
            for x in range(tile_x(w, z), tile_x(e, z) + 1):
                for y in range(tile_y(n, z), tile_y(s, z) + 1):
                    out.append((z, x, y))
    return out


def is_blank(png: bytes) -> bool:
    """全透明なら True。Pillow が無い環境では小さいPNGを空とみなす。"""
    try:
        from PIL import Image
    except ImportError:
        return len(png) < 400
    with Image.open(io.BytesIO(png)) as im:
        alpha = im.convert("RGBA").getchannel("A")
        return alpha.getextrema()[1] == 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--triggerid", default=DEFAULT_REPORT["triggerid"])
    ap.add_argument("--report", default=DEFAULT_REPORT["report"])
    ap.add_argument("--ana", default=DEFAULT_REPORT["ana"])
    ap.add_argument("--workers", type=int, default=6, help="並列数（相手はサーバなので控えめに）")
    ap.add_argument(
        "--out",
        default=str(Path(__file__).resolve().parent.parent / "viewer" / "public" / "data" / "jrisq" / WMS_LAYER),
    )
    ap.add_argument("--force", action="store_true", help="既存タイルも取り直す")
    args = ap.parse_args()

    report = {"triggerid": args.triggerid, "report": args.report, "ana": args.ana}
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    tiles = planned_tiles()
    print(f"対象タイル: {len(tiles):,} 枚  →  {out_dir}")

    lock = Lock()
    stats = {"written": 0, "blank": 0, "skipped": 0, "error": 0}
    zooms_written: set[int] = set()

    def fetch(t: tuple[int, int, int]) -> None:
        z, x, y = t
        path = out_dir / str(z) / str(x) / f"{y}.png"
        if path.exists() and not args.force:
            with lock:
                stats["skipped"] += 1
            return
        url = wms_url(x, y, z, report)
        for attempt in range(3):
            try:
                with urllib.request.urlopen(url, timeout=60) as res:
                    body = res.read()
                break
            except Exception:
                if attempt == 2:
                    with lock:
                        stats["error"] += 1
                    return
                time.sleep(1.5 * (attempt + 1))
        if is_blank(body):
            with lock:
                stats["blank"] += 1
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        with lock:
            stats["written"] += 1
            zooms_written.add(z)
            done = stats["written"] + stats["blank"] + stats["skipped"] + stats["error"]
            if done % 200 == 0:
                print(f"  {done:,}/{len(tiles):,}  書出={stats['written']:,} 空={stats['blank']:,}")

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(fetch, tiles))

    print(
        f"完了: 書出={stats['written']:,} 空={stats['blank']:,} "
        f"既存={stats['skipped']:,} 失敗={stats['error']:,}"
    )

    meta = {
        "source": "防災科学技術研究所 J-RISQ地震速報",
        "source_url": "https://www.j-risq.bosai.go.jp/",
        "wms_endpoint": WMS_ENDPOINT,
        "wms_layer": WMS_LAYER,
        "report": report,
        "note": (
            "J-RISQ の WMS は CORS ヘッダーを返さないため、GitHub Pages から直接は読めない。"
            "確定済みレポートのスナップショットとしてタイル化して同梱している。"
        ),
        "zoom_plan": [{"minzoom": a, "maxzoom": b, "bbox": list(c)} for a, b, c in ZOOM_PLAN],
        "zooms_written": sorted(zooms_written),
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tiles_written": stats["written"],
    }
    (out_dir.parent / "metadata.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"metadata: {out_dir.parent / 'metadata.json'}")
    return 1 if stats["error"] else 0


if __name__ == "__main__":
    sys.exit(main())
