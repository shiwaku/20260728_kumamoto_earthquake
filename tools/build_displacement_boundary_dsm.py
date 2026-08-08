#!/usr/bin/env python3
"""空中写真・数値表層モデル判読による変位境界（国土地理院）を、図から抜いて同梱する。

配信のかたち
------------
配信元は研究レポートのページで、成果物は **PDF と「位置情報付き図」の GeoTIFF だけ**。

    ページ: https://www.gsi.go.jp/chirijoho/chirijoho41073.html
    図:     https://gisstar.gsi.go.jp/R8kumamoto/Figures(GeoTIFF).zip

SAR判読の変位境界（10-2、`build_displacement_boundary.py`）と違い、
**ベクタでの配信が無い**。ZIP の中身は EPSG:3857 の RGBA GeoTIFF 4枚で、

    図1  変位境界の全体図（八代市〜御船町）        1331x1790  約22 m/px
    図2  右横ずれ量（氷川町〜宇城市）              1331x1790  約6 m/px
    図3  右横ずれ量（八代市）                      1332x1791  約6 m/px
    図4  縦ずれ量（八代市〜宇城市）                1332x1790  約9 m/px

いずれも地理院タイルの背景・地名・方位記号・スケールバー・凡例・インセット地図まで
入った「図」で、そのまま重ねると背景が二重になる。

そこで図1から**変位境界の赤線だけを色で抜き出し**、透過タイルに焼いて同梱する。
抜き出しは色の閾値と余白の矩形マスクだけの機械的な処理で、線の位置は配信図の
ジオリファレンスのまま動かさない。

なぜベクタ化しないのか
----------------------
赤マスクを細線化してポリラインに起こすこともできるが、

- 図1の線は南半分が実線・北半分が破線（推定区間）で、破線を繋ぐと
  配信元が引いていない連続性を足すことになる
- 線の太さは地上換算で約65m あり、中心線を1本に決める段階で解釈が入る

一方このデータは判読そのものが数10m の誤差を含む速報値なので、
約22 m/px のラスタのままの方が精度を偽らない。実線・破線の区別もそのまま残る。

余白のマスクについて
--------------------
方位記号（左上）とインセット地図（右下）は赤を含むので落とす。凡例は図1には無い。
矩形は図1の実測で、公表済みの静的な図なので固定値でよい。抜き終わったマスクに
帯の外の孤立画素が残っていないことは `--check` で確認できる。

使い方
------
    python3 tools/build_displacement_boundary_dsm.py              # 配信元から取得
    python3 tools/build_displacement_boundary_dsm.py --input figures.zip
    python3 tools/build_displacement_boundary_dsm.py --check      # 抜き出しの確認だけ
"""

from __future__ import annotations

import argparse
import io
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image

SOURCE_URL = "https://gisstar.gsi.go.jp/R8kumamoto/Figures(GeoTIFF).zip"
FIGURE = "図1(3857).tif"

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "viewer" / "public" / "data" / "henni_dsm"
RAW_SNAPSHOT = ROOT / "raw" / "gsi" / "displacement_boundary_dsm.zip"

# タイルのズーム範囲。図1は約22 m/px で、3857 の分解能では z13（19.1 m/px）が
# ほぼ等倍。これ以上焼いても情報は増えないので 13 で止め、拡大は MapLibre に任せる。
ZOOM_MIN, ZOOM_MAX = 9, 13

# 赤線の抽出条件。図の赤は (227,30,36) 前後。背景の地理院タイルにも
# 赤系（国道記号・注記）が出るが、彩度がこの閾値には届かない。
RED_MIN = 140
RED_MARGIN = 60

# 落とす余白（画像サイズに対する比）。(y0, y1, x0, x1)
MARGINALIA = (
    (0.78, 1.00, 0.70, 1.00),  # インセット地図（右下）
    (0.00, 0.09, 0.00, 0.14),  # 方位記号（左上）
)

# 抜いた線を塗り直す色。配信図の赤をそのまま使う。
# SAR判読の変位境界はマゼンタ（#ff2ec4）なので、2本を重ねても取り違えない。
LINE_RGB = (230, 32, 38)


def fetch(input_path: str | None, save_raw: bool) -> bytes:
    if input_path:
        print(f"入力: {input_path}")
        return Path(input_path).read_bytes()
    print(f"取得: {SOURCE_URL}")
    with urllib.request.urlopen(SOURCE_URL, timeout=300) as res:
        body = res.read()
    if save_raw:
        RAW_SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        RAW_SNAPSHOT.write_bytes(body)
        print(f"原本を保存: {RAW_SNAPSHOT.relative_to(ROOT)}")
    return body


def extract_figure(body: bytes, workdir: Path) -> Path:
    with zipfile.ZipFile(io.BytesIO(body)) as z:
        names = [n for n in z.namelist() if n.endswith(FIGURE)]
        if len(names) != 1:
            raise SystemExit(f"ZIP 内に {FIGURE} が1枚ではない: {names}")
        print(f"  ZIP 内: {names[0]}")
        out = workdir / "figure.tif"
        out.write_bytes(z.read(names[0]))
        return out


def build_mask(src: Path) -> tuple[np.ndarray, dict]:
    """赤線だけの真偽マスクと、元 GeoTIFF のプロファイルを返す。"""
    with rasterio.open(src) as ds:
        rgb = ds.read([1, 2, 3]).astype(np.int16)
        profile = ds.profile.copy()
    r, g, b = rgb[0], rgb[1], rgb[2]
    mask = (r > RED_MIN) & (r - g > RED_MARGIN) & (r - b > RED_MARGIN)

    h, w = mask.shape
    for y0, y1, x0, x1 in MARGINALIA:
        mask[int(h * y0) : int(h * y1), int(w * x0) : int(w * x1)] = False
    return mask, profile


def report(mask: np.ndarray) -> None:
    """帯の外に孤立画素が残っていないかを、行ごとの広がりで見る。"""
    ys, xs = np.nonzero(mask)
    print(f"  抽出画素: {mask.sum():,}（全体の {100 * mask.mean():.2f}%）")
    if not len(ys):
        raise SystemExit("赤が1画素も取れていない。閾値かマスクを疑う。")
    print(f"  画素範囲: x {xs.min()}-{xs.max()} / y {ys.min()}-{ys.max()}")
    # 変位境界は1本の帯なので、各行の赤は狭い範囲に固まるはず。
    widest = 0
    for y in np.unique(ys):
        row = xs[ys == y]
        widest = max(widest, int(row.max() - row.min()))
    print(f"  1行あたりの左右の広がり 最大 {widest}px（帯なので小さいほどよい）")


def write_rgba(mask: np.ndarray, profile: dict, out: Path) -> None:
    h, w = mask.shape
    rgba = np.zeros((4, h, w), np.uint8)
    for i, v in enumerate(LINE_RGB):
        rgba[i][mask] = v
    rgba[3][mask] = 255
    profile.update(count=4, dtype="uint8", compress="deflate", photometric="RGB", alpha="YES")
    profile.pop("nodata", None)
    with rasterio.open(out, "w", **profile) as ds:
        ds.write(rgba)
        ds.colorinterp = [
            rasterio.enums.ColorInterp.red,
            rasterio.enums.ColorInterp.green,
            rasterio.enums.ColorInterp.blue,
            rasterio.enums.ColorInterp.alpha,
        ]


def make_tiles(src: Path, out_dir: Path) -> None:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "gdal2tiles.py",
        "--xyz",
        "-z",
        f"{ZOOM_MIN}-{ZOOM_MAX}",
        "-r",
        "bilinear",
        "--processes",
        "4",
        "-w",
        "none",
        str(src),
        str(out_dir),
    ]
    print("  " + " ".join(cmd))
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)
    # gdal2tiles は完全透過のタイルも書くので、中身の無いものを落とす。
    # 焼いたタイルに座標は無いので、rasterio ではなく PIL で開く。
    removed = 0
    for png in out_dir.rglob("*.png"):
        with Image.open(png) as im:
            alpha = im.convert("RGBA").getchannel("A")
            if alpha.getextrema()[1] == 0:
                png.unlink()
                removed += 1
    for d in sorted(out_dir.rglob("*"), reverse=True):
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()
    kept = sum(1 for _ in out_dir.rglob("*.png"))
    total = sum(p.stat().st_size for p in out_dir.rglob("*.png"))
    print(f"  タイル {kept} 枚（完全透過の {removed} 枚を削除）／{total / 1024:.0f} KB")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--input", help="ローカルの ZIP を使う（省略時は配信元から取得）")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--save-raw", action="store_true", help="取得した原本を raw/gsi/ にも保存する")
    ap.add_argument("--check", action="store_true", help="抜き出しの確認だけしてタイルは焼かない")
    args = ap.parse_args()

    body = fetch(args.input, args.save_raw)
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        fig = extract_figure(body, tmpdir)
        mask, profile = build_mask(fig)
        report(mask)
        if args.check:
            return 0
        line = tmpdir / "line.tif"
        write_rgba(mask, profile, line)
        make_tiles(line, Path(args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
