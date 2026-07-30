import type {
  CircleLayerSpecification,
  ExpressionSpecification,
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
const NIED_ATTR =
  '<a href="https://www.j-risq.bosai.go.jp/" target="_blank" rel="noopener">防災科学技術研究所 J-RISQ地震速報</a>'

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
}

/** GeoJSON（面） */
interface GeoJsonPolygonDef extends LayerBase {
  kind: 'geojson'
  render: 'polygon'
  data: string
  minzoom?: number
  maxzoom?: number
  popup?: PopupSpec
}

/** GeoJSON（点・アイコン） */
interface GeoJsonPointDef extends LayerBase {
  kind: 'geojson'
  render: 'point'
  data: string
  minzoom?: number
  maxzoom?: number
  popup?: PopupSpec
  /**
   * アイコン画像。キーは地物の `_iconUrl` の値そのまま、値は MapLibre に登録する image id。
   * `_iconUrl` は http:// で配信されている場合があるため、読み込み時に https へ寄せる。
   */
  icons: Record<string, string>
  /** icons に一致しなかったときに使う image id */
  iconFallback: string
  /** アイコンの表示倍率 */
  iconSize?: number
}

export type LayerDef = RasterDef | WmsDef | GeoJsonPolygonDef | GeoJsonPointDef

// ---- 防災科研 J-RISQ 推計震度分布 ----
/**
 * 対象レポート。J-RISQ は同一地震に対して速報→最終報と複数の報を出すため、
 * 差し替えるときはここだけ変える。
 * R-20260728162724-0145-00001 = 2026/07/28 16:40:13 発表（Ver.8 最終報）。
 */
const JRISQ_REPORT = { triggerid: 'R-20260728162724', report: '0145', ana: '00001' }

/**
 * J-RISQ の WMS GetMap URL を組み立てる。
 * bbox は MapLibre がタイルごとに置換するプレースホルダなので、
 * URLSearchParams にかけて `{` `}` をエスケープされないよう後ろに直接つなぐ。
 */
export function jrisqWms(wmsLayer: string): string {
  const q = new URLSearchParams({
    service: 'WMS',
    version: '1.1.1',
    request: 'GetMap',
    layers: wmsLayer,
    srs: 'EPSG:3857',
    width: '256',
    height: '256',
    transparent: 'true',
    format: 'image/png',
    ...JRISQ_REPORT,
  })
  return `https://www.j-risq.bosai.go.jp/report/wms?${q.toString()}&bbox={bbox-epsg-3857}`
}

/**
 * 推計震度分布の WMS 直参照 URL（本番では使っていない）。
 *
 * MapLibre の WMS の作り方そのものは
 * https://maplibre.org/maplibre-gl-js/docs/examples/add-a-wms-source/ のとおりで、
 * この URL を raster ソースの tiles に渡せば動く形になっている。
 * ただし J-RISQ の WMS は Access-Control-Allow-Origin を返さないため、
 * GitHub Pages のような別オリジンからは全リクエストが遮断される
 * （実測: 90リクエストすべて net::ERR_FAILED）。
 * そのため本番の 'jrisq-shindo' レイヤーは、tools/fetch_jrisq_tiles.py で
 * 焼いた同梱タイルを参照している。CORS を返す WMS を足すときは
 * kind: 'wms' でこの形の URL をそのまま渡せばよい。
 */
export const JRISQ_WMS_URL = jrisqWms('GSI_M250')

/**
 * 推計震度の配色。J-RISQ の GetLegendGraphic
 * （request=GetLegendGraphic&layer=GSI_M250）の実物から採色した10段階。
 * 気象庁の震度配色とは異なる独自パレットなので、実測値をそのまま持つ。
 */
const SHINDO_LEGEND: LegendItem[] = [
  { label: '推定震度7', color: '#950d05' },
  { label: '推定震度6強', color: '#f45178' },
  { label: '推定震度6弱', color: '#faaa46' },
  { label: '推定震度5強', color: '#f7f618' },
  { label: '推定震度5弱', color: '#96d050' },
  { label: '推定震度4', color: '#1e973d' },
  { label: '推定震度3', color: '#31ada8' },
  { label: '推定震度2', color: '#447eb8' },
  { label: '推定震度1', color: '#96b4d3' },
  { label: '推定震度0', color: '#ffffff', outline: 'rgba(0,0,0,0.5)' },
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
  // ===== 揺れ =====
  {
    kind: 'raster',
    key: 'jrisq-shindo',
    name: '推計震度分布（250mメッシュ）',
    group: '揺れ',
    on: false,
    opacity: 0.65,
    z: 10,
    // J-RISQ の WMS は CORS ヘッダーを返さないため、GitHub Pages から直接は読めない。
    // tools/fetch_jrisq_tiles.py で確定レポートをタイル化して同梱したものを使う。
    // 経緯は上の JRISQ_WMS_URL のコメントを参照。
    tiles: [`${import.meta.env.BASE_URL}data/jrisq/GSI_M250/{z}/{x}/{y}.png`],
    minzoom: 5,
    maxzoom: 11,
    tileSize: 256,
    legend: SHINDO_LEGEND,
    attribution: NIED_ATTR,
    desc:
      '防災科学技術研究所 J-RISQ地震速報による、250mメッシュごとの推計震度。' +
      '観測点の震度と地盤の増幅特性から推定した値で、実測震度ではない。' +
      '2026/07/28 16:40:13発表（Ver.8 最終報）。' +
      'z11までのタイルを同梱しており、それ以上のズームは拡大表示になる。',
  },

  // ===== 被害状況 =====
  {
    kind: 'geojson',
    render: 'polygon',
    key: 'syamen',
    name: '斜面崩壊・土石流・堆積分布',
    group: '被害状況',
    on: true,
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
    on: true,
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
export const GROUPS = ['揺れ', '被害状況', '空中写真', '地形・活断層'] as const

export const layerById = (key: string): LayerDef | undefined => LAYERS.find((l) => l.key === key)

// ---- ソース定義 ----
export function sourceFor(def: LayerDef): SourceSpecification {
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
  const iconExpr = (): ExpressionSpecification => {
    const cases: string[] = []
    for (const [url, id] of Object.entries(def.icons)) cases.push(url, id)
    return ['match', ['coalesce', ['get', '_iconUrl'], ''], ...cases, def.iconFallback] as unknown as ExpressionSpecification
  }
  // アイコン画像の読み込みに失敗しても位置が分かるよう、円を下敷きに置く。
  const halo: CircleLayerSpecification = {
    id: `${src}--halo`,
    type: 'circle',
    source: src,
    ...zoom,
    paint: {
      'circle-radius': 5,
      'circle-color': 'rgba(255,255,255,0.9)',
      'circle-stroke-color': 'rgba(0,90,200,0.9)',
      'circle-stroke-width': 1,
      'circle-opacity': def.opacity,
      'circle-stroke-opacity': def.opacity,
    },
  }
  const sym: SymbolLayerSpecification = {
    id: `${src}--icon`,
    type: 'symbol',
    source: src,
    ...zoom,
    layout: {
      'icon-image': iconExpr(),
      'icon-size': def.iconSize ?? 1,
      'icon-allow-overlap': true,
      'icon-ignore-placement': true,
    },
    paint: { 'icon-opacity': def.opacity },
  }
  return [halo, sym]
}

/** 不透明度スライダーの反映。レイヤー種別ごとに効かせる paint プロパティが違う。 */
export function opacityUpdates(def: LayerDef, v: number): { id: string; prop: string; value: unknown }[] {
  const src = def.key
  if (def.kind === 'raster' || def.kind === 'wms') {
    return [{ id: `${src}--raster`, prop: 'raster-opacity', value: v }]
  }
  if (def.render === 'polygon') {
    return [
      { id: `${src}--fill`, prop: 'fill-opacity', value: fillOpacityExpr(v) },
      { id: `${src}--line`, prop: 'line-opacity', value: lineOpacityExpr(v) },
    ]
  }
  return [
    { id: `${src}--halo`, prop: 'circle-opacity', value: v },
    { id: `${src}--halo`, prop: 'circle-stroke-opacity', value: v },
    { id: `${src}--icon`, prop: 'icon-opacity', value: v },
  ]
}

/** クリック判定に使うレイヤー id（ラスタは対象外）。 */
export function queryableLayerIds(def: LayerDef): string[] {
  if (def.kind === 'raster' || def.kind === 'wms') return []
  return def.render === 'polygon' ? [`${def.key}--fill`, `${def.key}--line`] : [`${def.key}--icon`, `${def.key}--halo`]
}

/** 事前に map.addImage で登録しておくアイコン。http は https に寄せる。 */
export function iconsToLoad(def: LayerDef): { id: string; url: string }[] {
  if (def.kind !== 'geojson' || def.render !== 'point') return []
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
  const spec = def.kind === 'geojson' ? def.popup : undefined
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
      return `<dt>${esc(k)}</dt><dd>${rawHtml.has(k) ? v : esc(v)}</dd>`
    })
    .join('')

  return (
    `<div class="pp-title">${esc(title || def.name)}</div>` +
    `<div class="pp-sub">${esc(def.name)}</div>` +
    (rows ? `<dl class="pp-dl">${rows}</dl>` : '')
  )
}

/** レイヤートグルの色ドット用の代表色。 */
export function dotColor(def: LayerDef): string {
  if (def.legend?.length) return def.legend[0].color
  if (def.kind === 'geojson') return def.render === 'polygon' ? '#ff3232' : '#0a64c8'
  return 'rgba(150,150,150,0.9)'
}
