#!/usr/bin/env python3
"""国土地理院の令和8年熊本地震ページを定期巡回し、データの更新・追加を検知する。

なぜ必要か
----------
配信元の `BOUSAI/20260728_kumamoto_earthquake.html` は更新のたびに節が書き換わり、
新しい地理院地図タイル（空中写真・斜面崩壊・干渉画像など）が静かに増える。
`Last-Modified` ヘッダは返ってこないので、内容を構造化して取り込み、
前回のスナップショットと比べる以外に更新を知る方法が無い。

何を見ているか
--------------
1. **提供情報一覧の日付表記** — 「９．斜面崩壊・堆積分布データ（７月３０日公表、８月６日更新）」
   の括弧の中。節ごとの公表・更新日がそのまま書かれているので、最も素直な更新シグナル。
2. **地理院地図のタイルID** — 本文の `maps.gsi.go.jp/#...&ls=std%7C<ID>&...&lcd=<ID>`
   から抜く。ビューワが読むタイルの実体そのものなので、ここが増えたら新レイヤー追加の合図。
   さらに `viewer/src/layers.ts` を突き合わせて「ビューワ未収録」を明示する。
3. **配信ファイル** — zip / geojson / pdf / kml / csv / tif へのリンク。
4. **本文テキスト** — 節ごとに行単位で保存する。ハッシュだけだと「変わった」しか分からないが、
   テキストを持てばスナップショットの `git diff` がそのまま差分レポートになる。
5. **リンク先の下位ページ** — 干渉解析・変位境界・震源断層モデルなど、実データは
   リンク先に置かれている。本文中の gsi.go.jp の .html リンクを自動で辿るので、
   新しい下位ページが増えても監視対象に勝手に入る（巡回リストの手入れが要らない）。

TLS について
------------
www.gsi.go.jp は TLS の unsafe legacy renegotiation を要求する。新しい OpenSSL では
既定設定のまま繋がらない（curl は `error:0A000152` で落ちる）ので、
`tools/build_displacement_boundary.py` と同じ `OP_LEGACY_SERVER_CONNECT` を立てる。

使い方
------
    python3 tools/watch_gsi.py                     # 取得して差分だけ表示（スナップショットは触らない）
    python3 tools/watch_gsi.py --update            # 差分を表示し、スナップショットを書き換える
    python3 tools/watch_gsi.py --report report.md  # 差分を Markdown ファイルにも書く
    python3 tools/watch_gsi.py --github-output "$GITHUB_OUTPUT"   # changed / summary を Actions に渡す

終了コードは常に 0（更新の有無は `--github-output` の `changed` で判定する）。
取得に失敗したときだけ 1 を返す。
"""

from __future__ import annotations

import argparse
import html as htmllib
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

REPO = Path(__file__).resolve().parent.parent
SNAPSHOT = REPO / "watch" / "gsi_snapshot.json"
LAYERS_TS = REPO / "viewer" / "src" / "layers.ts"

ROOT_URL = "https://www.gsi.go.jp/BOUSAI/20260728_kumamoto_earthquake.html"

# 本文中の .html リンクは自動で辿るが、どのページにも貼ってある定型リンクは除く。
FOLLOW_DENY = {
    "https://www.gsi.go.jp/kikakuchousei/kikakuchousei40182.html",  # コンテンツ利用規約
    "https://www.gsi.go.jp/ENGLISH/page_e30030.html",  # English version
}

UA = "Mozilla/5.0 (compatible; kumamoto-eq-viewer watcher; +https://github.com/shiwaku/20260728_kumamoto_earthquake)"

LEGACY_CTX = ssl.create_default_context()
# OpenSSL 3 は unsafe legacy renegotiation を既定で拒否する。www.gsi.go.jp はそれを要求する。
LEGACY_CTX.options |= getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0x4)

DATA_EXT = ("zip", "geojson", "pdf", "kml", "kmz", "csv", "tif", "tiff", "json", "xlsx")

BLOCK_TAGS = (
    "br",
    "p",
    "div",
    "li",
    "tr",
    "td",
    "th",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "table",
    "dt",
    "dd",
    "hr",
)

FULLWIDTH_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")


# ---------------------------------------------------------------- 取得


def fetch(url: str, *, retries: int = 3) -> str:
    """ページを取る。gsi.go.jp は時々詰まるので数回粘る。"""
    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60, context=LEGACY_CTX) as res:
                raw = res.read()
            break
        except (urllib.error.URLError, TimeoutError, OSError) as e:  # noqa: PERF203
            last = e
            if attempt == retries - 1:
                raise
            time.sleep(2 * (attempt + 1))
    else:  # pragma: no cover - break で必ず抜ける
        raise RuntimeError(str(last))

    charset = "utf-8"
    m = re.search(rb'charset=["\']?([\w-]+)', raw[:4096], re.I)
    if m:
        charset = m.group(1).decode("ascii", "ignore")
    return raw.decode(charset, "replace")


# ---------------------------------------------------------------- HTML の下処理


def main_region(page: str) -> str:
    """`<div id="main">` から `<div id="footer">` までを切り出す。

    ヘッダ・ドロワーナビ・フッタは全ページ共通の定型で、しかもサイト改修で
    まとめて変わる。混ぜると差分がノイズだらけになるので本文だけ見る。
    """
    a = page.find('id="main"')
    b = page.find('id="footer"')
    if a < 0:
        return page
    return page[a : b if b > a else len(page)]


def to_lines(fragment: str) -> list[str]:
    """HTML断片を行のリストにする。ブロック要素の境界で改行する。

    1行の巨大な文字列にすると `git diff` が「1行まるごと変わった」しか言えなくなる。
    行に割っておけば、どの一文が増えたのかがそのまま読める。
    """
    s = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", fragment)
    s = re.sub(r"(?is)<!--.*?-->", " ", s)
    s = re.sub(r"(?i)<\s*/?\s*(?:%s)\b[^>]*>" % "|".join(BLOCK_TAGS), "\n", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = htmllib.unescape(s)
    s = s.replace("\xa0", " ")  # &nbsp; は普通の空白に寄せる（配信元が多用する）
    out: list[str] = []
    for line in s.split("\n"):
        line = re.sub(r"[ \t]+", " ", line).strip()
        if line:
            out.append(line)
    return out


def tile_ids(fragment: str) -> list[str]:
    """maps.gsi.go.jp のURLからタイルIDを抜く。

    `ls=std%7C<ID>%7C<ID2>` の重ね順指定と `lcd=<ID>` の選択レイヤー指定の両方に出てくる。
    背景地図（std, pale など）も混じるが、集合として安定しているので差分には出てこない。

    走査は maps.gsi.go.jp のURLの中だけに限る。本文全体に `%7C`/`|` を掛けると
    無関係な文字列を拾うため。
    """
    ids: set[str] = set()
    for url in re.findall(r'https?://maps\.gsi\.go\.jp/[^"\'\s<>]+', fragment, re.I):
        url = htmllib.unescape(url)
        ids.update(re.findall(r"(?:lcd=|%7C|%7c|\|)([0-9A-Za-z_]{3,})", url))
    return sorted(ids)


def data_files(fragment: str, base: str) -> list[str]:
    """配信ファイル（zip/geojson/pdf ほか）への絶対URL。"""
    out = set()
    for href in re.findall(r'href="([^"]+)"', fragment, re.I):
        href = htmllib.unescape(href)
        if re.search(r"\.(%s)(?:\?|$)" % "|".join(DATA_EXT), href, re.I):
            out.add(urljoin(base, href))
    return sorted(out)


def sub_pages(fragment: str, base: str) -> list[dict]:
    """本文中の gsi.go.jp の .html リンク（＝辿るべき下位ページ）。"""
    out: list[dict] = []
    seen: set[str] = set()
    for m in re.finditer(r'(?is)<a\s[^>]*href="([^"]+)"[^>]*>(.*?)</a>', fragment):
        href = urljoin(base, htmllib.unescape(m.group(1)))
        href = href.split("#")[0]
        if not href.endswith(".html") or "gsi.go.jp" not in href:
            continue
        if "maps.gsi.go.jp" in href or href in FOLLOW_DENY or href == base:
            continue
        if href in seen:
            continue
        seen.add(href)
        text = " ".join(to_lines(m.group(2)))
        out.append({"url": href, "text": text[:120]})
    return out


def page_dates(page: str) -> dict:
    """ページが自分で名乗っている日付。下位ページは「作成：… 更新：…」を持っている。"""
    dates: dict[str, str] = {}
    m = re.search(r'(?is)id="date"[^>]*>(.*?)</', page)
    if m:
        dates["last_update_label"] = " ".join(to_lines(m.group(1)))
    m = re.search(r"作成：([0-9０-９年月日]+)", page)
    if m:
        dates["created"] = m.group(1)
    m = re.search(r"更新：([0-9０-９年月日]+)", page)
    if m:
        dates["updated"] = m.group(1)
    return dates


# ---------------------------------------------------------------- 提供情報一覧の解析


def parse_index(region: str) -> list[dict]:
    """「提供情報一覧」の各行から 節番号・見出し・日付表記 を取る。

    行の形は `　９．斜面崩壊・堆積分布データ（７月３０日公表、８月６日更新）` 。
    見出し自体にも括弧が入る（`空中写真（垂直写真・斜め写真・正射画像）`）ので、
    末尾の括弧のうち「公表」「更新」を含むものだけを日付表記として切り離す。

    走査範囲は「提供情報一覧」の見出しから最初の節アンカー `<a name="1">` の直前まで。
    本文全体に掛けると各節の見出し（`１．空中写真…`）も同じ形なので二重に拾ってしまう。
    """
    start = region.find("提供情報一覧")
    end = region.find('<a name="1"', start if start >= 0 else 0)
    if start < 0 or end < 0:
        return []
    lines = to_lines(region[start:end])

    out: list[dict] = []
    for line in lines:
        m = re.match(r"^[　\s]*([0-9０-９]+(?:[－-][0-9０-９]+)?)．(.+)$", line)
        if not m:
            continue
        no = m.group(1).translate(FULLWIDTH_DIGITS).replace("－", "-")
        rest = m.group(2).strip()
        note = ""
        d = re.search(r"（([^（）]*(?:公表|更新)[^（）]*)）\s*$", rest)
        if d:
            # `<span>` の切れ目で空白が入る（`７月２８日公表 、７月２９日更新 `）ので詰める。
            note = re.sub(r"\s+", "", d.group(1))
            rest = rest[: d.start()].strip()
        out.append({"no": no, "title": re.sub(r"\s+", "", rest), "note": note})
    return out


def parse_sections(region: str, base: str) -> list[dict]:
    """`<a name="N">` を境目に本文を節へ割る。

    このページは見出しの階層より `<a name>` のほうが素直で、提供情報一覧の番号と
    そのまま対応する（`#9` が斜面崩壊、`#10-2` が SAR 変位境界）。
    """
    anchors = [(m.start(), m.group(1)) for m in re.finditer(r'<a\s+name="([^"]+)"', region)]
    if not anchors:
        return []
    out: list[dict] = []
    for i, (pos, name) in enumerate(anchors):
        end = anchors[i + 1][0] if i + 1 < len(anchors) else len(region)
        body = region[pos:end]
        lines = to_lines(body)
        out.append(
            {
                "anchor": name,
                "heading": lines[0] if lines else "",
                "tiles": tile_ids(body),
                "files": data_files(body, base),
                "text": lines,
            }
        )
    return out


def extract(url: str, page: str, *, is_root: bool) -> dict:
    region = main_region(page)
    m = re.search(r"(?is)<title>(.*?)</title>", page)
    rec: dict = {
        "url": url,
        "title": " ".join(to_lines(m.group(1))) if m else "",
        **page_dates(page),
        "tiles": tile_ids(region),
        "files": data_files(region, url),
    }
    if is_root:
        rec["index"] = parse_index(region)
        rec["sub_pages"] = sub_pages(region, url)
        rec["sections"] = parse_sections(region, url)
    else:
        rec["text"] = to_lines(region)
    return rec


def page_key(url: str) -> str:
    """スナップショットのキー。URLのファイル名部分（拡張子なし）。"""
    name = url.rstrip("/").rsplit("/", 1)[-1]
    return re.sub(r"\.html?$", "", name) or "index"


def crawl(*, verbose: bool = True) -> dict:
    """ルートページと、そこから辿れる下位ページを1周する。"""
    pages: dict[str, dict] = {}
    root_html = fetch(ROOT_URL)
    root = extract(ROOT_URL, root_html, is_root=True)
    pages[page_key(ROOT_URL)] = root
    if verbose:
        print(f"取得: {ROOT_URL}", file=sys.stderr)

    for sub in root.get("sub_pages", []):
        url = sub["url"]
        key = page_key(url)
        if key in pages:
            continue
        try:
            pages[key] = extract(url, fetch(url), is_root=False)
        except Exception as e:  # noqa: BLE001 - 1ページ落ちても巡回は続ける
            print(f"警告: {url} を取得できなかった: {e}", file=sys.stderr)
            pages[key] = {"url": url, "error": str(e)}
            continue
        if verbose:
            print(f"取得: {url}", file=sys.stderr)
        time.sleep(1)  # 配信元に連続で叩き込まない

    return {
        "schema": 1,
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "root": ROOT_URL,
        "pages": pages,
    }


# ---------------------------------------------------------------- ビューワとの突き合わせ


def viewer_source() -> str:
    """`layers.ts` の中身。タイルIDが載っているかの照合に使う。

    ビューワはタイルURLをテンプレートで組む箇所がある
    （`https://maps.gsi.go.jp/xyz/${s.id}/2/3/1.geojson` のように ID が別定義）ため、
    URLの形で正規表現を当てると取りこぼす。IDそのものが原文に出てくるかを見るのが確実。
    """
    if not LAYERS_TS.exists():
        return ""
    return LAYERS_TS.read_text(encoding="utf-8")


# ---------------------------------------------------------------- 差分


def _index_map(page: dict) -> dict[str, dict]:
    return {e["no"]: e for e in page.get("index", [])}


def _section_map(page: dict) -> dict[str, dict]:
    return {s["anchor"]: s for s in page.get("sections", [])}


def _tiles_by_section(page: dict) -> dict[str, str]:
    """タイルID → その出所の節見出し。差分に「どの節の話か」を添えるため。"""
    out: dict[str, str] = {}
    for s in page.get("sections", []):
        for t in s["tiles"]:
            out.setdefault(t, s["heading"])
    return out


def diff_snapshots(old: dict, new: dict) -> list[str]:
    """前回と今回を比べて Markdown の行リストを返す。空なら変更なし。"""
    lines: list[str] = []
    old_pages = old.get("pages", {})
    new_pages = new.get("pages", {})
    viewer = viewer_source()

    # --- ページの出入り
    added_pages = [k for k in new_pages if k not in old_pages]
    removed_pages = [k for k in old_pages if k not in new_pages]
    if added_pages:
        lines.append("### 新しいリンク先ページ")
        for k in added_pages:
            p = new_pages[k]
            lines.append(f"- {p.get('title') or k}  \n  {p['url']}")
        lines.append("")
    if removed_pages:
        lines.append("### 消えたリンク先ページ")
        for k in removed_pages:
            lines.append(f"- {old_pages[k].get('title') or k}  ({old_pages[k].get('url', '')})")
        lines.append("")

    # --- 提供情報一覧の日付表記（節ごとの公表・更新日）
    root_key = page_key(new.get("root", ROOT_URL))
    o_root, n_root = old_pages.get(root_key, {}), new_pages.get(root_key, {})
    o_idx, n_idx = _index_map(o_root), _index_map(n_root)
    idx_lines: list[str] = []
    for no, e in n_idx.items():
        if no not in o_idx:
            idx_lines.append(f"- **新規** {no}．{e['title']}（{e['note']}）")
        elif o_idx[no]["note"] != e["note"]:
            idx_lines.append(f"- **更新** {no}．{e['title']}: 「{o_idx[no]['note']}」→ 「{e['note']}」")
        elif o_idx[no]["title"] != e["title"]:
            idx_lines.append(f"- **改題** {no}．「{o_idx[no]['title']}」→ 「{e['title']}」")
    for no, e in o_idx.items():
        if no not in n_idx:
            idx_lines.append(f"- **削除** {no}．{e['title']}")
    if idx_lines:
        lines.append("### 提供情報一覧の変化")
        lines += idx_lines
        lines.append("")

    # --- タイルID
    o_tiles = {t for p in old_pages.values() for t in p.get("tiles", [])}
    n_tiles = {t for p in new_pages.values() for t in p.get("tiles", [])}
    where = _tiles_by_section(n_root)
    for k, p in new_pages.items():
        for t in p.get("tiles", []):
            where.setdefault(t, p.get("title") or k)
    if n_tiles - o_tiles:
        lines.append("### 地理院地図タイルの追加")
        for t in sorted(n_tiles - o_tiles):
            mark = "" if t in viewer else "  ← **ビューワ未収録**"
            lines.append(f"- `{t}`{mark}  \n  出所: {where.get(t, '?')}")
        lines.append("")
    if o_tiles - n_tiles:
        lines.append("### 地理院地図タイルの消滅（配信停止の可能性）")
        for t in sorted(o_tiles - n_tiles):
            mark = "  ← **ビューワが参照中**" if t in viewer else ""
            lines.append(f"- `{t}`{mark}")
        lines.append("")

    # --- 配信ファイル
    o_files = {f for p in old_pages.values() for f in p.get("files", [])}
    n_files = {f for p in new_pages.values() for f in p.get("files", [])}
    if n_files - o_files:
        lines.append("### 配信ファイルの追加")
        for f in sorted(n_files - o_files):
            lines.append(f"- {f}")
        lines.append("")
    if o_files - n_files:
        lines.append("### 配信ファイルの消滅")
        for f in sorted(o_files - n_files):
            lines.append(f"- {f}")
        lines.append("")

    # --- 下位ページの日付表記と本文
    body_lines: list[str] = []
    for k, n_p in new_pages.items():
        o_p = old_pages.get(k)
        if o_p is None:
            continue
        for field, label in (("updated", "更新"), ("created", "作成"), ("last_update_label", "最終更新日")):
            if o_p.get(field) != n_p.get(field):
                body_lines.append(
                    f"- {n_p.get('title') or k}: {label} 「{o_p.get(field) or '—'}」→ 「{n_p.get(field) or '—'}」"
                )
        if k == root_key:
            o_sec, n_sec = _section_map(o_p), _section_map(n_p)
            for anchor, s in n_sec.items():
                if anchor in o_sec and o_sec[anchor]["text"] != s["text"]:
                    body_lines.append(f"- 本文が変わった節: #{anchor} {s['heading']}")
        elif "text" in n_p and "text" in o_p and o_p["text"] != n_p["text"]:
            body_lines.append(f"- 本文が変わった: {n_p.get('title') or k}")
    if body_lines:
        lines.append("### 本文・更新日表記の変化")
        lines += body_lines
        lines.append("")

    return lines


def audit_lines(snap: dict) -> list[str]:
    """配信中なのに `layers.ts` に載っていないタイルの一覧。

    差分とは別の観点で、「取りこぼしが今いくつあるか」を毎回言えるようにしておく。
    背景地図や凡例（std, pale, afm, hillshademap …）は取り込む対象ではないので、
    この地震の配信物だけに絞る。
    """
    viewer = viewer_source()
    if not viewer:
        return []
    pages = snap.get("pages", {})
    where: dict[str, str] = {}
    for k, p in pages.items():
        for t in p.get("tiles", []):
            where.setdefault(t, p.get("title") or k)
    root = pages.get(page_key(snap.get("root", ROOT_URL)), {})
    for s in root.get("sections", []):
        for t in s["tiles"]:
            where[t] = s["heading"]

    # この地震の配信物だけ。ID に地震名が入っている。
    target = re.compile(r"(20260729kumamoto|20260728R8kumamoto)")
    missing = sorted(t for t in where if target.search(t) and t not in viewer)
    if not missing:
        return []
    out = [f"### ビューワ未収録のタイル（{len(missing)}件）"]
    for t in missing:
        out.append(f"- `{t}`  \n  出所: {where.get(t, '?')}")
    out.append("")
    return out


def summarize(lines: list[str]) -> str:
    """Issue タイトル向けの1行要約。

    `$GITHUB_OUTPUT` は `key=value` を1行で書く形式なので、改行が混ざると壊れる。
    見出ししか使わないので通常は混ざらないが、念のため落としておく。
    """
    heads = [ln[4:] for ln in lines if ln.startswith("### ")]
    if not heads:
        return "変更なし"
    s = re.sub(r"\s+", " ", "、".join(heads))
    # Issue タイトルに使うので長すぎない範囲に収める。切り詰めはここで済ませる
    # （シェルの `cut -c` はバイト単位で切ることがあり、日本語が化ける）。
    return s if len(s) <= 80 else s[:79] + "…"


def carry_over_failures(old: dict, new: dict) -> list[str]:
    """取得に失敗したページは前回の内容を引き継ぐ。

    そのまま空の記録で差分を取ると「タイルが全部消えた」「ファイルが全部消えた」という
    誤検知になり、さらに `--update` でその壊れた記録が次回の基準になって、
    復旧した瞬間に今度は「全部追加された」と鳴る。一時的な取得失敗は差分ではないので、
    前回の内容を据え置いて、失敗した事実だけを警告として残す。
    """
    warn: list[str] = []
    old_pages = old.get("pages", {})
    for key, page in list(new.get("pages", {}).items()):
        if "error" not in page:
            continue
        err = page["error"]
        prev = old_pages.get(key)
        if prev and "error" not in prev:
            # 前回の記録をそのまま据え置く。失敗の事実はレポートにだけ出し、
            # スナップショットには残さない（次回成功時に消し忘れが起きない）。
            new["pages"][key] = dict(prev)
            warn.append(f"- {prev.get('title') or key}: 取得失敗のため前回の内容を据え置き（{err}）")
        else:
            warn.append(f"- {page.get('url', key)}: 取得失敗（{err}）")
    return warn


# ---------------------------------------------------------------- エントリポイント


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--update", action="store_true", help="スナップショットを書き換える")
    ap.add_argument(
        "--audit",
        action="store_true",
        help="差分の有無にかかわらず、配信中なのに layers.ts に無いタイルを列挙する",
    )
    ap.add_argument("--report", type=Path, help="差分レポート（Markdown）の出力先")
    ap.add_argument("--github-output", type=Path, help="GitHub Actions の $GITHUB_OUTPUT に changed/summary を書く")
    ap.add_argument("--snapshot", type=Path, default=SNAPSHOT, help="スナップショットの場所")
    args = ap.parse_args()

    try:
        new = crawl()
    except Exception as e:  # noqa: BLE001
        print(f"エラー: ルートページを取得できなかった: {e}", file=sys.stderr)
        return 1

    first_run = not args.snapshot.exists()
    old = {} if first_run else json.loads(args.snapshot.read_text(encoding="utf-8"))

    failures = carry_over_failures(old, new)

    if first_run:
        diff = ["初回取得。以降はこのスナップショットとの差分を見る。", ""]
        changed = False
    else:
        diff = diff_snapshots(old, new)
        changed = bool(diff)

    # 未収録の棚卸しは、差分が出たとき（対応作業の材料になる）と明示指定のときだけ添える。
    # 毎回無条件に足すと「変更なし」の判定に混ざる。要約は差分側だけから作る。
    report = diff + audit_lines(new) if (changed or first_run or args.audit) else diff

    if failures:
        report = report + ["### 取得できなかったページ"] + failures + [""]

    n_pages = len(new["pages"])
    n_tiles = len({t for p in new["pages"].values() for t in p.get("tiles", [])})
    footer = [
        "---",
        f"巡回: {n_pages}ページ / タイルID {n_tiles}件 / 取得時刻 {new['fetched_at']}",
        f"配信元: {ROOT_URL}",
    ]

    verbose_out = changed or first_run or args.audit or bool(failures)
    body = "\n".join(report + footer) if verbose_out else "変更なし"
    print(body)

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(body + "\n", encoding="utf-8")

    # 変化が無いときは書き換えない。`fetched_at` だけが動いて作業ツリーが汚れるのを避ける
    # （最後にいつ巡回したかは Actions の実行ログに残る）。
    if args.update and (changed or first_run):
        args.snapshot.parent.mkdir(parents=True, exist_ok=True)
        args.snapshot.write_text(
            json.dumps(new, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8"
        )

    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as f:
            f.write(f"changed={'true' if changed else 'false'}\n")
            f.write(f"first_run={'true' if first_run else 'false'}\n")
            f.write(f"summary={summarize(diff)}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
