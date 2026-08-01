#!/usr/bin/env python3
"""国土交通省「通れるマップ」の道路規制情報を同梱用の GeoJSON に整形する。

配信元
------
https://www.mlit.go.jp/road/saigai/r8kumamoto/index.html

ページには2系統のリンクがあり、**使えるのは日時別 ZIP だけ**。

- ❌ 「現時点データ一式」`road/saigai/**test**/map.zip`
      … 同梱の index.html のタイトルが「霞ヶ関での大雪　道路の被害状況マップ」で、
        別災害のテストデータ。規制309件は全国の事前通行規制・積雪・路面凍結（1〜2月）、
        ETC2.0 は首都圏（経度138.4〜139.7）で九州は0本。入れ子で 260123 / 260209 /
        260529 の大雪回の ZIP まで同梱されている。熊本地震のデータは1件も入っていない
- ✅ 日時別 `road/saigai/r8kumamoto/{YYMMDDHHMM}data.zip`
      … 7/29 8時〜7/31 8時の6本。規制開始日時・整理IDとも 2026年7月で、
        規制理由も落石・地震・道路損壊・橋梁損傷等。九州の外は0本

なお 7/31 16時（`2607311600data.zip`）はページ本文が「最新」と書いているのに 404。
命名の揺れではなく（6パターン試して全滅）先方の上げ忘れとみられるため、
既定は取得できる最新の 7/31 8時にしてある。

ZIP の中身（2607310800data.zip）
--------------------------------
- `json/dourokisei.geojson`      … 規制 55本
- `json/.geojson`                … 規制 29本。**ファイル名が拡張子だけ**（`img/.png` も同様）。
                                    cp932 で読み直しても基底名は空なので先方の作成ミス
- `json/ETC2.0_speed_data.geojson` … 47,065本・45.9MB
- `json/tukoujisseki.geojson`      … 通行実績 38,715本・33.6MB

規制が2ファイルに分裂しているが**幾何が完全一致する重複が20本**あるので単純結合は不可。
このスクリプトは幾何のハッシュで重複を除き、属性の多い側を残して **62本**にする。
ETC2.0 と通行実績は属性が `_color`/`_opacity`/`_weight` の3つだけで速度値も路線名も
持たないため、ここでは扱わない（載せるなら PMTiles 化が必要）。

配色を作り直している理由
------------------------
同梱の凡例画像（img/usage_guide.png）は

    規制中（被災）区間  赤   … 高速道路・直轄国道・補助国道・都道府県道等
    規制中（事前）区間  黒   … 高速道路（有料道路を含む）
                        灰   … 直轄国道・補助国道・都道府県道等
    規制解除後（被災区間のみ）薄灰

と、**status × 道路種別**で色を割り当てていると読める。しかし実データはこれに合わない。

- `#999999`（19本）は凡例では「事前」だが、規制理由は落石6・道路損壊4・地震2…で
  規制種別は全19本が「災害」。高速道路も4本混じる
- `#000000`（2本）も凡例では「事前」だが規制理由は「地震」

つまり配信側の色は凡例どおりの意味になっていない。そのまま使うと**誤った凡例**を
出すことになるので、色は捨てて `規制開始_内容`／`規制内容` から状態を導き直す。
こちらはデータ自身から検証できる（全面通行止47本・通行止め解除2本・属性なし13本）。

`#9900ff`（13本）は凡例に無い色で、属性が `_color`/`_opacity`/`_weight` だけの
実質空の地物。7時点すべてを取得して数えると、**7/31 8時にだけ現れる**（7/29 12時〜
7/30 16時には1本も無い）。九州自動車道・九州中央道や阿蘇〜大分方面の広域ルートを
なぞっており、7/31 に新設された区分と思われるが、属性が無いので断定できない。

配信元はこの13本を `_weight: 5`／`_opacity: 0.5`、つまり他の規制（`_weight: 10`／
`_opacity: 0.6〜1`）の半分の太さ・半分の濃さで描いていて、副次的な要素として
扱っている。ここでも消さずに残すが、意味を主張しないよう細い灰色で目立たなく描く
（消すと62→49本になり、配信元にある線が地図から失われてしまうため）。

`通行止め解除` を青にすると既定ONの「全国の主要活断層帯」（`#3388ff` の線）と
見分けがつかないので緑にしている。

そのほかの正規化
----------------
- `始点経度緯度`（1本だけ存在するキーの誤字。値は他と同じ緯度,経度の順）→ `始点緯度経度`
- 高速道路の5本は `始点`/`終点`/`規制内容`/`規制延長_Km`、県道等は `始点住所`/`終点住所`/
  `規制開始_内容`/`延長_Km` と、同じ意味で別キーになっているので片方へ寄せる
- `name`（整理ID）と `_dashArray` は表示に使わないので落とす
- `_weight` は 10/5（Leaflet 基準で太すぎる）、`_opacity` は 0.5〜1 とばらついているので
  一定値に揃える。不透明度はビューワのスライダーで操作する

使い方
------
    python3 tools/build_road_restriction.py                      # 7/31 8時を取得
    python3 tools/build_road_restriction.py --timestamp 2607301600
    python3 tools/build_road_restriction.py --input raw/mlit/2607310800data.zip
    python3 tools/build_road_restriction.py --save-raw
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

BASE_URL = "https://www.mlit.go.jp/road/saigai/r8kumamoto"
PAGE_URL = f"{BASE_URL}/index.html"
DEFAULT_TIMESTAMP = "2607310800"

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "viewer" / "public" / "data" / "mlit" / "road_restriction.geojson"
RAW_DIR = ROOT / "raw" / "mlit"

# ZIP 内の規制ファイル。`json/.geojson` は基底名が無いが実在する。
RESTRICTION_MEMBERS = ("json/dourokisei.geojson", "json/.geojson")

# 座標の丸め桁数。5桁 ≒ 1m。
NDIGITS = 5

# 状態の判定と描画。規制内容の文字列から導く。
# 配信元の _color / _weight / _opacity は凡例と整合しないため使わない（docstring 参照）。
CLOSED = "全面通行止め"
REOPENED = "通行止め解除"
UNKNOWN = "不明"
STATE_STYLE = {
    CLOSED: {"_color": "#e60012", "_weight": 5, "_opacity": 1},
    REOPENED: {"_color": "#00a040", "_weight": 5, "_opacity": 1},
    # 意味が特定できない13本。細く薄くして、読み取りを主張しない。
    UNKNOWN: {"_color": "#9e9e9e", "_weight": 3, "_opacity": 0.7},
}

# 表示に使う属性。この順序がそのままポップアップの行順（layers.ts の popup.rows と対応）。
OUT_PROPS = ("路線名", "道路種別", "状態", "規制理由", "区間", "規制開始", "延長", "場所")


def fetch(url: str) -> bytes:
    # UA と Referer が無いと 403/404 を返すことがある。
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0", "Referer": PAGE_URL},
    )
    with urllib.request.urlopen(req, timeout=180) as res:
        return res.read()


def round_coords(c: object) -> object:
    if isinstance(c, (int, float)):
        return round(c, NDIGITS)
    if isinstance(c, list):
        return [round_coords(x) for x in c]
    return c


def geom_key(feat: dict) -> str:
    """幾何のハッシュ。2ファイル間の重複判定に使う。"""
    coords = (feat.get("geometry") or {}).get("coordinates")
    return hashlib.md5(json.dumps(coords, separators=(",", ":")).encode()).hexdigest()


def filled(props: dict) -> int:
    """空でない属性の数。重複したときどちらを残すかの判断に使う。"""
    return sum(1 for v in props.values() if v not in (None, ""))


def first(props: dict, *keys: str) -> str:
    """同じ意味で別キーになっている属性を1つに寄せる。"""
    for k in keys:
        v = props.get(k)
        if v not in (None, ""):
            return str(v).strip()
    return ""


def state_of(props: dict) -> str:
    content = first(props, "規制開始_内容", "規制内容")
    if not content:
        return UNKNOWN
    if "解除" in content:
        return REOPENED
    # 「全面通行止」「全面通行止め」の表記揺れをまとめる。
    return CLOSED if "通行止" in content else content


def normalize(props: dict) -> dict:
    """配信元の属性を、表示に使う形へ組み直す。"""
    start = first(props, "始点住所", "始点")
    end = first(props, "終点住所", "終点")
    # 住所に改行が入っている地物がある。
    start, end = start.replace("\n", " "), end.replace("\n", " ")
    length = first(props, "延長_Km", "規制延長_Km")
    state = state_of(props)

    out: dict[str, str] = {
        "路線名": first(props, "路線名"),
        "道路種別": first(props, "道路種別"),
        "状態": state,
        "規制理由": first(props, "規制理由"),
        "区間": f"{start} → {end}" if start and end else start or end,
        "規制開始": first(props, "規制開始_日時"),
        # 誤字キー 始点経度緯度 もここで拾う（値の順序は他と同じ）。
        "延長": f"{length} km" if length and length not in ("0", "0.0") else "",
        "場所": first(props, "県名") + first(props, "市町村名"),
    }
    direction = first(props, "規制方向")
    if direction:
        out["状態"] = f"{state}（{direction}）"

    return {
        **{k: v for k, v in out.items() if v},
        **STATE_STYLE.get(state, STATE_STYLE[UNKNOWN]),
    }


def load_features(body: bytes) -> tuple[list[dict], dict[str, int]]:
    z = zipfile.ZipFile(io.BytesIO(body))
    names = {i.filename for i in z.infolist()}
    counts: dict[str, int] = {}
    feats: list[dict] = []
    for member in RESTRICTION_MEMBERS:
        if member not in names:
            print(f"  !! {member} が ZIP に無い（配信側の構成が変わった可能性）")
            continue
        fc = json.loads(z.read(member))
        got = fc.get("features", [])
        counts[member] = len(got)
        feats.extend(got)
    return feats, counts


def dedupe(feats: list[dict]) -> tuple[list[dict], int]:
    """幾何が同一の地物を、属性の多い側を残してまとめる。"""
    best: dict[str, dict] = {}
    dups = 0
    for f in feats:
        k = geom_key(f)
        if k in best:
            dups += 1
            if filled(f.get("properties") or {}) <= filled(best[k].get("properties") or {}):
                continue
        best[k] = f
    return list(best.values()), dups


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--input", help="ローカルの ZIP を使う（省略時は配信元から取得）")
    ap.add_argument(
        "--timestamp",
        default=DEFAULT_TIMESTAMP,
        help=f"取得する時点 YYMMDDHHMM（既定 {DEFAULT_TIMESTAMP} = 2026/7/31 8時）",
    )
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--save-raw", action="store_true", help="取得した ZIP を raw/mlit/ にも保存する")
    args = ap.parse_args()

    if args.input:
        src = Path(args.input)
        print(f"入力: {src}")
        body = src.read_bytes()
    else:
        url = f"{BASE_URL}/{args.timestamp}data.zip"
        print(f"取得: {url}")
        body = fetch(url)
        if args.save_raw:
            RAW_DIR.mkdir(parents=True, exist_ok=True)
            snapshot = RAW_DIR / f"{args.timestamp}data.zip"
            snapshot.write_bytes(body)
            print(f"原本を保存: {snapshot.relative_to(ROOT)}")

    feats, counts = load_features(body)
    for member, n in counts.items():
        print(f"  {member}: {n}本")
    if not feats:
        print("規制情報が取れなかった", file=sys.stderr)
        return 1

    feats, dups = dedupe(feats)
    print(f"重複（幾何が完全一致）を {dups}本 除去 → {len(feats)}本")

    states: dict[str, int] = {}
    kinds: dict[str, int] = {}
    for f in feats:
        props = f.get("properties") or {}
        f["properties"] = normalize(props)
        state = state_of(props)
        states[state] = states.get(state, 0) + 1
        g = f.get("geometry") or {}
        kinds[g.get("type", "?")] = kinds.get(g.get("type", "?"), 0) + 1
        if "coordinates" in g:
            g["coordinates"] = round_coords(g["coordinates"])

    fc = {"type": "FeatureCollection", "features": feats}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    compact = json.dumps(fc, ensure_ascii=False, separators=(",", ":"))
    out.write_text(compact, encoding="utf-8")

    print(f"幾何: {kinds}")
    print(f"状態: {states}")
    print(f"{out.relative_to(ROOT)}: {len(compact.encode('utf-8')):,} B")
    return 0


if __name__ == "__main__":
    sys.exit(main())
