# 令和8年（2026年）熊本地震 災害情報ビューワ

2026年7月28日 16時27分に発生した**令和8年（2026年）熊本地震**（熊本県熊本地方 深さ16km、M7.1 暫定値、最大震度7＝宇城市・氷川町）の災害情報レイヤーを、[MapLibre GL JS](https://maplibre.org/) で重ね合わせて閲覧する WebGIS。

## 収録レイヤー

| グループ | レイヤー | 形式 | 出典 | 既定 |
| --- | --- | --- | --- | --- |
| 震源・揺れ | 震源（震央） | GeoJSON（点） | 気象庁 | ON |
| 震源・揺れ | 推計震度分布（250mメッシュ） | ラスタタイル（同梱） | 気象庁 | ON |
| 人口 | 夜間人口（国勢調査2020 125mメッシュ） | PMTiles（同梱・359,259メッシュ） | 総務省統計局／e-Stat | |
| 被害状況 | 斜面崩壊・土石流・堆積分布 | GeoJSON（21面） | 国土地理院 | |
| 被害状況 | 道路規制（7/31 7:30時点） | GeoJSON（同梱・62区間） | 国土交通省 | |
| 空中写真 | 正射画像（速報）八代地区 7/29撮影 | ラスタタイル | 国土地理院 | |
| 空中写真 | 垂直写真（速報）八代地区 7/29撮影 | GeoJSON（点・513枚） | 国土地理院 | |
| 空中写真 | 斜め写真 八代地区 7/29撮影 | GeoJSON（点・567枚） | 国土地理院 | |
| 空中写真 | 垂直写真 熊本1地区 7/29撮影 | GeoJSON（点・127枚） | 国土地理院 | |
| 空中写真 | 垂直写真 熊本2地区 7/29撮影 | GeoJSON（点・201枚） | 国土地理院 | |
| 空中写真 | 斜め写真 熊本4地区 7/29撮影 | GeoJSON（点・140枚） | 国土地理院 | |
| 地殻変動 | SAR干渉画像 だいち4号 7/2〜7/30 | ラスタタイル | 国土地理院（解析）／JAXA | |
| 地殻変動 | SAR干渉画像 だいち2号 2025/8/12〜7/28 | ラスタタイル | 国土地理院（解析）／JAXA | |
| 地形・活断層 | 全国の主要活断層帯 | GeoJSON（同梱・3,248地物） | 地震調査研究推進本部 | ON |
| 地形・活断層 | 活断層図（都市圏活断層図） | ラスタタイル | 国土地理院 | |

背景地図は国土地理院の最適化ベクトルタイル（淡色）と全国最新写真、3D地形は産総研のシームレス標高タイル。
配信元が CORS を返すレイヤーは実行時に直接参照し、同梱は[4つだけ](#同梱データ)。

### データの出どころ

| 出典 | 参照先 |
| --- | --- |
| 国土地理院「[令和8年（2026年）熊本地震に関する情報](https://www.gsi.go.jp/BOUSAI/20260728_kumamoto_earthquake.html)」 | レイヤー定義 `maps.gsi.go.jp/layers_txt/layers_20260729kumamoto.txt` |
| 気象庁「[推計震度分布図](https://www.jma.go.jp/bosai/map.html)」 | 索引 `.../estimated_intensity_map/data/list.json` のイベント `202607281627_741` |
| 地震調査研究推進本部「全国の主要活断層帯」 | `maps.gsi.go.jp/xyz/active_fault/2/3/1.geojson` |
| 産総研 地質調査総合センター「[シームレス標高タイル](https://gbank.gsj.jp/seamless/elev/)」 | `gbank.gsj.jp/seamless/elev/terrainRGB/mixed/{z}/{y}/{x}.png` |
| 国土地理院「[熊本地震に伴う地殻変動](https://www.gsi.go.jp/uchusokuchi/20260728kumamoto.html)」（SAR） | レイヤー定義 `maps.gsi.go.jp/sar/layers_txt/layers_alos2_eq_20260728kumamoto.txt` |
| 国土交通省「[通れるマップ](https://www.mlit.go.jp/road/saigai/r8kumamoto/index.html)」 | 日時別 `www.mlit.go.jp/road/saigai/r8kumamoto/2607310800data.zip`（**「現時点データ一式」は別災害のテストデータなので使わない**） |

## ビューワの操作

- **レイヤーパネル**（デスクトップは左、モバイルはボトムシート） … トグル、`i` で説明、
  ON のあいだだけ不透明度スライダーと凡例。全ON／全OFF、▴▾ で開閉
- **背景地図**（右下）「地図」／「写真」、**テーマ**（🌙 ☀️）、**3D地形**（右上の山アイコン）
- **ポップアップ** … 点・面をクリックで属性。空中写真はサムネイル → クリックで拡大
- **URL ハッシュ**に位置・ズーム・傾き・向きが入る。`?debug` で右上に診断 HUD

## セットアップと公開

```sh
cd viewer
npm ci
npm run dev      # http://localhost:8000
npm run build    # tsc --noEmit && vite build → viewer/dist
```

`main` への push で GitHub Actions（`.github/workflows/deploy.yml`）が GitHub Pages へデプロイする。
Vite の `base` は `'./'` なのでプロジェクトページ（`/<repo>/` 配下）でも動く。
初回のみ **Settings → Pages → Source** を **GitHub Actions** にする。

## レイヤーの追加

`viewer/src/layers.ts` の `LAYERS` に 1 エントリ足すだけでよい。`main.ts` は `kind` だけを見て
汎用的に地図へ載せるので、レイヤーごとの分岐は要らない。

| `kind` | 内容 |
| --- | --- |
| `raster` | XYZ ラスタタイル。`bounds` を書くと範囲外を取りに行かない |
| `wms` | `{bbox-epsg-3857}` を使った WMS（[MapLibre の作法](https://maplibre.org/maplibre-gl-js/docs/examples/add-a-wms-source/)どおり。**CORS を返すサーバに限る**） |
| `geojson` | `render: 'polygon'`（LineString が混在していても線として描く）／`render: 'point'`（`icons` か `circle`）。`data` は URL でもインラインの FeatureCollection でもよい |
| `pmtiles` | ベクタタイルを1属性の階級区分で塗る。`prop` と `steps`（`{min, color, label}` 昇順）から `step` 式と凡例の両方を作る。`extrude` を付けると `fill-extrusion` で描き、属性値 × `metersPerUnit` が高さになる（**常に立体**。2D/3D の切替は無い） |

共通の指定は `z`（重なり順・大きいほど前面）、`group`（パネルの見出し。順序は `GROUPS`、そこに無いものは非表示）、
`legend` か `legendImage`（階級区分は `steps` から自動生成）、`popup`（`title` / `rows` / `labels` /
`html` = エスケープせず埋め込む属性）、`desc`（`i` の説明）、`attribution`。

地理院地図の災害 GeoJSON は cocotile 方式（`maxNativeZoom: 2`）なので、対象地区を含む z=2 タイル1枚を
`data` に直接指定する。地物が持つ Leaflet 用のスタイル属性（`_fillColor` / `_color` / `_fillOpacity` /
`_weight`）は配色を決め直さずそのまま使う。

## 同梱データ

直接参照できない・しないほうがよい4つだけを `viewer/public/data/` に置いている。

| データ | 同梱する理由 | 生成 |
| --- | --- | --- |
| 道路規制<br>62区間・271KB | 配信元は ZIP。規制が2ファイルに分裂していて重複22本を含むので、統合と正規化が要る | `tools/build_road_restriction.py` |
| 推計震度分布<br>z5-z11・958タイル・約0.9MB | 気象庁は1次メッシュごとの PNG で配信していて、MapLibre の image ソースだと緯度方向に100m前後歪む。GDAL で再投影してタイルに焼いている | `tools/fetch_jma_shindo_tiles.py` |
| 主要活断層帯<br>3,248地物・869KB | 配信元はインデント付き2.36MBで gzip も返らない。座標を5桁に丸めた compact JSON にして実転送 約160KB | `tools/build_active_fault.py` |
| 夜間人口メッシュ<br>359,259メッシュ・19MB | 元の全国版 PMTiles は311MBで GitHub の100MB上限を超える。人口3項目だけに絞って揺れた範囲へ切り出し | `tools/build_population_mesh.py` |

使うときに知っておくとよい癖:

- **推計震度は震度4以上しか塗られていない**（震度1〜3の公式色は1画素も含まれないことを実測で確認）。
  弱い揺れまで見たいなら防災科研 J-RISQ だが、WMS が CORS を返さず別オリジンから読めない
  （予備に `tools/fetch_jrisq_tiles.py` と `raw/jrisq/*.kml` を残してある）
- **推計震度の配色は J-RISQ のものに置き換えている**（値は気象庁のまま）。気象庁の配色は面積の大半を
  占める震度4〜5弱が淡くて階級差が読みにくい。戻すなら `--palette jma` で焼き直して `SHINDO_LEGEND` も戻す
- **主要活断層帯は断層線が名称を持たない**。名称は不可視ポリゴン163面（`name` 134種／`description` 54種）
  の側にしかないので、クリック時は `_` 始まり以外の属性を持つ地物を優先して選んでいる
- **夜間人口は低ズームでメッシュが統合される**（`--coalesce-densest-as-needed`）。人口は合算されるので、
  1区画の値も3Dの高さも125mメッシュ1つ分より大きくなる。人口0は描かず、実際に描かれるのは352,267メッシュ
- **通れるマップの「現時点データ一式」（`road/saigai/test/map.zip`）は使ってはいけない**。同梱の
  index.html のタイトルが「霞ヶ関での大雪　道路の被害状況マップ」で、中身は全国の積雪・路面凍結規制（1〜2月）と
  首都圏の ETC2.0。熊本地震のデータは1件も無い。使えるのは日時別 ZIP（7/29 8時〜7/31 8時の6本）だけで、
  ページが「最新」と書いている7/31 16時は404
- **道路規制の色は配信元のものを使っていない**。同梱凡例は「規制中（事前）＝灰・黒」としているが、
  実データの `#999999` 19本は規制種別が全件「災害」で規制理由も落石・道路損壊。凡例どおりの意味に
  なっていないので、`規制内容` から状態を導き直している。属性が空の13区間（7/31 8時にだけ現れる）は
  意味が特定できないので細い灰色で控えめに描いている
- 夜間人口の入力 parquet は `../japan-mobility-ease-diagnosis/` にあり、**このリポジトリの外**

## 設計メモ

込み入った判断はソース側のコメントに書いてある。ここは索引。

| 判断 | 理由 | 詳細 |
| --- | --- | --- |
| 3D地形は産総研の Terrain-RGB（PNG標高タイルではない） | MapLibre の `encoding: 'custom'` は線形式のみで符号付き24bitを解釈できず、海面下が +167km の尖りになる | `layers.ts` `TERRAIN` |
| 3D地形の `maxzoom` は 14、`{z}/{y}/{x}` 順 | z15以降は 400 が散発し、穴があるとその範囲だけ平坦になる。URL の x/y は地理院タイルと逆 | 同上 |
| 3D地形はパネルに出さず `TerrainControl` | ソースは常時スタイルに入れておく（無効な間はタイルを取らない）。スタイル差し替えで消えるので `reloadStyle()` で戻す | `main.ts` |
| 夜間人口は色相310°の4階級 | 推計震度（10〜150°）と活断層線（258°）に挟まれた唯一の空き。6階級では明度差が足りず基図に紛れる | `layers.ts` `pop-mesh` |
| 夜間人口の区切りは 1/4/12/35 | 対象域の四分位。当初の 1/10/30/100/300/1000 は上位2階級に0.65%しか入らなかった | 同上 |
| 夜間人口は常に立体・ONで自動的に傾ける | 密集市街地は最上位階級が支配的になるので、内部の差は高さで読む | 同上 |
| SAR は `https://` へ書き換え、実測 bbox を `bounds` に入れて直接参照 | 定義は `http://` だが https でも同じタイルが返る。解析範囲が定義に無いので z11 の到達確認から実測 | `layers.ts` `sar-*` |
| ダークテーマでコントロールアイコンを差し替え | MapLibre のアイコンは `fill` が `#333` 固定 | `style.css` |
| デスクトップはスケールバーを右へ300pxずらす | パネルと地図コントロールが同じ `z-index: 2` で、DOM で後ろのパネルが勝つ | 同上 |

コンソールに出るが無害なもの: SAR は bbox 内でもストリップから外れたタイルが 404 になり、
その 404 に CORS ヘッダが付かないため CORS エラーとして表示される。描画には影響しない。

## リポジトリ構成

```
.github/workflows/deploy.yml    GitHub Pages へのデプロイ
raw/                            取得した原本（J-RISQ の KML、主要活断層帯の GeoJSON）
tools/                          同梱データの生成スクリプトとアイコン生成
viewer/index.html               パネルの骨組みと諸元表示
viewer/src/main.ts              kind を見てレイヤーを載せる汎用エンジン、UI、地図コントロール
viewer/src/layers.ts            レイヤーレジストリ（ここに足す）と 3D地形の設定
viewer/src/basemap.ts           背景地図（淡色ベクター／写真、ダークは明度反転で生成）
viewer/src/pale-style.json      地理院 最適化ベクトルタイルの淡色スタイル
viewer/src/theme.ts             ライト／ダークの判定と保存
viewer/src/style.css            パネル・凡例・ポップアップ・地図コントロールの見た目
viewer/public/data/             同梱データ
viewer/public/icons/            ファビコン・アプリアイコン
```

## 未対応

- **地形分類データ**（自然地形 / 人工地形） … `{z}/{x}/{y}.geojson`（native z16）配信で
  MapLibre がそのまま扱えない。ベクトルタイル化（PMTiles 等）が要る
- **ETC2.0 平均速度**（47,065本・46MB）と**通行実績**（38,715本・34MB） … 通れるマップの
  同じ ZIP に入っているが、属性が `_color`/`_opacity`/`_weight` の3つだけで速度値も路線名も時刻も
  持たない。載せるなら PMTiles 化が必要で、得られるのは「時速20km以下／21km以上」の2値と
  「通行実績」の1色を塗るだけのレイヤー。凡例に「工事車両の速度や通行実績が表示されている場合があり、
  一般車両は通れない場合もある」と明記されている点にも注意が要る
- **震源断層モデル**、電子基準点による地殻変動

## 出典・ライセンス

- 国土地理院コンテンツの利用は[国土地理院コンテンツ利用規約](https://www.gsi.go.jp/kikakuchousei/kikakuchousei40182.html)に従う
- 気象庁のデータ利用は[気象庁ホームページについて](https://www.jma.go.jp/jma/kishou/info/coment.html)に従う
- J-RISQ地震速報の利用は防災科学技術研究所の定めに従う
- 国勢調査の統計データ・境界データの利用は[政府統計の総合窓口（e-Stat）の利用規約](https://www.e-stat.go.jp/terms-of-use)に従う
- 主要活断層帯のデータは地震調査研究推進本部の長期評価に基づく
- SAR干渉画像は国土地理院による解析結果で、原初データの所有は JAXA
- 道路規制は国土交通省「通れるマップ」の公開データ（民間プローブの提供元はトヨタ自動車・日産自動車・
  本田技研工業・いすゞ自動車・日野自動車）
- 本ビューワのコードは MIT License
