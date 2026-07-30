import type { FeatureCollection } from 'geojson'
import type {
  CircleLayerSpecification,
  ExpressionSpecification,
  FillExtrusionLayerSpecification,
  FillLayerSpecification,
  LayerSpecification,
  LineLayerSpecification,
  RasterLayerSpecification,
  SourceSpecification,
  SymbolLayerSpecification,
} from 'maplibre-gl'

/**
 * 令和8年（2026年）熊本地震 災害情報レイヤーのレジストリ。
 *
 * レイヤーを追加するときは LAYERS に 1 エントリ足すだけでよい。
 * main.ts は kind（raster / wms / geojson）だけを見て汎用的に地図へ載せるため、
 * 個別のレイヤーに対する分岐を main.ts 側へ書き足す必要はない。
 *
 * 各エントリの url / minzoom / maxzoom は、地理院地図のレイヤー定義
 * （https://maps.gsi.go.jp/layers_txt/layers_20260729kumamoto.txt 等）および
 * 実際のタイル・GeoJSON への到達確認に基づく実測値。
 */

// ---- 出典 ----
const GSI_ATTR =
  '<a href="https://www.gsi.go.jp/BOUSAI/20260728_kumamoto_earthquake.html" target="_blank" rel="noopener">国土地理院</a>'
const JMA_ATTR = '<a href="https://www.jma.go.jp/" target="_blank" rel="noopener">気象庁</a>'
const ESTAT_ATTR =
  '<a href="https://www.e-stat.go.jp/gis" target="_blank" rel="noopener">国勢調査2020 125mメッシュ（総務省統計局／e-Stat）</a>'
const HERP_ATTR =
  '<a href="https://www.jishin.go.jp/main/oshirase/20260728_kumamoto.html" target="_blank" rel="noopener">地震調査研究推進本部</a>'

/** 震央（気象庁 暫定値）: 2026/07/28 16:27 熊本県熊本地方 深さ16km M7.1 */
export const EPICENTER: [number, number] = [130.65, 32.61]

// ---- 凡例 ----
export interface LegendItem {
  label: string
  color: string
  /** box=塗り, line=線, dot=点。既定は box。 */
  shape?: 'box' | 'line' | 'dot'
  /** 枠線色（box のとき） */
  outline?: string
}

// ---- 共通定義 ----
interface LayerBase {
  /** 一意キー。MapLibre の source id / layer id の接頭辞に使う。 */
  key: string
  /** 表示名 */
  name: string
  /** パネルのグループ見出し */
  group: string
  /** 初期表示 ON/OFF */
  on: boolean
  /** 初期不透明度（UI のスライダーで変更可能） */
  opacity: number
  /** i ボタンで開く説明。データの性質・判読上の注意を書く。 */
  desc: string
  /** AttributionControl に出す出典 */
  attribution: string
  /**
   * 重なり順。大きいほど前面。
   * パネルの並び（group 単位）とは独立に指定できるようにしてある。
   */
  z: number
  legend?: LegendItem[]
  /** 凡例が画像で配布されている場合の URL（legend より優先して表示） */
  legendImage?: string
}

/** ラスタタイル（地理院タイル等） */
interface RasterDef extends LayerBase {
  kind: 'raster'
  tiles: string[]
  minzoom?: number
  maxzoom?: number
  tileSize?: number
  /**
   * データが存在する範囲 [西, 南, 東, 北]。
   * 撮影範囲の外まで無駄にタイルを取りに行って 404 を量産しないために指定する。
   */
  bounds?: [number, number, number, number]
}

/**
 * WMS。MapLibre の raster ソースに {bbox-epsg-3857} を含む URL を渡す方式。
 * https://maplibre.org/maplibre-gl-js/docs/examples/add-a-wms-source/
 */
interface WmsDef extends LayerBase {
  kind: 'wms'
  /** {bbox-epsg-3857} を含む GetMap URL */
  url: string
  tileSize?: number
  minzoom?: number
  maxzoom?: number
}

/**
 * PMTiles のベクタタイルを、1属性の階級区分（コロプレス）で塗るレイヤー。
 * 統計系のレイヤーを足すときはこの kind を使う。
 */
interface ChoroplethDef extends LayerBase {
  kind: 'pmtiles'
  /** PMTiles の URL（`pmtiles://` は内部で付ける） */
  url: string
  /** タイル内のレイヤー名 */
  sourceLayer: string
  /** 色分けに使う属性 */
  prop: string
  /**
   * 階級。min の昇順に並べる。先頭の min 未満は描かない（値なし扱い）。
   * MapLibre の step 式と凡例の両方をここから作る。
   */
  steps: { min: number; color: string; label: string }[]
  minzoom?: number
  maxzoom?: number
  popup?: PopupSpec
  /**
   * 立体表示（3D）の設定。指定すると fill ではなく fill-extrusion で描く。
   * 2D のときは高さ 0 のままなので、見た目は塗りと変わらない。
   */
  extrude?: {
    /** 高さに使う属性。省略時は prop と同じ。 */
    prop?: string
    /** 属性値1あたりの高さ（m） */
    metersPerUnit: number
  }
}

/** ポップアップの組み立て方 */
interface PopupSpec {
  /** タイトルに使う属性。無ければレイヤー名。 */
  title?: string
  /** 表に出す属性の順序。省略時は `_` 始まり以外の全属性。 */
  rows?: string[]
  /**
   * 生 HTML として描画する属性。
   * 地理院地図の写真レイヤーは属性値に <img>/<a> を含む HTML が入っているため、
   * エスケープせずそのまま埋め込む必要がある。
   */
  html?: string[]
  /** 属性名の表示ラベル。配信データのキーがローマ字のときに読める見出しへ差し替える。 */
  labels?: Record<string, string>
}

/** GeoJSON ソースの中身。URL か、インラインの FeatureCollection。 */
type GeoJsonData = string | FeatureCollection

/** GeoJSON（面。LineString が混在していても線として描かれる） */
interface GeoJsonPolygonDef extends LayerBase {
  kind: 'geojson'
  render: 'polygon'
  data: GeoJsonData
  minzoom?: number
  maxzoom?: number
  popup?: PopupSpec
}

/** 円マーカーの見た目 */
interface CircleSpec {
  radius: number
  color: string
  strokeColor?: string
  strokeWidth?: number
}

/** GeoJSON（点。アイコン画像か円マーカーで描く） */
interface GeoJsonPointDef extends LayerBase {
  kind: 'geojson'
  render: 'point'
  data: GeoJsonData
  minzoom?: number
  maxzoom?: number
  popup?: PopupSpec
  /**
   * アイコン画像。キーは地物の `_iconUrl` の値そのまま、値は MapLibre に登録する image id。
   * `_iconUrl` は http:// で配信されている場合があるため、読み込み時に https へ寄せる。
   * 省略すると circle だけで描く（フォントにもスプライトにも依存しない）。
   */
  icons?: Record<string, string>
  /** icons に一致しなかったときに使う image id */
  iconFallback?: string
  /** アイコンの表示倍率 */
  iconSize?: number
  /**
   * 円マーカー。配列の先頭が最背面。
   * 省略時、icons があれば読み込み失敗時の下敷きとして既定の円を1枚置く。
   */
  circle?: CircleSpec[]
}

export type LayerDef = RasterDef | WmsDef | GeoJsonPolygonDef | GeoJsonPointDef | ChoroplethDef

// ---- 気象庁 推計震度分布図（250mメッシュ） ----
/**
 * 値は気象庁の推計震度、配色は防災科研 J-RISQ のもの。
 *
 * 気象庁の配信 PNG には気象庁の階級色（#fae696〜#b40068）が焼き込まれているので、
 * tools/fetch_jma_shindo_tiles.py の --palette jrisq で、各画素を気象庁の階級色の
 * 最近傍へ再分類してから J-RISQ の色に置き換えている。ここの色はその置き換え後の値。
 * 気象庁の配色に戻すなら --palette jma で焼き直して、ここも元の6色に戻す。
 *
 * 画像に描かれているのは**震度4以上だけ**（震度1〜3の気象庁公式色
 * #f2f2ff / #00aaff / #0041ff は1画素も含まれないことを実測で確認）。
 * 索引 list.json の rank_cnt には震度0〜3のメッシュ数も入っているが、図には出てこない。
 */
const SHINDO_LEGEND: LegendItem[] = [
  { label: '震度7', color: '#950d05' },
  { label: '震度6強', color: '#f45178' },
  { label: '震度6弱', color: '#faaa46' },
  { label: '震度5強', color: '#f7f618' },
  { label: '震度5弱', color: '#96d050' },
  { label: '震度4', color: '#1e973d' },
]

// ---- 地理院地図 斜め写真の方向アイコン ----
// _iconUrl は 181/184/185/186 の4種（撮影方向の概略を示す矢印）。
const NANAME_ICON_BASE = 'https://cyberjapandata.gsi.go.jp/portal/sys/v4/symbols'
const NANAME_ICONS: Record<string, string> = {
  [`${NANAME_ICON_BASE}/181.png`]: 'naname-181',
  [`${NANAME_ICON_BASE}/184.png`]: 'naname-184',
  [`${NANAME_ICON_BASE}/185.png`]: 'naname-185',
  [`${NANAME_ICON_BASE}/186.png`]: 'naname-186',
  // データ側は http:// で配信されているため、両方をキーに持たせて取りこぼさない。
  'http://cyberjapandata.gsi.go.jp/portal/sys/v4/symbols/181.png': 'naname-181',
  'http://cyberjapandata.gsi.go.jp/portal/sys/v4/symbols/184.png': 'naname-184',
  'http://cyberjapandata.gsi.go.jp/portal/sys/v4/symbols/185.png': 'naname-185',
  'http://cyberjapandata.gsi.go.jp/portal/sys/v4/symbols/186.png': 'naname-186',
}

const SUICHOKU_ICONS: Record<string, string> = {
  'https://maps.gsi.go.jp/portal/sys/v4/symbols/081.png': 'suichoku-081',
  'http://maps.gsi.go.jp/portal/sys/v4/symbols/081.png': 'suichoku-081',
}

/**
 * 収録レイヤー。パネルはこの配列順（グループ単位でまとめて）表示する。
 * 地図の重なり順は z（大きいほど前面）で決まる。
 */
export const LAYERS: LayerDef[] = [
  // ===== 震源・揺れ =====
  {
    kind: 'geojson',
    render: 'point',
    key: 'epicenter',
    name: '震源（震央）',
    group: '震源・揺れ',
    on: true,
    opacity: 1,
    // 他のどのレイヤーよりも前面に置く
    z: 1000,
    data: {
      type: 'FeatureCollection',
      features: [
        {
          type: 'Feature',
          geometry: { type: 'Point', coordinates: EPICENTER },
          properties: {
            発生日時: '2026年7月28日 16時27分頃',
            震央地名: '熊本県熊本地方',
            深さ: '16km',
            規模: 'M7.1（気象庁マグニチュード、暫定値）',
            最大震度: '7（宇城市・氷川町）',
            震源断層: '日奈久断層帯（高野－白旗区間・日奈久区間）沿い、長さ約30km',
          },
        },
      ],
    },
    // フォント（グリフ）に依存させないため、記号ではなく円2枚で描く。
    circle: [
      { radius: 11, color: 'rgba(210,0,40,0.18)', strokeColor: 'rgba(255,255,255,0.95)', strokeWidth: 2 },
      { radius: 5, color: 'rgba(210,0,40,1)', strokeColor: 'rgba(255,255,255,0.95)', strokeWidth: 1.5 },
    ],
    legend: [{ label: '震央', color: '#d20028', shape: 'dot' }],
    attribution: JMA_ATTR,
    desc:
      '気象庁が発表した震央の位置（暫定値）。2026年7月28日16時27分頃、熊本県熊本地方の深さ16kmで M7.1。' +
      '最大震度7を宇城市と氷川町で観測した。震源断層は日奈久断層帯に沿って長さ約30km。',
  },
  {
    kind: 'raster',
    key: 'jma-shindo',
    name: '推計震度分布（250mメッシュ）',
    group: '震源・揺れ',
    on: true,
    opacity: 0.65,
    z: 10,
    // 気象庁は1次メッシュごとの800×800px PNG で配信している（CORS は * だが、
    // image ソースで並べると緯度方向に歪むため、GDAL で再投影してタイル化して同梱）。
    // 生成は tools/fetch_jma_shindo_tiles.py。
    tiles: [`${import.meta.env.BASE_URL}data/jma_shindo/{z}/{x}/{y}.png`],
    minzoom: 5,
    maxzoom: 11,
    tileSize: 256,
    legend: SHINDO_LEGEND,
    attribution: JMA_ATTR,
    desc:
      '気象庁の推計震度分布図（250mメッシュ）。観測された震度と地盤の増幅特性から推計した値で、実測震度ではない。' +
      'いずれかの観測点で震度5弱以上を観測したときに、地震発生後15分程度で作成・提供される。' +
      '2026年7月28日16時27分の本震（M7.1、最大計測震度6.6）のもの。' +
      '図に塗られているのは震度4以上だけで、震度1〜3の範囲は含まれない。' +
      '配色は防災科研 J-RISQ のものに置き換えてあり、気象庁の凡例とは色が異なる（震度の値は気象庁のまま）。' +
      'z11までのタイルを同梱しており、それ以上のズームは拡大表示になる。',
  },

  // ===== 人口 =====
  {
    kind: 'pmtiles',
    key: 'pop-mesh',
    name: '夜間人口（国勢調査2020 125mメッシュ）',
    group: '人口',
    on: false,
    // 階級色のコントラストは不透明度100%で検証しているため、下げすぎると
    // 設計した段差が背景に溶けて潰れる。また 3D では半透明の柱が重なると
    // 前後が混ざって読めなくなる（MapLibre は半透明の押し出しを深度順に描かない）。
    // 基図がうっすら見える範囲で高めに取る。
    opacity: 0.9,
    z: 15,
    url: `${import.meta.env.BASE_URL}data/census/pop_mesh125.pmtiles`,
    sourceLayer: 'pop_mesh',
    prop: 'pop',
    minzoom: 9,
    maxzoom: 14,
    /**
     * 逐次パレット（1色相・明度単調）。OKLCH の色相310°を保ち、明度を 0.80→0.44 で
     * 等間隔に落として彩度を中間で最大にしたもの。
     *
     * 色相を紫〜マゼンタ帯にしているのは、他レイヤーと衝突しない唯一の帯だから。
     * 推計震度が使う色相（およそ10/25/60/100/120/150/180/250）と活断層線の青（260）に
     * 挟まれた空きが 290〜340 しかなく、その中央付近が310°。
     *
     * 以前は ColorBrewer の Purples をそのまま使っていたが、逐次パレットの検査で
     * 2項目落ちていた。最も薄い2階級の明度差が 0.056（下限0.06未満）で見分けられず、
     * 最も薄い色は淡色背景に対して 1.13:1（下限2:1未満）でほぼ見えなかった。
     * このランプは明度単調・隣接ΔL・薄端コントラスト・単一色相の4項目すべてを満たし、
     * 薄端 2.11:1（淡色）/ 7.72:1（暗）、濃端 7.38:1（淡色）/ 2.20:1（暗）で、
     * 淡色・写真・ダークのどの背景でも消えない。
     *
     * 階級の区切りは対象域 352,267メッシュの実分布に合わせている。
     * 当初は 1/10/30/100/300/1000 で切っていたが、これは分布と噛み合っておらず、
     * 最も薄い階級だけで45.0%、上位2階級は合わせて0.65%（1000人以上は6メッシュ）
     * しか入らなかった。ランプの濃い側がほぼ使われず、地図の7割が薄い2色になって
     * 「どこに人が多いか」が読めない状態だった。
     * 現在の区切りでの占有率は 25.2 / 30.7 / 21.2 / 14.5 / 7.4 / 1.0 %。
     */
    steps: [
      { min: 1, color: '#cb9fec', label: '1〜4人' },
      { min: 5, color: '#bf81eb', label: '5〜14人' },
      { min: 15, color: '#b067e1', label: '15〜39人' },
      { min: 40, color: '#9d53cc', label: '40〜99人' },
      { min: 100, color: '#8649ad', label: '100〜249人' },
      { min: 250, color: '#6c4288', label: '250人以上' },
    ],
    // 立体表示（右下の 2D/3D で切替）。1人あたり5mで、色に加えて高さでも量が読める。
    extrude: { metersPerUnit: 5 },
    attribution: ESTAT_ATTR,
    popup: {
      rows: ['pop', 'pop65', 'pop75'],
      labels: { pop: '総人口', pop65: '65歳以上', pop75: '75歳以上' },
    },
    desc:
      '令和2年（2020年）国勢調査の125mメッシュ別人口（夜間人口）。揺れた範囲にどれだけの人が住んでいるかを見るためのもの。' +
      '右下の「3D」で立体表示に切り替えると、色に加えて高さでも人口が読める（1人あたり5m）。' +
      'ズーム9〜14で表示し、低ズームでは隣接メッシュを統合して人口を合算しているため、' +
      '1区画の値と3Dの高さが125mメッシュ1つ分より大きくなることがある。拡大するほど正確。' +
      '65歳以上・75歳以上の人口はクリックで確認できる。',
  },

  // ===== 被害状況 =====
  {
    kind: 'geojson',
    render: 'polygon',
    key: 'syamen',
    name: '斜面崩壊・土石流・堆積分布',
    group: '被害状況',
    on: false,
    opacity: 1,
    z: 40,
    // 地理院地図の cocotile 方式（maxNativeZoom=2）のため、
    // 八代地区を含む z=2 タイル 1 枚に全地物が入っている。
    data: 'https://maps.gsi.go.jp/xyz/20260729kumamoto_syamenhoukai_dosekiryu_taiseki_yatsushiro/2/3/1.geojson',
    legendImage: 'https://maps.gsi.go.jp/legend/20260729kumamoto_syamenhoukai_dosekiryu_taiseki_legend.png',
    attribution: GSI_ATTR,
    desc:
      '国土地理院が7月29日撮影の空中写真（正射画像）を判読して作成した、本地震により生じたと考えられる斜面崩壊・土石流・堆積箇所。' +
      '現地調査は行われていないため、実際に崩壊した箇所が表示されていない場合や、本地震によらない箇所を含む場合がある。' +
      '長さまたは幅がおおむね30m以上のものを表示。2026年7月29日23時50分作成。',
  },

  // ===== 空中写真 =====
  {
    kind: 'raster',
    key: 'ortho',
    name: '正射画像（速報）八代地区 7/29撮影',
    group: '空中写真',
    on: false,
    opacity: 1,
    z: 20,
    tiles: ['https://maps.gsi.go.jp/xyz/20260729kumamoto_yatsushiro_0729do_sokuho/{z}/{x}/{y}.png'],
    minzoom: 10,
    maxzoom: 18,
    tileSize: 256,
    // 判読範囲ポリゴン（斜面崩壊分布データに含まれる #3388ff の地物）の実測 bbox。
    // 撮影範囲とほぼ一致するので、これを外れたタイルは取りに行かない。
    bounds: [130.4310, 32.2444, 130.7714, 32.5895],
    attribution: GSI_ATTR,
    desc:
      '空中写真から自動処理により作成した正射画像。自動処理のため構造物等に歪み・ズレ・不連続が生じて見える場合があり、' +
      'また雲の影響で地表が見えにくい場合がある。',
  },
  {
    kind: 'geojson',
    render: 'point',
    key: 'suichoku',
    name: '垂直写真（速報）八代地区 7/29撮影',
    group: '空中写真',
    on: false,
    opacity: 1,
    z: 50,
    data: 'https://maps.gsi.go.jp/xyz/20260729kumamoto_yatsushiro_0729suichoku_sokuho/2/3/1.geojson',
    icons: SUICHOKU_ICONS,
    iconFallback: 'suichoku-081',
    attribution: GSI_ATTR,
    popup: { title: '写真番号', rows: ['写真番号', '撮影日', '画像', '備考'], html: ['画像', '備考'] },
    desc:
      '撮影位置に写真をひも付けた点データ。アイコンをクリックするとサムネイルが開き、さらにクリックすると拡大表示できる。' +
      '速報用写真のため通常の航空カメラによる撮影画像より画質が低く、雲の影響で地上が見えにくい場合がある。',
  },
  {
    kind: 'geojson',
    render: 'point',
    key: 'naname',
    name: '斜め写真 八代地区 7/29撮影',
    group: '空中写真',
    on: false,
    opacity: 1,
    z: 60,
    data: 'https://maps.gsi.go.jp/xyz/20260729kumamoto_yatsushiro_0729naname/2/3/1.geojson',
    icons: NANAME_ICONS,
    iconFallback: 'naname-185',
    attribution: GSI_ATTR,
    popup: { title: '写真番号', rows: ['写真番号', '撮影日時', '画像', '備考'], html: ['画像', '備考'] },
    desc:
      'アイコンはカメラのシャッターを切った位置に置かれ、向きは撮影方向の概略を示す。' +
      'クリックするとサムネイルが開き、さらにクリックすると拡大表示できる。雲の影響で地上が見えにくい場合がある。',
  },

  // ===== 地形・活断層 =====
  {
    kind: 'geojson',
    render: 'polygon',
    key: 'active-fault',
    name: '全国の主要活断層帯',
    group: '地形・活断層',
    on: true,
    opacity: 1,
    z: 32,
    // 配信元 https://maps.gsi.go.jp/xyz/active_fault/2/3/1.geojson は CORS を返すので
    // 直接参照もできるが、整形済み2.36MBで gzip も返らないため圧縮して同梱している。
    // 生成は tools/build_active_fault.py。
    data: `${import.meta.env.BASE_URL}data/herp/active_fault.geojson`,
    legend: [{ label: '主要活断層帯', color: '#3388ff', shape: 'line' }],
    attribution: HERP_ATTR,
    // 名称・説明は断層線ではなく、名称表示用の不可視ポリゴン（163面）側が持っている。
    // 名称はタイトルに出るので、表には description（区間名や評価上の注記）だけ出す。
    popup: { title: 'name', rows: ['description'], html: ['description'], labels: { description: '備考' } },
    desc:
      '地震調査研究推進本部が長期評価の対象としている全国の主要活断層帯。' +
      '本地震で活動したとみられる日奈久断層帯も含む。断層線をクリックしても名称は出ず、' +
      '断層帯の範囲（名称表示用の不可視の領域）をクリックすると名称と評価の説明が出る。' +
      '全国規模のデータなので、拡大して詳細な位置を見るときは「活断層図（都市圏活断層図）」を使う。',
  },
  {
    kind: 'raster',
    key: 'afm',
    name: '活断層図（都市圏活断層図）',
    group: '地形・活断層',
    on: false,
    opacity: 0.85,
    z: 30,
    tiles: ['https://maps.gsi.go.jp/xyz/afm/{z}/{x}/{y}.png'],
    maxzoom: 16,
    tileSize: 256,
    attribution: GSI_ATTR,
    desc:
      '国土地理院の都市圏活断層図。本地震で活動したとみられる日奈久断層帯（高野－白旗区間・日奈久区間）を含む。' +
      '「阿蘇」「熊本改訂版」「八代改訂版」「日奈久」の各図が公開されており、GeoTIFF も配布されている。',
  },
]

/** パネルに出すグループの順序。LAYERS に無いグループは無視される。 */
export const GROUPS = ['震源・揺れ', '人口', '被害状況', '空中写真', '地形・活断層'] as const

export const layerById = (key: string): LayerDef | undefined => LAYERS.find((l) => l.key === key)

// ---- ソース定義 ----
export function sourceFor(def: LayerDef): SourceSpecification {
  if (def.kind === 'pmtiles') {
    return {
      type: 'vector',
      url: `pmtiles://${def.url}`,
      ...(def.minzoom !== undefined ? { minzoom: def.minzoom } : {}),
      ...(def.maxzoom !== undefined ? { maxzoom: def.maxzoom } : {}),
      attribution: def.attribution,
    }
  }
  if (def.kind === 'raster' || def.kind === 'wms') {
    return {
      type: 'raster',
      tiles: def.kind === 'wms' ? [def.url] : def.tiles,
      tileSize: def.tileSize ?? 256,
      ...(def.minzoom !== undefined ? { minzoom: def.minzoom } : {}),
      ...(def.maxzoom !== undefined ? { maxzoom: def.maxzoom } : {}),
      ...(def.kind === 'raster' && def.bounds ? { bounds: def.bounds } : {}),
      attribution: def.attribution,
    }
  }
  return { type: 'geojson', data: def.data, attribution: def.attribution }
}

// ---- 描画レイヤー定義 ----
// 1つの LayerDef が複数の MapLibre レイヤーになることがある（面＝塗り＋輪郭）。
// 返り値の配列順がそのまま addLayer 順（後ろほど前面）。

/**
 * 地理院地図の GeoJSON は、地物ごとに Leaflet 用のスタイル属性
 * （_fillColor / _color / _fillOpacity / _weight）を持っている。
 * 配色を独自に決め直すのではなく、その値をデータ駆動でそのまま使う。
 */
const featureFill: ExpressionSpecification = ['coalesce', ['get', '_fillColor'], '#ff3232']
const featureStroke: ExpressionSpecification = ['coalesce', ['get', '_color'], '#ff0000']

/** 地物の _fillOpacity と、UI スライダーの不透明度を掛け合わせる。 */
function fillOpacityExpr(opacity: number): ExpressionSpecification {
  return ['*', ['to-number', ['coalesce', ['get', '_fillOpacity'], 0.5]], opacity]
}
function lineOpacityExpr(opacity: number): ExpressionSpecification {
  return ['*', ['to-number', ['coalesce', ['get', '_opacity'], 1]], opacity]
}
const lineWidthExpr: ExpressionSpecification = ['to-number', ['coalesce', ['get', '_weight'], 1]]

/** 階級区分の step 式。steps は min の昇順。 */
function stepColor(def: ChoroplethDef): ExpressionSpecification {
  const [first, ...rest] = def.steps
  const expr: unknown[] = ['step', ['to-number', ['get', def.prop], 0], first.color]
  for (const s of rest) expr.push(s.min, s.color)
  return expr as ExpressionSpecification
}

export function mapLayersFor(def: LayerDef): LayerSpecification[] {
  const src = def.key
  const zoom = {
    ...(def.minzoom !== undefined ? { minzoom: def.minzoom } : {}),
    ...(def.maxzoom !== undefined ? { maxzoom: def.maxzoom } : {}),
  }

  if (def.kind === 'raster' || def.kind === 'wms') {
    const l: RasterLayerSpecification = {
      id: `${src}--raster`,
      type: 'raster',
      source: src,
      paint: { 'raster-opacity': def.opacity },
    }
    return [l]
  }

  if (def.kind === 'pmtiles') {
    // 先頭階級の下限未満（人口ゼロ等）は描かないよう filter で落とす。
    const filter: ExpressionSpecification = [
      '>=',
      ['to-number', ['get', def.prop], -1],
      def.steps[0].min,
    ]
    if (def.extrude) {
      // 立体化するレイヤーは 2D でも fill-extrusion のまま高さ0で描く。
      // レイヤー種別を切り替えると載せ直しが必要になり、状態管理が増えるため。
      const l: FillExtrusionLayerSpecification = {
        id: `${src}--fill`,
        type: 'fill-extrusion',
        source: src,
        'source-layer': def.sourceLayer,
        ...zoom,
        filter,
        paint: {
          'fill-extrusion-color': stepColor(def),
          'fill-extrusion-opacity': def.opacity,
          'fill-extrusion-base': 0,
          'fill-extrusion-height': 0,
        },
      }
      return [l]
    }
    const l: FillLayerSpecification = {
      id: `${src}--fill`,
      type: 'fill',
      source: src,
      'source-layer': def.sourceLayer,
      ...zoom,
      filter,
      paint: { 'fill-color': stepColor(def), 'fill-opacity': def.opacity },
    }
    return [l]
  }

  if (def.render === 'polygon') {
    const fill: FillLayerSpecification = {
      id: `${src}--fill`,
      type: 'fill',
      source: src,
      filter: ['match', ['geometry-type'], ['Polygon'], true, false],
      ...zoom,
      paint: { 'fill-color': featureFill, 'fill-opacity': fillOpacityExpr(def.opacity) },
    }
    const line: LineLayerSpecification = {
      id: `${src}--line`,
      type: 'line',
      source: src,
      ...zoom,
      paint: {
        'line-color': featureStroke,
        'line-width': lineWidthExpr,
        'line-opacity': lineOpacityExpr(def.opacity),
      },
    }
    return [fill, line]
  }

  // point
  const layers: LayerSpecification[] = []
  for (const [i, c] of circleSpecs(def).entries()) {
    const circle: CircleLayerSpecification = {
      id: circleId(src, i),
      type: 'circle',
      source: src,
      ...zoom,
      paint: {
        'circle-radius': c.radius,
        'circle-color': c.color,
        'circle-stroke-color': c.strokeColor ?? 'rgba(0,0,0,0)',
        'circle-stroke-width': c.strokeWidth ?? 0,
        'circle-opacity': def.opacity,
        'circle-stroke-opacity': def.opacity,
      },
    }
    layers.push(circle)
  }
  if (def.icons && def.iconFallback) {
    const cases: string[] = []
    for (const [url, id] of Object.entries(def.icons)) cases.push(url, id)
    const iconExpr = ['match', ['coalesce', ['get', '_iconUrl'], ''], ...cases, def.iconFallback]
    const sym: SymbolLayerSpecification = {
      id: `${src}--icon`,
      type: 'symbol',
      source: src,
      ...zoom,
      layout: {
        'icon-image': iconExpr as unknown as ExpressionSpecification,
        'icon-size': def.iconSize ?? 1,
        'icon-allow-overlap': true,
        'icon-ignore-placement': true,
      },
      paint: { 'icon-opacity': def.opacity },
    }
    layers.push(sym)
  }
  return layers
}

const circleId = (src: string, i: number): string => `${src}--c${i}`

/**
 * 点レイヤーの円マーカー。
 * circle 指定があればそれを使い、無ければアイコンの下敷き用に既定の円を1枚返す
 * （アイコン画像の読み込みに失敗しても位置が分かるようにするため）。
 */
function circleSpecs(def: GeoJsonPointDef): CircleSpec[] {
  if (def.circle?.length) return def.circle
  return [{ radius: 5, color: 'rgba(255,255,255,0.9)', strokeColor: 'rgba(0,90,200,0.9)', strokeWidth: 1 }]
}

/** 不透明度スライダーの反映。レイヤー種別ごとに効かせる paint プロパティが違う。 */
export function opacityUpdates(def: LayerDef, v: number): { id: string; prop: string; value: unknown }[] {
  const src = def.key
  if (def.kind === 'raster' || def.kind === 'wms') {
    return [{ id: `${src}--raster`, prop: 'raster-opacity', value: v }]
  }
  if (def.kind === 'pmtiles') {
    const prop = def.extrude ? 'fill-extrusion-opacity' : 'fill-opacity'
    return [{ id: `${src}--fill`, prop, value: v }]
  }
  if (def.render === 'polygon') {
    return [
      { id: `${src}--fill`, prop: 'fill-opacity', value: fillOpacityExpr(v) },
      { id: `${src}--line`, prop: 'line-opacity', value: lineOpacityExpr(v) },
    ]
  }
  const out = circleSpecs(def).flatMap((_, i) => [
    { id: circleId(src, i), prop: 'circle-opacity', value: v },
    { id: circleId(src, i), prop: 'circle-stroke-opacity', value: v },
  ])
  if (def.icons) out.push({ id: `${src}--icon`, prop: 'icon-opacity', value: v })
  return out
}

/** 立体表示できるレイヤーか。 */
export const isExtrudable = (def: LayerDef): boolean => def.kind === 'pmtiles' && !!def.extrude

/**
 * 立体表示の ON/OFF に伴う paint 更新。
 * 2D では高さ0にして、塗りと同じ見た目に戻す。
 */
export function extrusionUpdates(def: LayerDef, on: boolean): { id: string; prop: string; value: unknown }[] {
  if (def.kind !== 'pmtiles' || !def.extrude) return []
  const prop = def.extrude.prop ?? def.prop
  const height: ExpressionSpecification | number = on
    ? (['*', ['to-number', ['coalesce', ['get', prop], 0], 0], def.extrude.metersPerUnit] as ExpressionSpecification)
    : 0
  return [{ id: `${def.key}--fill`, prop: 'fill-extrusion-height', value: height }]
}

/** クリック判定に使うレイヤー id（ラスタは対象外）。 */
export function queryableLayerIds(def: LayerDef): string[] {
  if (def.kind === 'raster' || def.kind === 'wms') return []
  if (def.kind === 'pmtiles') return [`${def.key}--fill`]
  if (def.render === 'polygon') return [`${def.key}--fill`, `${def.key}--line`]
  const ids = circleSpecs(def).map((_, i) => circleId(def.key, i))
  return def.icons ? [`${def.key}--icon`, ...ids] : ids
}

/** 事前に map.addImage で登録しておくアイコン。http は https に寄せる。 */
export function iconsToLoad(def: LayerDef): { id: string; url: string }[] {
  if (def.kind !== 'geojson' || def.render !== 'point' || !def.icons) return []
  const seen = new Map<string, string>()
  for (const [url, id] of Object.entries(def.icons)) {
    if (!seen.has(id)) seen.set(id, url.replace(/^http:\/\//, 'https://'))
  }
  return [...seen].map(([id, url]) => ({ id, url }))
}

// ---- ポップアップ ----
function esc(s: string): string {
  return s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c] as string)
}

/**
 * 属性表示。地理院地図の写真レイヤーは属性値そのものが HTML 断片（サムネイル＋リンク）なので、
 * popup.html に挙げた属性だけはエスケープせずに描く。
 * それ以外はエスケープし、`_` 始まりの内部スタイル属性は出さない。
 */
export function popupHtml(def: LayerDef, props: Record<string, unknown>): string {
  const spec = def.kind === 'geojson' || def.kind === 'pmtiles' ? def.popup : undefined
  const rawHtml = new Set(spec?.html ?? [])
  const keys = spec?.rows ?? Object.keys(props).filter((k) => !k.startsWith('_'))

  const title = spec?.title ? String(props[spec.title] ?? '') : ''
  const rows = keys
    .filter((k) => {
      const v = props[k]
      return v !== undefined && v !== null && v !== ''
    })
    .map((k) => {
      const v = String(props[k])
      const label = spec?.labels?.[k] ?? k
      return `<dt>${esc(label)}</dt><dd>${rawHtml.has(k) ? v : esc(v)}</dd>`
    })
    .join('')

  return (
    `<div class="pp-title">${esc(title || def.name)}</div>` +
    `<div class="pp-sub">${esc(def.name)}</div>` +
    (rows ? `<dl class="pp-dl">${rows}</dl>` : '')
  )
}

/**
 * パネルに出す凡例。
 * 階級区分レイヤーは steps から組み立てる（凡例と塗り分けが必ず一致するようにするため）。
 */
export function legendFor(def: LayerDef): LegendItem[] {
  if (def.kind === 'pmtiles') {
    return def.steps.map((s) => ({ label: s.label, color: s.color, outline: 'rgba(0,0,0,0.25)' }))
  }
  return def.legend ?? []
}
