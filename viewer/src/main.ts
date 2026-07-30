import maplibregl from 'maplibre-gl'
import { Protocol } from 'pmtiles'
import 'maplibre-gl/dist/maplibre-gl.css'

import { getBasemapStyle, type Basemap } from './basemap'
import {
  GROUPS,
  LAYERS,
  TERRAIN,
  type LayerDef,
  iconsToLoad,
  isExtrudable,
  legendFor,
  mapLayersFor,
  opacityUpdates,
  popupHtml,
  queryableLayerIds,
  sourceFor,
  terrainSource,
} from './layers'
import { applyThemeAttr, initialTheme, type Theme } from './theme'
import './style.css'

/**
 * 初期表示。既定で ON のレイヤー（震源・推計震度分布・主要活断層帯）が
 * まとめて見える広さにしてある。八代地区の空中写真もこの範囲に収まる。
 */
const INITIAL_CENTER: [number, number] = [130.7, 32.55]
const INITIAL_ZOOM = 9.3

let theme: Theme = initialTheme()
let base: Basemap = 'pale'
applyThemeAttr(theme)

const isMobile = window.matchMedia('(max-width: 640px)').matches
const DEBUG = new URLSearchParams(location.search).has('debug')

// 背景の淡色地図（地理院 最適化ベクトルタイル）は PMTiles で配信されているため、
// スタイルを読み込む前に pmtiles:// プロトコルを登録しておく。
const protocol = new Protocol()
maplibregl.addProtocol('pmtiles', protocol.tile)

const map = new maplibregl.Map({
  container: 'map',
  style: getBasemapStyle(base, theme),
  center: INITIAL_CENTER,
  zoom: INITIAL_ZOOM,
  hash: true,
  attributionControl: false,
  // 既定は60度。3D地形の起伏や人口の柱を横から見たいので上限まで倒せるようにする
  // （MapLibre の上限は85度）。
  maxPitch: 85,
  maxTileCacheSize: isMobile ? 24 : undefined,
  pixelRatio: isMobile ? Math.min(window.devicePixelRatio || 1, 2) : undefined,
})
map.addControl(new maplibregl.NavigationControl({ showCompass: true, visualizePitch: true }), 'top-right')
map.addControl(
  new maplibregl.GeolocateControl({
    positionOptions: { enableHighAccuracy: true },
    trackUserLocation: true,
    showUserLocation: true,
  }),
  'top-right',
)
// 3D地形は MapLibre 標準の TerrainControl（山アイコン）で切り替える。
// ソースは ensureTerrainSource() で常にスタイルへ入れておく。
map.addControl(
  new maplibregl.TerrainControl({ source: TERRAIN.key, exaggeration: TERRAIN.exaggeration }),
  'top-right',
)
map.addControl(new maplibregl.ScaleControl(), 'bottom-left')
map.addControl(new maplibregl.AttributionControl({ compact: true }))

// ---- 診断（?debug） ----
const diagLog: string[] = []
let hudEl: HTMLElement | null = null
function diag(msg: string): void {
  diagLog.push(`${new Date().toISOString().slice(11, 19)} ${msg}`)
  if (diagLog.length > 10) diagLog.shift()
  // eslint-disable-next-line no-console
  console.log('[diag]', msg)
  renderHud()
}
function renderHud(): void {
  if (!DEBUG || !hudEl) return
  const rows = LAYERS.filter((l) => l.on)
    .map((l) => {
      const ids = queryableLayerIds(l).filter((id) => map.getLayer(id))
      const n = ids.length ? map.queryRenderedFeatures({ layers: ids }).length : -1
      return `${l.key}: ${n}`
    })
    .join('  ')
  hudEl.innerHTML =
    `<b>build ${__BUILD_TIME__}</b><br>zoom ${map.getZoom().toFixed(1)}<br>` +
    `<u>rendered features</u><br>${rows || '(none)'}<br><u>log</u><br>${diagLog.join('<br>')}`
}
function initHud(): void {
  if (!DEBUG) return
  hudEl = document.createElement('div')
  hudEl.id = 'diag-hud'
  document.body.append(hudEl)
  map.on('render', () => {
    if (map.areTilesLoaded()) renderHud()
  })
}

// ---- アイコンの登録 ----
// symbol レイヤーは icon-image が未登録だと警告を出して描画されないため、
// レイヤーを載せる前に addImage を済ませる。スタイル差し替えで消えるので毎回やり直す。
const iconPromises = new Map<string, Promise<void>>()
function ensureIcons(def: LayerDef): Promise<void> {
  const list = iconsToLoad(def)
  if (!list.length) return Promise.resolve()
  const load = async (): Promise<void> => {
    await Promise.all(
      list.map(async ({ id, url }) => {
        if (map.hasImage(id)) return
        try {
          const res = await map.loadImage(url)
          if (!map.hasImage(id)) map.addImage(id, res.data)
        } catch {
          diag(`icon load failed: ${id}`)
        }
      }),
    )
  }
  const key = `${def.key}:${base}:${theme}`
  let p = iconPromises.get(key)
  if (!p) {
    p = load()
    iconPromises.set(key, p)
  }
  return p
}

// ---- 立体表示 ----
// 立体化するレイヤーは常に fill-extrusion で高さを入れて載せてある。
// 真上から見ていると高さが分からないので、ONにしたときに水平なら地図を傾ける。
function tiltForExtrusion(): void {
  if (map.getPitch() > 0) return
  map.easeTo({ pitch: map.getTerrain() ? 62 : 48, bearing: -15, duration: 600 })
}

// ---- 3D地形のソース ----
// TerrainControl は setTerrain するだけなので、ソースは常に用意しておく。
// raster-dem は terrain が無効な間タイルを取りに行かないので、置いておく分の負荷は無い。
function ensureTerrainSource(): void {
  if (!map.getSource(TERRAIN.key)) map.addSource(TERRAIN.key, terrainSource())
}

// ---- 重なり順 ----
// z が大きいほど前面。自分より z が大きい既存レイヤーのうち最小のものの直前に挿入する。
// 震源レイヤーは z=1000 なので、常に最前面に留まる。
function beforeIdFor(def: LayerDef): string | undefined {
  const above = LAYERS.filter((l) => l.z > def.z).sort((a, b) => a.z - b.z)
  for (const l of above) {
    const first = mapLayersFor(l)[0]?.id
    if (first && map.getLayer(first)) return first
  }
  return undefined
}

function addLayer(def: LayerDef): void {
  if (!map.getSource(def.key)) map.addSource(def.key, sourceFor(def))
  const specs = mapLayersFor(def)
  if (specs.every((s) => map.getLayer(s.id))) return
  const before = beforeIdFor(def)
  for (const spec of specs) {
    if (map.getLayer(spec.id)) continue
    map.addLayer(spec, before)
  }
  // 立体表示のレイヤーは、傾けないと高さが見えない
  if (isExtrudable(def)) tiltForExtrusion()
}

function ensureLayer(def: LayerDef): void {
  const icons = iconsToLoad(def)
  if (icons.length) {
    // アイコン待ちの間に OFF に戻された場合は載せない
    void ensureIcons(def).then(() => {
      if (def.on) addLayer(def)
    })
    return
  }
  addLayer(def)
}

function removeLayer(def: LayerDef): void {
  for (const spec of mapLayersFor(def)) {
    if (map.getLayer(spec.id)) map.removeLayer(spec.id)
  }
  if (map.getSource(def.key)) map.removeSource(def.key)
}

/** 有効なレイヤーだけを z 順に載せる。無効なものはソースごと持たない＝軽量。 */
function addDataLayers(): void {
  for (const def of [...LAYERS].sort((a, b) => a.z - b.z)) {
    if (def.on) ensureLayer(def)
    else removeLayer(def)
  }
}

// ---- テーマ / 背景 ----
const themeBtn = document.getElementById('theme-btn') as HTMLButtonElement
const renderThemeBtn = (): void => {
  themeBtn.textContent = theme === 'dark' ? '☀️' : '🌙'
}
// ラスタ（写真）↔ベクタ（淡色）の切替は diff 適用が効かないため完全再構築する。
// setStyle 直後は isStyleLoaded() が旧スタイルで true を返すため idle を待つ。
function reloadStyle(): void {
  // スタイルを差し替えるとソースも terrain も消えるので、状態を覚えて戻す
  const terrainWasOn = !!map.getTerrain()
  map.setStyle(getBasemapStyle(base, theme), { diff: false })
  map.once('idle', () => {
    ensureTerrainSource()
    if (terrainWasOn) map.setTerrain({ source: TERRAIN.key, exaggeration: TERRAIN.exaggeration })
    addDataLayers()
  })
}
themeBtn.addEventListener('click', () => {
  theme = theme === 'dark' ? 'light' : 'dark'
  applyThemeAttr(theme)
  renderThemeBtn()
  reloadStyle()
})

const panel = document.getElementById('panel') as HTMLElement
const collapseBtn = document.getElementById('collapse-btn') as HTMLButtonElement
const renderCollapseBtn = (): void => {
  collapseBtn.textContent = panel.classList.contains('collapsed') ? '▾' : '▴'
}
collapseBtn.addEventListener('click', () => {
  panel.classList.toggle('collapsed')
  renderCollapseBtn()
})

// ---- レイヤーパネル ----
const layersDiv = document.getElementById('layers') as HTMLElement

function legendMarkup(def: LayerDef): string {
  if (def.legendImage) {
    return `<img class="lg-img" src="${def.legendImage}" alt="${def.name}の凡例" loading="lazy" />`
  }
  const items = legendFor(def)
  if (!items.length) return ''
  return items
    .map((it) => {
      const border = it.outline ? `border-color:${it.outline}` : ''
      return `<span class="lg-row"><span class="lg-sw lg-${it.shape ?? 'box'}" style="background:${it.color};${border}"></span>${it.label}</span>`
    })
    .join('')
}

function buildPanel(): void {
  for (const group of GROUPS) {
    const defs = LAYERS.filter((l) => l.group === group)
    if (!defs.length) continue

    const head = document.createElement('div')
    head.className = 'group-head'
    head.textContent = group
    layersDiv.append(head)

    for (const def of defs) {
      const item = document.createElement('div')
      item.className = 'layer-item'
      item.dataset.key = def.key

      const label = document.createElement('label')
      label.className = 'toggle'

      const input = document.createElement('input')
      input.type = 'checkbox'
      input.checked = def.on
      input.addEventListener('change', () => setLayerVisible(def, input.checked))

      const sw = document.createElement('span')
      sw.className = 'switch'
      const text = document.createElement('span')
      text.className = 't-label'
      text.textContent = def.name

      const desc = document.createElement('div')
      desc.className = 'layer-desc'
      desc.hidden = true
      desc.textContent = def.desc

      const info = document.createElement('button')
      info.type = 'button'
      info.className = 'info-btn'
      info.textContent = 'i'
      info.setAttribute('aria-label', `${def.name}の説明`)
      info.setAttribute('aria-expanded', 'false')
      info.addEventListener('click', (e) => {
        e.preventDefault()
        e.stopPropagation()
        const open = desc.hidden
        desc.hidden = !open
        info.setAttribute('aria-expanded', String(open))
      })

      label.append(input, sw, text, info)

      const opac = document.createElement('div')
      opac.className = 'layer-opacity'
      opac.hidden = !def.on
      const range = document.createElement('input')
      range.type = 'range'
      range.min = '0'
      range.max = '1'
      range.step = '0.05'
      range.value = String(def.opacity)
      range.setAttribute('aria-label', `${def.name}の不透明度`)
      const val = document.createElement('span')
      val.className = 'op-val'
      val.textContent = `${Math.round(def.opacity * 100)}%`
      range.addEventListener('input', () => {
        const v = Number(range.value)
        val.textContent = `${Math.round(v * 100)}%`
        setLayerOpacity(def, v)
      })
      opac.append(range, val)

      const legend = document.createElement('div')
      legend.className = 'layer-legend'
      legend.innerHTML = legendMarkup(def)
      legend.hidden = !def.on || !legend.innerHTML

      item.append(label, desc, opac, legend)
      layersDiv.append(item)
    }
  }
}

function setLayerVisible(def: LayerDef, on: boolean): void {
  def.on = on
  if (on) ensureLayer(def)
  else removeLayer(def)
  const item = layersDiv.querySelector<HTMLElement>(`.layer-item[data-key="${def.key}"]`)
  item?.querySelector<HTMLElement>('.layer-opacity')?.toggleAttribute('hidden', !on)
  const lg = item?.querySelector<HTMLElement>('.layer-legend')
  if (lg) lg.hidden = !on || !lg.innerHTML
}

function setLayerOpacity(def: LayerDef, v: number): void {
  def.opacity = v
  for (const u of opacityUpdates(def, v)) {
    if (map.getLayer(u.id)) map.setPaintProperty(u.id, u.prop, u.value as never)
  }
}

function setAll(on: boolean): void {
  for (const def of LAYERS) {
    if (def.on === on) continue
    const input = layersDiv.querySelector<HTMLInputElement>(`.layer-item[data-key="${def.key}"] input[type=checkbox]`)
    if (input) input.checked = on
    setLayerVisible(def, on)
  }
}
;(document.getElementById('all-on') as HTMLButtonElement).addEventListener('click', () => setAll(true))
;(document.getElementById('all-off') as HTMLButtonElement).addEventListener('click', () => setAll(false))

// ---- 背景地図スイッチャー（右下） ----
class BasemapControl implements maplibregl.IControl {
  private el!: HTMLElement
  onAdd(): HTMLElement {
    this.el = document.createElement('div')
    this.el.className = 'maplibregl-ctrl basemap-switch'
    const defs: [Basemap, string][] = [
      ['pale', '地図'],
      ['photo', '写真'],
    ]
    for (const [b, label] of defs) {
      const btn = document.createElement('button')
      btn.type = 'button'
      btn.textContent = label
      btn.dataset.base = b
      btn.setAttribute('aria-selected', String(b === base))
      btn.addEventListener('click', () => setBase(b))
      this.el.append(btn)
    }
    return this.el
  }
  onRemove(): void {
    this.el.remove()
  }
  sync(): void {
    for (const btn of this.el.querySelectorAll<HTMLButtonElement>('button')) {
      btn.setAttribute('aria-selected', String(btn.dataset.base === base))
    }
  }
}
const basemapCtrl = new BasemapControl()
map.addControl(basemapCtrl, 'bottom-right')



function setBase(next: Basemap): void {
  if (next === base) return
  base = next
  basemapCtrl.sync()
  reloadStyle()
}

// ---- クリック（ポップアップ） ----
const activeQueryIds = (): string[] =>
  LAYERS.filter((l) => l.on)
    .flatMap(queryableLayerIds)
    .filter((id) => map.getLayer(id))

if (window.matchMedia('(hover: hover)').matches) {
  map.on('mousemove', (e) => {
    const ids = activeQueryIds()
    const hit = ids.length && map.queryRenderedFeatures(e.point, { layers: ids }).length > 0
    map.getCanvas().style.cursor = hit ? 'pointer' : ''
  })
}

let popup: maplibregl.Popup | null = null
map.on('click', (e) => {
  const ids = activeQueryIds()
  const feats = ids.length ? map.queryRenderedFeatures(e.point, { layers: ids }) : []
  if (!feats.length) return
  // 中身のある地物を優先する。主要活断層帯のように、線には属性が無く
  // 名称は不可視ポリゴン側にしか無いデータがあるため、先頭決め打ちだと空のポップアップになる。
  const hasContent = (x: maplibregl.MapGeoJSONFeature): boolean =>
    Object.entries(x.properties ?? {}).some(([k, v]) => !k.startsWith('_') && v !== null && v !== '')
  const f = feats.find(hasContent) ?? feats[0]
  const key = f.layer.id.split('--')[0]
  const def = LAYERS.find((l) => l.key === key)
  if (!def) return
  if (popup) {
    const old = popup
    popup = null
    old.remove()
  }
  const p = new maplibregl.Popup({ closeButton: true, maxWidth: '320px' })
    .setLngLat(e.lngLat)
    .setHTML(popupHtml(def, f.properties as Record<string, unknown>))
    .addTo(map)
  p.on('close', () => {
    if (popup === p) popup = null
  })
  popup = p
})

// ---- 初期化 ----
const buildEl = document.getElementById('build-ver')
if (buildEl) buildEl.textContent = `build: ${__BUILD_TIME__}`
renderThemeBtn()
buildPanel()
if (isMobile) panel.classList.add('collapsed')
renderCollapseBtn()
map.on('load', () => {
  ensureTerrainSource()
  addDataLayers()
})
initHud()

// WebGL コンテキスト消失からの復帰（iOS Safari 等でメモリ逼迫時に起きる）
const canvas = map.getCanvas()
canvas.addEventListener(
  'webglcontextlost',
  (e) => {
    e.preventDefault()
    diag('WebGL context lost')
  },
  false,
)
canvas.addEventListener(
  'webglcontextrestored',
  () => {
    diag('WebGL context restored → relayering')
    iconPromises.clear()
    if (map.isStyleLoaded()) {
      ensureTerrainSource()
      addDataLayers()
    } else {
      map.once('idle', () => {
        ensureTerrainSource()
        addDataLayers()
      })
    }
  },
  false,
)

map.on('error', (e) => {
  const msg = (e && (e as unknown as { error?: Error }).error?.message) || 'map error'
  diag(`error: ${msg}`)
})
;(window as unknown as { __map: maplibregl.Map }).__map = map
