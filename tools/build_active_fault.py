#!/usr/bin/env python3
"""全国の主要活断層帯（地震調査研究推進本部）の GeoJSON を圧縮して同梱用に書き出す。

なぜ取り込むのか
----------------
配信元 `https://maps.gsi.go.jp/xyz/active_fault/2/3/1.geojson` は
Access-Control-Allow-Origin: * を返すので、他の地理院レイヤーと同じく実行時に
直接参照することもできる。ただしこのファイルは整形済み（インデント付き）で
**2.36MB あり、しかも配信側が gzip を返さない**ため、レイヤーを ON にするたび
2.36MB を素で転送することになる。

そこで座標を5桁（約1m）に丸めた compact JSON にして同梱する。
GitHub Pages は静的ファイルに gzip/brotli を掛けるので、実転送量は大きく下がる。
災害時に配信元が重い・落ちている場合でも表示できる、という利点もある。

データの構造（実測）
--------------------
- LineString 3,085本 … 断層線本体。`_color: #3388ff` / `_weight: 3` / `_opacity: 1`
- Polygon    163面   … 断層帯の名称を持つ**不可視**の領域。
                       `_opacity: 0` / `_fillOpacity: 0` で、地理院地図では
                       クリックして名称を出すための当たり判定として使われている。
                       `name`（135種）と `description`（55種）はこちらにしか無い。

使い方
------
    python3 tools/build_active_fault.py                    # 配信元から取得
    python3 tools/build_active_fault.py --input raw/gsi/active_fault_jishinhonbu.geojson
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

SOURCE_URL = "https://maps.gsi.go.jp/xyz/active_fault/2/3/1.geojson"
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "viewer" / "public" / "data" / "herp" / "active_fault.geojson"
RAW_SNAPSHOT = ROOT / "raw" / "gsi" / "active_fault_jishinhonbu.geojson"

# 描画とポップアップに実際に使う属性だけ残す。
KEEP_PROPS = ("_color", "_opacity", "_weight", "_fillColor", "_fillOpacity", "name", "description")

# 座標の丸め桁数。5桁 ≒ 1m で、全国規模の断層線には十分。
NDIGITS = 5


def round_coords(c: object) -> object:
    if isinstance(c, (int, float)):
        return round(c, NDIGITS)
    if isinstance(c, list):
        return [round_coords(x) for x in c]
    return c


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", help="ローカルの GeoJSON を使う（省略時は配信元から取得）")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--save-raw", action="store_true", help="取得した原本を raw/gsi/ にも保存する")
    args = ap.parse_args()

    if args.input:
        src = Path(args.input)
        print(f"入力: {src}")
        body = src.read_bytes()
    else:
        print(f"取得: {SOURCE_URL}")
        with urllib.request.urlopen(SOURCE_URL, timeout=120) as res:
            body = res.read()
        if args.save_raw:
            RAW_SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
            RAW_SNAPSHOT.write_bytes(body)
            print(f"原本を保存: {RAW_SNAPSHOT.relative_to(ROOT)}")

    d = json.loads(body)
    feats = d.get("features", [])

    kinds: dict[str, int] = {}
    named = 0
    for f in feats:
        g = f.get("geometry") or {}
        kinds[g.get("type", "?")] = kinds.get(g.get("type", "?"), 0) + 1
        props = f.get("properties") or {}
        if props.get("name"):
            named += 1
        f["properties"] = {k: v for k, v in props.items() if k in KEEP_PROPS and v is not None}
        if "coordinates" in g:
            g["coordinates"] = round_coords(g["coordinates"])

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    compact = json.dumps(d, ensure_ascii=False, separators=(",", ":"))
    out.write_text(compact, encoding="utf-8")

    before = len(body)
    after = len(compact.encode("utf-8"))
    print(f"地物 {len(feats):,}（{kinds}）／名称あり {named}")
    print(f"{out.relative_to(ROOT)}: {before:,} B → {after:,} B（{after / before:.0%}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
