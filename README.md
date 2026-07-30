# 令和8年（2026年）熊本地震 災害情報ビューワ

2026年7月28日 16時27分頃に発生した**令和8年（2026年）熊本地震**（熊本県熊本地方 深さ16km、M7.1（暫定値）、最大震度7＝宇城市・氷川町）の災害情報レイヤーを、[MapLibre GL JS](https://maplibre.org/) で重ね合わせて閲覧する WebGIS。

## 収録レイヤー

| グループ | レイヤー | 形式 | 出典 | 既定 |
| --- | --- | --- | --- | --- |
| 震源・揺れ | 震源（震央） | GeoJSON（点） | 気象庁 | ON |
| 震源・揺れ | 推計震度分布（250mメッシュ） | ラスタタイル（同梱） | 防災科研 J-RISQ地震速報 | ON |
| 被害状況 | 斜面崩壊・土石流・堆積分布 | GeoJSON（21面） | 国土地理院 | |
| 空中写真 | 正射画像（速報）八代地区 7/29撮影 | ラスタタイル | 国土地理院 | |
| 空中写真 | 垂直写真（速報）八代地区 7/29撮影 | GeoJSON（点・513枚） | 国土地理院 | |
| 空中写真 | 斜め写真 八代地区 7/29撮影 | GeoJSON（点・567枚） | 国土地理院 | |
| 地形・活断層 | 全国の主要活断層帯 | GeoJSON（同梱・3,248地物） | 地震調査研究推進本部 | ON |
| 地形・活断層 | 活断層図（都市圏活断層図） | ラスタタイル | 国土地理院 | |

背景地図は国土地理院の**最適化ベクトルタイル**（淡色。ダークテーマは明度反転で生成）と**全国最新写真**を切り替えられる。

### データの出どころ

- 国土地理院「[令和8年（2026年）熊本地震に関する情報](https://www.gsi.go.jp/BOUSAI/20260728_kumamoto_earthquake.html)」
  レイヤーの URL・ズーム範囲は地理院地図のレイヤー定義 `https://maps.gsi.go.jp/layers_txt/layers_20260729kumamoto.txt` に準拠。
- 防災科学技術研究所「[J-RISQ地震速報](https://www.j-risq.bosai.go.jp/)」
  レポート `R-20260728162724-0145-00001`（2026/07/28 16:40:13発表 Ver.8 最終報）。
- 地震調査研究推進本部「全国の主要活断層帯」
  地理院地図のレイヤー `active_fault_jishinhonbu`（`https://maps.gsi.go.jp/xyz/active_fault/2/3/1.geojson`）。

## セットアップ

```sh
cd viewer
npm ci
npm run dev      # http://localhost:8000
npm run build    # tsc --noEmit && vite build → viewer/dist
```

## 公開

`main` への push で GitHub Actions（`.github/workflows/deploy.yml`）が `viewer/` をビルドし、GitHub Pages へデプロイする。
Vite の `base` は `'./'` にしてあるため、プロジェクトページ（`/<repo>/` 配下）でもそのまま動く。

初回のみ、リポジトリの **Settings → Pages → Source** を **GitHub Actions** に設定する必要がある。

## レイヤーの追加

`viewer/src/layers.ts` の `LAYERS` に 1 エントリ足すだけでよい。`main.ts` は `kind` だけを見て
汎用的に地図へ載せるので、レイヤーごとの分岐を書き足す必要はない。

対応している `kind`:

- `raster` … XYZ ラスタタイル（地理院タイル等）。`bounds` を書くと範囲外を取りに行かない
- `wms` … `{bbox-epsg-3857}` を使った WMS（[MapLibre の作法](https://maplibre.org/maplibre-gl-js/docs/examples/add-a-wms-source/)どおり。**ただし CORS を返すサーバに限る**）
- `geojson` … `render: 'polygon'`（面。LineString が混在していても線として描かれる）/
  `render: 'point'`（`icons` でアイコン画像、`circle` で円マーカー。`data` は URL でもインラインの
  FeatureCollection でもよい）

ポップアップは `popup` で組み立てる。`title` にタイトルへ使う属性、`rows` に出す属性の順序、
`labels` に見出しの読み替え、`html` にエスケープせず埋め込む属性（地理院の写真レイヤーは
属性値そのものが `<img>` を含む HTML）を書く。

`z` が重なり順（大きいほど前面）、`group` がパネルの見出し。凡例は `legend`（色と label の配列）か
`legendImage`（配布されている凡例画像の URL）で与える。

### 地理院地図の GeoJSON レイヤーについて

地理院地図の災害 GeoJSON は **cocotile** 方式（`maxNativeZoom: 2`）で、対象地区を含む
z=2 タイル 1 枚に全地物が入っている。そのため MapLibre では `{z}/{x}/{y}` を使わず、
その 1 枚を `geojson` ソースの `data` に直接指定している。

地物ごとに Leaflet 用のスタイル属性（`_fillColor` / `_color` / `_fillOpacity` / `_weight`）を
持っているので、配色を独自に決め直さず、データ駆動でその値をそのまま使っている。

## J-RISQ の推計震度分布をタイル化している理由

J-RISQ の WMS は https と EPSG:3857 に対応しており、MapLibre の `{bbox-epsg-3857}` 方式で
そのまま raster ソースにできる形になっている。しかし**レスポンスに
`Access-Control-Allow-Origin` が無い**ため、GitHub Pages のような別オリジンからは
ブラウザに遮断される（実測: 90リクエストすべて `net::ERR_FAILED`）。

対象レポートは確定済みのスナップショットなので、あらかじめタイルへ焼いて同梱している。

```sh
python3 tools/fetch_jrisq_tiles.py                    # 既定レポートを取得
python3 tools/fetch_jrisq_tiles.py --triggerid R-... --report 0145 --ana 00001
```

- 入力（原本）: `raw/jrisq/R-20260728162724-0145-00001.kml`
  J-RISQ のレポートページからダウンロードできる KML。中身はベクタではなく
  WMS の `GroundOverlay` 9枚で、そのうち `visibility=1` の `GSI_M250` が推計震度分布にあたる。
  残り8枚は震度曝露人口（震度5弱〜6強 × 250mメッシュ／行政区）。
- 出力先: `viewer/public/data/jrisq/GSI_M250/{z}/{x}/{y}.png` と `viewer/public/data/jrisq/metadata.json`
- 範囲: 推定震度1以上の実測範囲（128.5-138.6E / 29.4-37.3N）、z5-z11
- 全透明のタイルは書き出さないため、計画枚数（4,116枚）の3割程度に収まる
- 配色は J-RISQ の `GetLegendGraphic` の実物から採色した10段階（推定震度0〜7）。
  気象庁の震度配色とは別の独自パレットなので、`layers.ts` の `SHINDO_LEGEND` に実測値を持っている

なお国土地理院のタイル・GeoJSON は `Access-Control-Allow-Origin: *` を返すため、
こちらは基本的に取り込みせず実行時に直接参照している（例外は次項）。

## 主要活断層帯を圧縮して同梱している理由

配信元 `https://maps.gsi.go.jp/xyz/active_fault/2/3/1.geojson` は CORS を返すので直接参照もできる。
ただしこのファイルはインデント付きで **2.36MB あり、しかも配信側が gzip を返さない**。
レイヤーを ON にするたび 2.36MB を素で転送することになるため、座標を5桁（約1m）に丸めた
compact JSON にして同梱している。GitHub Pages は静的ファイルを圧縮して返すので、
実転送量は **約160KB**（元の1/14）に収まる。災害時に配信元が重い場合でも表示できる利点もある。

```sh
python3 tools/build_active_fault.py                    # 配信元から取得して生成
python3 tools/build_active_fault.py --input raw/gsi/active_fault_jishinhonbu.geojson
```

データの構造には癖がある。

- LineString 3,085本 … 断層線本体（`_color: #3388ff` / `_weight: 3`）。**属性に名称を持たない**
- Polygon 163面 … 断層帯の名称を持つ**不可視**の領域（`_opacity: 0` / `_fillOpacity: 0`）。
  地理院地図ではクリックして名称を出すための当たり判定として使われている。
  `name`（135種）と `description`（55種）はこちらにしか無い

そのため、クリック時は「`_` 始まり以外の属性を持つ地物」を優先して選ぶようにしている
（先頭決め打ちだと、線に当たったときに空のポップアップになる）。

## リポジトリ構成

```
.github/workflows/deploy.yml   GitHub Pages へのデプロイ
raw/                           取得した原本（J-RISQ の KML、主要活断層帯の GeoJSON）
tools/fetch_jrisq_tiles.py     J-RISQ の WMS → 静的 XYZ タイル
tools/build_active_fault.py    主要活断層帯 GeoJSON の圧縮
tools/make_icons.py            ファビコン・アプリアイコンの生成
viewer/src/layers.ts           レイヤーレジストリ（ここに足す）
viewer/src/main.ts             kind を見てレイヤーを載せる汎用エンジン
viewer/src/basemap.ts          背景地図（淡色ベクター／写真、ダークは明度反転）
viewer/public/data/            同梱データ（推計震度タイル、主要活断層帯）
```

## 未対応（今後）

- **地形分類データ**（自然地形 / 人工地形） … `{z}/{x}/{y}.geojson`（native z16）で配信されており、
  MapLibre がそのまま扱える形式ではないため、ベクトルタイル化（PMTiles 等）が必要
- **「だいち2号」SAR干渉解析による地殻変動** … `https://maps.gsi.go.jp/sar/layers_txt/layers_alos2_eq_20260728kumamoto.txt`
- **震源断層モデル**、電子基準点による地殻変動

## 出典・ライセンス

- 国土地理院コンテンツの利用は[国土地理院コンテンツ利用規約](https://www.gsi.go.jp/kikakuchousei/kikakuchousei40182.html)に従う
- J-RISQ地震速報の利用は防災科学技術研究所の定めに従う
- 本ビューワのコードは MIT License
