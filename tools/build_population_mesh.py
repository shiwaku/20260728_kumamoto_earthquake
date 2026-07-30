#!/usr/bin/env python3
"""国勢調査2020 125mメッシュの夜間人口を、震災地域に切り出して PMTiles にする。

入力
----
`japan-mobility-ease-diagnosis` の食料品アクセス分析で作った
`output/food_desert_125m.parquet`（全国 2,814,032 メッシュ）。
`mesh_code` / `pop_total` / `pop_65over` / `pop_75over` / `geometry`(WKB) を持つ。

なぜ作り直すのか
----------------
同じデータから作られた全国版 PMTiles（`output/food_desert_125m.pmtiles`）は
**311MB** ある。GitHub は1ファイル100MBが上限なのでそのままは載せられない。
また食料品店までの距離（`dist_*`）という本件に無関係な高エントロピー属性が
入っており、これがタイルサイズを大きくしている。
そこで人口3項目だけに絞り、揺れた範囲へ切り出して作り直す。

出力
----
`viewer/public/data/census/pop_mesh125.pmtiles`
レイヤー名 `pop_mesh`、属性 `pop`（総人口）/ `pop65` / `pop75`。

低ズームでは 125m メッシュが1画素未満になるため、tippecanoe の
`--coalesce-densest-as-needed` で隣接メッシュを統合し、
`--accumulate-attribute` で人口を合算させている（統合後も合計人口が保たれる）。

使い方
------
    python3 tools/build_population_mesh.py
    python3 tools/build_population_mesh.py --bbox 129.8 31.5 131.6 33.5
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SRC = (
    ROOT.parent / "japan-mobility-ease-diagnosis" / "output" / "food_desert_125m.parquet"
)
DEFAULT_OUT = ROOT / "viewer" / "public" / "data" / "census" / "pop_mesh125.pmtiles"

# 既定の切り出し範囲。推計震度5弱以上が及んだ九州中北部を覆う。
DEFAULT_BBOX = (129.5, 31.0, 132.0, 33.8)

MINZOOM, MAXZOOM = 9, 14


def primary_mesh_prefixes(bbox: tuple[float, float, float, float]) -> set[str]:
    """bbox に掛かる1次地域メッシュコード（4桁）。

    1次メッシュは上2桁が floor(緯度 × 1.5)、下2桁が floor(経度) - 100。
    parquet 全体を走る前の粗いふるいとして使う。
    """
    w, s, e, n = bbox
    lat = range(int(s * 1.5), int(n * 1.5) + 1)
    lon = range(int(w) - 100, int(e) - 100 + 1)
    return {f"{a:02d}{b:02d}" for a in lat for b in lon}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", default=str(DEFAULT_SRC))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--bbox", nargs=4, type=float, metavar=("W", "S", "E", "N"), default=list(DEFAULT_BBOX))
    ap.add_argument("--keep-geojson", action="store_true", help="中間の GeoJSONSeq を残す")
    args = ap.parse_args()

    import pyarrow.parquet as pq
    import shapely

    src = Path(args.src)
    if not src.exists():
        print(f"入力が見つからない: {src}", file=sys.stderr)
        return 1
    bbox = (args.bbox[0], args.bbox[1], args.bbox[2], args.bbox[3])
    prefixes = primary_mesh_prefixes(bbox)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    tmp = Path(tempfile.mkdtemp(prefix="popmesh-")) / "pop_mesh125.geojsonseq"
    print(f"入力: {src}")
    print(f"範囲: {bbox}  1次メッシュ {len(prefixes)}区画")

    total = kept = 0
    pop_sum = p65_sum = p75_sum = 0
    pf = pq.ParquetFile(src)
    cols = ["mesh_code", "pop_total", "pop_65over", "pop_75over", "geometry"]
    with tmp.open("w", encoding="utf-8") as fh:
        for batch in pf.iter_batches(batch_size=200_000, columns=cols):
            total += batch.num_rows
            mc = batch.column("mesh_code").to_pylist()
            idx = [i for i, c in enumerate(mc) if c[:4] in prefixes]
            if not idx:
                continue
            wkb = batch.column("geometry").to_pylist()
            pt = batch.column("pop_total").to_pylist()
            p65 = batch.column("pop_65over").to_pylist()
            p75 = batch.column("pop_75over").to_pylist()
            geoms = shapely.from_wkb([wkb[i] for i in idx])
            bounds = shapely.bounds(geoms)
            for j, i in enumerate(idx):
                x0, y0, x1, y1 = bounds[j]
                if x1 < bbox[0] or x0 > bbox[2] or y1 < bbox[1] or y0 > bbox[3]:
                    continue
                # 125m メッシュは軸に平行な矩形なので、外周をそのまま書き出す。
                ring = [[round(x, 6), round(y, 6)] for x, y in geoms[j].exterior.coords]
                feat = {
                    "type": "Feature",
                    "properties": {"pop": pt[i], "pop65": p65[i], "pop75": p75[i]},
                    "geometry": {"type": "Polygon", "coordinates": [ring]},
                }
                fh.write(json.dumps(feat, separators=(",", ":")) + "\n")
                kept += 1
                pop_sum += pt[i]
                p65_sum += p65[i]
                p75_sum += p75[i]
            if total % 1_000_000 == 0:
                print(f"  走査 {total:,} / 抽出 {kept:,}")

    print(f"抽出: {kept:,} / {total:,} メッシュ")
    print(f"  総人口 {pop_sum:,} 人 ／ 65歳以上 {p65_sum:,} 人 ／ 75歳以上 {p75_sum:,} 人")
    print(f"中間ファイル: {tmp} ({tmp.stat().st_size:,} B)")

    cmd = [
        "tippecanoe",
        "-Z", str(MINZOOM),
        "-z", str(MAXZOOM),
        "-l", "pop_mesh",
        "-n", "国勢調査2020 125mメッシュ 夜間人口（令和8年熊本地震 対象域）",
        # 低ズームでメッシュが1画素未満になる分は統合し、人口は合算して保つ。
        "--coalesce-densest-as-needed",
        "--accumulate-attribute=pop:sum",
        "--accumulate-attribute=pop65:sum",
        "--accumulate-attribute=pop75:sum",
        "--force", "-P",
        "-o", str(out),
        str(tmp),
    ]
    print("\n" + " ".join(cmd))
    r = subprocess.run(cmd)
    if r.returncode != 0:
        return r.returncode

    print(f"\n{out.relative_to(ROOT)}: {out.stat().st_size:,} B")
    if not args.keep_geojson:
        tmp.unlink(missing_ok=True)
        tmp.parent.rmdir()
    return 0


if __name__ == "__main__":
    sys.exit(main())
