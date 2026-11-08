import { useEffect, useMemo, useState } from 'react'
import {
  ArrowDown, ArrowUp, Download, FileText, Image, Mic2,
  Music, Plus, RefreshCw, Trash2, Upload
} from 'lucide-react'
import { api } from '../lib/api'
import { buildAudacityScript, buildM3U, buildSlideManifest, downloadText, fmtTime } from './assemblyExport'

const DEFAULT_TEMPLATE = [
  { id: 'a1', type: 'intro', label: 'Intro', dur: 30, audio: null, slides: [] },
  { id: 'a2', type: 'segment', label: 'Segment 1', dur: 600, audio: null, slides: [] },
  { id: 'a3', type: 'ad', label: 'Ad Spot A', dur: 60, audio: null, slides: [] },
  { id: 'a4', type: 'segment', label: 'Segment 2', dur: 600, audio: null, slides: [] },
  { id: 'a5', type: 'jingle', label: 'Out Jingle', dur: 15, audio: null, slides: [] },
  { id: 'a6', type: 'ad', label: 'Ad Spot B', dur: 60, audio: null, slides: [] },
  { id: 'a7', type: 'jingle', label: 'In Jingle', dur: 15, audio: null, slides: [] },
  { id: 'a8', type: 'segment', label: 'Segment 3', dur: 600, audio: null, slides: [] },
  { id: 'a9', type: 'jingle', label: 'Out Jingle', dur: 15, audio: null, slides: [] },
  { id: 'a10', type: 'outro', label: 'Outro', dur: 30, audio: null, slides: [] },
  { id: 'a11', type: 'ad', label: 'Outro Ad Spot', dur: 60, audio: null, slides: [] },
]

const AUDIO_EXT = /\.(mp3|wav|m4a|ogg)$/i
const IMAGE_EXT = /\.(jpg|jpeg|png|webp|gif)$/i

function cloneTemplate() {
  return JSON.parse(JSON.stringify(DEFAULT_TEMPLATE))
}

function nameOf(asset) {
  return asset?.original_name || asset?.filename || asset?.name || asset?.stored_name || ''
}

function classifyAsset(asset) {
  const n = nameOf(asset).toLowerCase()
  const role = String(asset?.role || '').toLowerCase()
  if (IMAGE_EXT.test(n) || String(asset?.content_type || '').startsWith('image/')) return 'image'
  if (!AUDIO_EXT.test(n) && !String(asset?.content_type || '').startsWith('audio/')) return 'other'
  if (role.includes('intro') || n.includes('intro')) return 'intro'
  if (role.includes('outro') || n.includes('outro')) return 'outro'
  if (role.includes('jingle') || n.includes('jingle') || n.includes('bumper')) return 'jingle'
  if (role.includes('ad') || n.includes('ad_') || n.includes('advert')) return 'ad'
  return 'segment'
}

function mapEpisodeAssets(assets = [], ads = []) {
  const slots = cloneTemplate()
  const buckets = { intro: [], outro: [], segment: [], ad: [], jingle: [], image: [] }
  assets.forEach((asset) => {
    const kind = classifyAsset(asset)
    if (buckets[kind]) buckets[kind].push(asset)
  })

  ads.forEach((ad) => {
    const audio = ad.audio_file || ad.audio_path || ad.audio || ''
    if (audio) buckets.ad.push({ original_name: audio, ...ad })
  })

  let seg = 0, ad = 0, jingle = 0
  slots.forEach((slot) => {
    let source = null
    if (slot.type === 'intro') source = buckets.intro.shift()
    if (slot.type === 'outro') source = buckets.outro.shift()
    if (slot.type === 'segment') source = buckets.segment[seg++]
    if (slot.type === 'ad') source = buckets.ad[ad++]
    if (slot.type === 'jingle') source = buckets.jingle[jingle++]
    if (source) slot.audio = nameOf(source)
  })

  const visualSlots = slots.filter((slot) => ['intro', 'ad', 'outro'].includes(slot.type))
  buckets.image.forEach((asset, i) => {
    if (!visualSlots.length) return
    visualSlots[i % visualSlots.length].slides.push({ filename: nameOf(asset), caption: '' })
  })

  return slots
}

export default function AssemblyTab() {
  const [episodes, setEpisodes] = useState([])
  const [episodeId, setEpisodeId] = useState('')
  const [episodeName, setEpisodeName] = useState('Episode Assembly')
  const [slots, setSlots] = useState(cloneTemplate)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const totalSecs = useMemo(() => slots.reduce((t, s) => t + (Number(s.dur) || 0), 0), [slots])
  const totalSlides = useMemo(() => slots.reduce((t, s) => t + (s.slides?.length || 0), 0), [slots])
  const missingAudio = useMemo(() => slots.filter((s) => !s.audio).length, [slots])

  async function loadEpisodes() {
    setLoading(true)
    setError('')
    try {
      const data = await api.listEpisodes()
      setEpisodes(Array.isArray(data) ? data : (data.episodes || []))
    } catch (e) {
      setError(e.message || 'Could not load episodes')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadEpisodes() }, [])

  async function loadEpisode(id) {
    if (!id) return
    setLoading(true)
    setError('')
    try {
      const ep = episodes.find((item) => (item.episode_id || item.id) === id)
      const [detail, assetData, ads] = await Promise.all([
        api.getEpisode(id).catch(() => null),
        api.listAssets(id).catch(() => ({ assets: [] })),
        api.listAds(id).catch(() => []),
      ])
      setEpisodeName(detail?.config?.title || detail?.title || ep?.title || id)
      const assets = Array.isArray(assetData) ? assetData : (assetData.assets || [])
      setSlots(mapEpisodeAssets(assets, ads))
    } catch (e) {
      setError(e.message || 'Could not load episode assets')
    } finally {
      setLoading(false)
    }
  }

  function updateSlot(id, patch) {
    setSlots((current) => current.map((slot) => slot.id === id ? { ...slot, ...patch } : slot))
  }

  function moveSlot(index, delta) {
    const nextIndex = index + delta
    if (nextIndex < 0 || nextIndex >= slots.length) return
    setSlots((current) => {
      const next = [...current]
      const [moved] = next.splice(index, 1)
      next.splice(nextIndex, 0, moved)
      return next
    })
  }

  function removeSlot(id) {
    setSlots((current) => current.filter((slot) => slot.id !== id))
  }

  function addSlot(type) {
    const defaults = {
      segment: { label: 'New Segment', dur: 600 },
      ad: { label: 'New Ad Spot', dur: 60 },
      jingle: { label: 'Jingle', dur: 15 },
    }
    const d = defaults[type]
    setSlots((current) => [...current, {
      id: `slot_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
      type,
      ...d,
      audio: null,
      slides: [],
    }])
  }

  function assignAudio(slot, file) {
    if (!file) return
    updateSlot(slot.id, { audio: file.name, _audioFile: file })
  }

  function assignSlides(slot, fileList) {
    const added = Array.from(fileList || []).map((file) => ({ filename: file.name, caption: '', _file: file }))
    updateSlot(slot.id, { slides: [...(slot.slides || []), ...added] })
  }

  const safeName = episodeName.replace(/[^a-z0-9_-]/gi, '_')

  return (
    <div className="assembly-tab">
      <div className="assembly-toolbar">
        <div>
          <div className="assembly-title">EPISODE ASSEMBLY BOARD</div>
          <div className="assembly-subtitle">Final sequence, ad placement, jingles, audio handoff and visual track</div>
        </div>
        <button className="btn btn-steel" onClick={loadEpisodes} disabled={loading}><RefreshCw size={12} />REFRESH</button>
        <select className="ds-select assembly-episode-select" value={episodeId} onChange={(e) => { setEpisodeId(e.target.value); loadEpisode(e.target.value) }}>
          <option value="">SELECT EPISODE</option>
          {episodes.map((ep) => {
            const id = ep.episode_id || ep.id
            return <option key={id} value={id}>{ep.title || id}</option>
          })}
        </select>
        <input className="ds-input assembly-name" value={episodeName} onChange={(e) => setEpisodeName(e.target.value)} />
      </div>

      {error && <div className="assembly-error">{error}</div>}

      <div className="assembly-stats">
        <span><Mic2 size={12} /> Runtime <b>{fmtTime(totalSecs)}</b></span>
        <span><Image size={12} /> Slides <b>{totalSlides}</b></span>
        <span><Music size={12} /> Missing audio <b className={missingAudio ? 'assembly-warn' : ''}>{missingAudio}</b></span>
        <span><FileText size={12} /> Slots <b>{slots.length}</b></span>
      </div>

      <div className="assembly-list">
        {slots.map((slot, index) => (
          <div className="assembly-slot" key={slot.id}>
            <div className={`assembly-type type-${slot.type}`}>{slot.type}</div>
            <input className="ds-input assembly-label" value={slot.label} onChange={(e) => updateSlot(slot.id, { label: e.target.value })} />
            <div className={`assembly-file ${slot.audio ? 'ok' : ''}`}><Music size={11} />{slot.audio || 'no audio assigned'}</div>
            {['intro', 'ad', 'outro'].includes(slot.type) && <div className="assembly-file"><Image size={11} />{slot.slides?.length || 0} slides</div>}
            <input className="ds-input assembly-duration" type="number" min="1" value={slot.dur} onChange={(e) => updateSlot(slot.id, { dur: Number(e.target.value) || 1 })} />
            <label className="btn btn-steel btn-sm assembly-upload"><Upload size={11} /> AUDIO<input hidden type="file" accept="audio/*" onChange={(e) => assignAudio(slot, e.target.files?.[0])} /></label>
            {['intro', 'ad', 'outro'].includes(slot.type) && <label className="btn btn-steel btn-sm assembly-upload"><Image size={11} /> SLIDES<input hidden multiple type="file" accept="image/*,video/*" onChange={(e) => assignSlides(slot, e.target.files)} /></label>}
            <button className="icon-btn" onClick={() => moveSlot(index, -1)} disabled={index === 0}><ArrowUp size={12} /></button>
            <button className="icon-btn" onClick={() => moveSlot(index, 1)} disabled={index === slots.length - 1}><ArrowDown size={12} /></button>
            <button className="icon-btn del" onClick={() => removeSlot(slot.id)}><Trash2 size={12} /></button>
          </div>
        ))}
      </div>

      <div className="assembly-footer">
        <span className="assembly-add-label">ADD SLOT</span>
        {['segment', 'ad', 'jingle'].map((type) => <button key={type} className="btn btn-steel btn-sm" onClick={() => addSlot(type)}><Plus size={11} />{type.toUpperCase()}</button>)}
        <button className="btn btn-steel btn-sm" onClick={() => setSlots(cloneTemplate())}><RefreshCw size={11} />RESET</button>
        <div className="assembly-export-spacer" />
        <button className="btn btn-gold" onClick={() => downloadText(buildAudacityScript(slots, episodeName), `${safeName}_audacity.txt`)}><FileText size={12} />AUDACITY SCRIPT</button>
        <button className="btn btn-steel" onClick={() => downloadText(buildSlideManifest(slots, episodeName), `${safeName}_slides.json`, 'application/json')} disabled={!totalSlides}><Image size={12} />SLIDE MANIFEST</button>
        <button className="btn btn-steel" onClick={() => downloadText(buildM3U(slots, episodeName), `${safeName}.m3u`)}><Download size={12} />M3U</button>
      </div>

      <style>{`
        .assembly-tab{display:flex;flex-direction:column;flex:1;min-height:0;background:var(--bg);overflow:hidden}
        .assembly-toolbar{display:flex;align-items:center;gap:10px;padding:12px 16px;border-bottom:1px solid var(--rim);background:var(--surface);flex-wrap:wrap}
        .assembly-title{font-family:var(--font-display);font-size:1.2rem;letter-spacing:.08em;color:var(--gold)}
        .assembly-subtitle{font-family:var(--font-mono);font-size:.48rem;color:var(--steel);letter-spacing:.06em}
        .assembly-episode-select{width:220px}.assembly-name{min-width:220px;flex:1}
        .assembly-error{padding:8px 16px;color:var(--red);border-bottom:1px solid var(--rim);font-family:var(--font-mono);font-size:.58rem}
        .assembly-stats{display:flex;gap:24px;align-items:center;padding:8px 16px;border-bottom:1px solid var(--rim);font-family:var(--font-mono);font-size:.54rem;color:var(--steel)}
        .assembly-stats span{display:flex;align-items:center;gap:6px}.assembly-stats b{color:var(--bone)}.assembly-stats .assembly-warn{color:var(--red)}
        .assembly-list{flex:1;min-height:0;overflow:auto;padding:10px 12px;display:flex;flex-direction:column;gap:4px}
        .assembly-slot{display:flex;align-items:center;gap:7px;padding:7px 8px;background:var(--surface);border:1px solid var(--rim);border-radius:var(--radius)}
        .assembly-type{width:66px;flex:0 0 66px;text-align:center;border-radius:99px;padding:3px 5px;font-family:var(--font-mono);font-size:.48rem;text-transform:uppercase;border:1px solid var(--rim);color:var(--steel)}
        .type-intro{color:var(--blue)}.type-segment{color:var(--green)}.type-ad{color:var(--gold)}.type-jingle{color:#c084fc}.type-outro{color:var(--red)}
        .assembly-label{width:145px;flex:0 0 145px}.assembly-file{display:flex;align-items:center;gap:5px;min-width:120px;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--steel);font-family:var(--font-mono);font-size:.5rem}.assembly-file.ok{color:var(--bone)}
        .assembly-duration{width:64px;flex:0 0 64px;text-align:right}.assembly-upload{cursor:pointer}.assembly-footer{display:flex;align-items:center;gap:7px;padding:10px 12px;border-top:1px solid var(--rim);background:var(--surface);flex-wrap:wrap}.assembly-add-label{font-family:var(--font-mono);font-size:.48rem;color:var(--steel)}.assembly-export-spacer{flex:1}
      `}</style>
    </div>
  )
}
