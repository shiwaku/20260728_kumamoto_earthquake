#!/usr/bin/env python3
"""SAR判読による変位境界（国土地理院）の GeoJSON を、表示用に整えて同梱する。

なぜ取り込むのか
----------------
配信元は www.gsi.go.jp の ZIP（`/common/000279979.zip`）で、中身は GeoJSON 1本。
同じ内容が `/common/000279927.geojson` としても置かれているが、いずれも
**CORS ヘッダを返さない**ため、ブラウザから直接読むことはできない。
そのうえ www.gsi.go.jp は TLS の unsafe legacy renegotiation を要求するので、
新しい OpenSSL では既定の設定のまま繋がらない（下の LEGACY_CTX を参照）。

データの構造（実測）
--------------------
- 51地物すべて MultiLineString。うち **26地物は coordinates が空**で、
  地理院地図に載せると何も描かれない。判読作業の残骸とみられるので落とす。
- 残る25地物・25本・181点。総延長 42.8km（公表文の「約35km」は帯の長さで、
  こちらは枝分かれした線も足した実延長）。
- 属性は `id` だけ。**一意ではなく**（例: 23 は非空だけで6地物）、空の地物とも
  値を共有する。判読区間のまとまりを表す番号とみられるが、凡例の公表は無い。

色について
----------
配信データに描画属性は無い。国土地理院の公表図（図1〜3）は黒線だが、
本ビューワはダークテーマと空中写真も背景に取るため、どの背景でも沈まない
マゼンタ（#ff2ec4）に置き換えている。SAR干渉画像の bcyr 系配色（青→シアン→
黄→赤）には無い色相なので、重ねたときに縞と混ざらない。

使い方
------
    python3 tools/build_displacement_boundary.py                   # 配信元から取得
    python3 tools/build_displacement_boundary.py --input raw/gsi/xxx.geojson
"""

from __future__ import annotations

import argparse
import io
import json
import ssl
import sys
import urllib.request
import zipfile
from pathlib import Path

SOURCE_URL = "https://www.gsi.go.jp/common/000279979.zip"
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "viewer" / "public" / "data" / "gsi" / "displacement_boundary.geojson"
RAW_SNAPSHOT = ROOT / "raw" / "gsi" / "displacement_boundary.zip"

# 線の見た目。viewer 側は _color / _weight / _opacity をそのまま使う。
LINE_COLOR = "#ff2ec4"
LINE_WEIGHT = 3

# 座標の丸め桁数。判読位置そのものが数10〜100m の誤差を含むので5桁（約1m）で十分。
NDIGITS = 5

# www.gsi.go.jp は RFC 5746 非対応のため、既定の OpenSSL 3 では
# UNSAFE_LEGACY_RENEGOTIATION_DISABLED で接続できない。
LEGACY_CTX = ssl.create_default_context()
LEGACY_CTX.options |= getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0x4)


def round_coords(c: object) -> object:
    if isinstance(c, (int, float)):
        return round(c, NDIGITS)
    if isinstance(c, list):
        return [round_coords(x) for x in c]
    return c


def load_geojson(body: bytes) -> dict:
    """ZIP でも生の GeoJSON でも受ける。ZIP なら中の .geojson を1本取り出す。"""
    if body[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(body)) as z:
            names = [n for n in z.namelist() if n.lower().endswith(".geojson")]
            if len(names) != 1:
                raise SystemExit(f"ZIP 内の .geojson が1本ではない: {names}")
            print(f"  ZIP 内: {names[0]}")
            body = z.read(names[0])
    # 配信物は BOM 付き。
    return json.loads(body.decode("utf-8-sig"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", help="ローカルの ZIP か GeoJSON を使う（省略時は配信元から取得）")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--save-raw", action="store_true", help="取得した原本を raw/gsi/ にも保存する")
    args = ap.parse_args()

    if args.input:
        src = Path(args.input)
        print(f"入力: {src}")
        body = src.read_bytes()
    else:
        print(f"取得: {SOURCE_URL}")
        with urllib.request.urlopen(SOURCE_URL, timeout=120, context=LEGACY_CTX) as res:
            body = res.read()
        if args.save_raw:
            RAW_SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
            RAW_SNAPSHOT.write_bytes(body)
            print(f"原本を保存: {RAW_SNAPSHOT.relative_to(ROOT)}")

    d = load_geojson(body)
    feats = d.get("features", [])

    kept = []
    dropped = 0
    points = 0
    for f in feats:
        g = f.get("geometry") or {}
        coords = g.get("coordinates")
        if not coords:
            dropped += 1
            continue
        g["coordinates"] = round_coords(coords)
        points += sum(len(line) for line in g["coordinates"])
        props = f.get("properties") or {}
        f["properties"] = {
            "判読ID": props.get("id"),
            "_color": LINE_COLOR,
            "_weight": LINE_WEIGHT,
            "_opacity": 1,
        }
        kept.append(f)

    d["features"] = kept
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    compact = json.dumps(d, ensure_ascii=False, separators=(",", ":"))
    out.write_text(compact, encoding="utf-8")

    print(f"地物 {len(feats)} → {len(kept)}（座標が空の {dropped} 地物を除外）／{points} 点")
    print(f"{out.relative_to(ROOT)}: {len(compact.encode('utf-8')):,} B")
    return 0


if __name__ == "__main__":
    sys.exit(main())
