// components/SocialTab.jsx
import { useState, useEffect, useRef } from 'react'
import { Zap, Download, RefreshCw, Image, Upload } from 'lucide-react'
import { api } from '../lib/api'
import { Modal, Field, SectionHead, Spinner, Empty, Badge, Divider, Toast } from './ui'
import { useToast } from '../hooks/useToast'

const PLATFORMS   = ['instagram', 'twitter', 'youtube', 'tiktok', 'linkedin', 'podcast_art']
const EXPORT_TYPES = ['audiogram', 'thumbnail', 'quote_card', 'promo_clip', 'show_notes']
const ASPECT_OPTS  = ['1:1', '16:9', '9:16', '4:5']

// Asset slot names from ASSET_SLOTS.md
const ASSET_SLOTS = [
  { key: 'thumbnail_base',  label: 'Thumbnail Base',    desc: 'Main official social thumbnail', accent: '#e8b84b' },
  { key: 'waveform_base',   label: 'Waveform Base',     desc: 'Main audiogram background', accent: '#58a6ff' },
  { key: 'alternate_cover', label: 'Alternate Cover',   desc: 'Blue countryside alternate', accent: '#a78bfa' },
  { key: 'character_logo',  label: 'Character Logo',    desc: 'Vintage cream Phil/Jim logo', accent: '#f0c987' },
  { key: 'segment_tech_talk',label:'Tech Talk Card',    desc: 'Tech Talk segment card', accent: '#38bdf8' },
  { key: 'logo',            label: 'Logo Mark',         desc: 'Main simplified mark', accent: '#4ade80' },
  { key: 'pops_thumbnail_base', label: 'POPS Thumbnail Base', desc: 'Proof of Presence banner artwork', accent: '#3b82f6' },
  { key: 'pops_character_art', label: 'POPS Character Art', desc: 'Average Dad Mode character image', accent: '#06b6d4' },
  { key: 'pops_wordmark', label: 'POPS Wordmark', desc: 'Proof of Presence nameplate', accent: '#60a5fa' },
  { key: 'pops_logo_mark', label: 'POPS Logo Mark', desc: 'Compact POPS shield icon', accent: '#2563eb' },
]

const PRESET_ACCENTS = {
  youtube_thumbnail: '#f87171', youtube_shorts: '#fb7185', tiktok: '#22d3ee',
  instagram_reels: '#e879f9', facebook_feed: '#60a5fa', linkedin_post: '#38bdf8', x_post: '#a1a1aa',
}
const BACKGROUND_ASSET_SLOTS = ASSET_SLOTS.filter(slot => !['logo', 'pops_logo_mark', 'pops_wordmark'].includes(slot.key))

export default function ExportsMode({ episodeId, onEpisodeChange }) {
  const { toast, showToast } = useToast()
  const [episodes,  setEpisodes]  = useState([])
  const [activeEp,  setActiveEp]  = useState(null)
  const [exports,   setExports]   = useState([])
  const [presets,   setPresets]   = useState([])
  const [generating, setGenerating] = useState(false)
  const [showCreate, setShowCreate] = useState(false)
  const [selectedPreset, setSelectedPreset] = useState(null)
  const [assetStatus, setAssetStatus] = useState([])
  const selectionRequest = useRef(0)

  useEffect(() => {
    loadEpisodes()
    loadPresets()
    fetch('/api/social/assets').then(r => { if (!r.ok) throw new Error('Asset check failed'); return r.json() }).then(data => setAssetStatus(data.assets || [])).catch(() => showToast('Asset availability could not be checked'))
  }, [])

  const loadEpisodes = async () => {
    try {
      const data = await api.listEpisodes()
      const list = Array.isArray(data) ? data : (data.episodes || [])
      setEpisodes(list)
      if (list.length) selectEpisode(list.find(ep => (ep.episode_id || ep.id) === episodeId) || list[0])
    } catch { showToast('Could not load episodes') }
  }

  const loadPresets = async () => {
    try {
      const p = await api.socialPresets()
      setPresets(Array.isArray(p) ? p : (p.presets || []))
    } catch { setPresets([]) }
  }

  const selectEpisode = async (ep) => {
    const requestId = ++selectionRequest.current
    setActiveEp(ep)
    setExports([])
    onEpisodeChange?.(ep.episode_id || ep.id)
    try {
      const data = await api.listSocialExports(ep.episode_id || ep.id)
      if (requestId === selectionRequest.current) setExports(Array.isArray(data) ? data : (data.exports || []))
    } catch { if (requestId === selectionRequest.current) setExports([]) }
  }

  const epId = activeEp?.episode_id || activeEp?.id

  const handleGenerate = async (form) => {
    if (!epId) return
    setGenerating(true)
    try {
      await api.generateSocial({ ...form, episode_id: epId })
      showToast('Social export completed')
      setShowCreate(false)
      await selectEpisode(activeEp)
    } catch (e) {
      showToast('Generate failed: ' + e.message)
    } finally { setGenerating(false) }
  }

  return (
    <div className="tab-body social-exports-layout">

      {/* LEFT — episode picker */}
      <div className="pane-left">
        <SectionHead label="Episodes" />
        <div className="scrollable">
          {episodes.length === 0 && <Empty msg="No episodes" />}
          {episodes.map(ep => {
            const id = ep.episode_id || ep.id
            const active = epId === id
            return (
              <div key={id} className={`ep-row${active ? ' active' : ''}`} onClick={() => selectEpisode(ep)}>
                <div className="ep-num">{String(id).slice(0, 12).toUpperCase()}</div>
                <div className="ep-title">{ep.title || id}</div>
              </div>
            )
          })}
        </div>
      </div>

      {/* CENTER — exports */}
      <div className="pane-main">
        <div className="section-head">
          <span className="section-label">
            {activeEp ? `${activeEp.title || epId} — Exports (${exports.length})` : 'Select an episode'}
          </span>
          <button className="btn btn-gold btn-sm" onClick={() => setShowCreate(true)} disabled={!activeEp}>
            <Zap size={10} /> GENERATE
          </button>
          <button className="icon-btn" onClick={() => activeEp && selectEpisode(activeEp)}>
            <RefreshCw size={10} />
          </button>
        </div>

        <div className="scrollable social-exports-list" style={{ padding: '10px 14px' }}>
          {!activeEp && <Empty msg="← Select an episode" />}
          {activeEp && exports.length === 0 && (
            <div style={{ textAlign: 'center', paddingTop: '3rem' }}>
              <Empty msg="No social exports yet — generate one above" />
            </div>
          )}
          {exports.map((ex, i) => (
            <div key={ex.export_id || i} className="preset-card" style={{ cursor: 'default' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                <Image size={14} style={{ color: 'var(--gold)', flexShrink: 0 }} />
                <span className="font-display" style={{ fontSize: '1.17rem', color: 'var(--bone)', letterSpacing: '.06em' }}>
                  {ex.export_type || `Export #${i + 1}`}
                </span>
                <Badge type="gold">{ex.platform || '—'}</Badge>
                <Badge type={ex.status === 'done' ? 'green' : 'steel'}>{ex.status || 'pending'}</Badge>
              </div>
              <div className="font-mono" style={{ fontSize: '0.68rem', color: 'var(--steel)', marginBottom: 8 }}>
                {ex.aspect_ratio || '—'} · Asset: {ex.asset_slot || 'thumbnail_base'} · {ex.created_at || '—'}
              </div>
              {ex.preview_url && (
                ex.media_type?.startsWith('video/') ? <video
                  controls preload="metadata" src={ex.preview_url} aria-label={`${ex.export_type || 'Social'} video preview`}
                  className="social-export-media"
                /> : ex.media_type?.startsWith('audio/') ? <audio
                  controls preload="metadata" src={ex.preview_url} aria-label={`${ex.export_type || 'Social'} audio preview`}
                  style={{ display: 'block', width: '100%', marginBottom: 8 }}
                /> : <img src={ex.preview_url} alt={`${ex.export_type || 'Social'} preview`} className="social-export-media" />
              )}
              {ex.file_path && (
                <button className="btn btn-steel btn-sm" onClick={() => window.open(api.socialDownloadUrl(ex.export_id))}>
                  <Download size={9} /> DOWNLOAD
                </button>
              )}
              {ex.post_text && <div style={{ marginTop: 10 }}><div className="field-label">Post copy</div><pre style={{ whiteSpace: 'pre-wrap', fontFamily: 'inherit', fontSize: '1.04rem' }}>{ex.post_text}</pre><button className="btn btn-steel btn-sm" onClick={() => navigator.clipboard.writeText(ex.post_text).then(() => showToast('Post copy copied')).catch(() => showToast('Clipboard unavailable; use the download link'))}>COPY POST</button>{ex.post_copy_url && <a className="btn btn-steel btn-sm" href={ex.post_copy_url} download>DOWNLOAD COPY</a>}</div>}
            </div>
          ))}
        </div>
      </div>

      {/* RIGHT — asset slots & presets */}
      <div className="pane-right">
        <SectionHead label="Asset Slots" />
        <div className="social-right-scroll">
          <div className="social-assets-list" style={{ padding: '10px 12px', borderBottom: '1px solid var(--rim)' }}>
            {ASSET_SLOTS.map(slot => (
              <div key={slot.key} style={{ marginBottom: 8 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 5, alignItems: 'baseline' }}>
                  <div style={{ fontSize: '0.91rem', fontWeight: 600, color: 'var(--bone)', marginBottom: 2 }}>{slot.label}</div>
                  <span className="font-mono" style={{ fontSize: '0.68rem', color: assetStatus.find(asset => asset.id === slot.key)?.available ? 'var(--green)' : 'var(--gold)', whiteSpace: 'nowrap' }}>
                    {assetStatus.find(asset => asset.id === slot.key)?.available ? 'READY' : 'MISSING'}
                  </span>
                </div>
                <div className="font-mono" style={{ fontSize: '0.68rem', color: 'var(--steel)' }}>{slot.desc} · {assetStatus.find(asset => asset.id === slot.key)?.filename || `${slot.key}.png`}</div>
              </div>
            ))}
            <div className="social-asset-help">Add these PNGs under <code>social/templates</code> or <code>social/assets</code>, then reload Social. There is no upload control. Presets use Thumbnail Base or Waveform Base when that file is available; Logo Mark is for the Slideshow and Ad Cards builders.</div>
          </div>

          <SectionHead label="Presets" />
          <div className="social-preset-grid">
            {presets.length === 0 && <Empty msg="No presets" />}
            {presets.map((p, i) => (
              <button
                key={i}
                type="button"
                className={`preset-card social-preset-tile${selectedPreset === i ? ' selected' : ''}`}
                aria-pressed={selectedPreset === i}
                style={{ '--preset-accent': PRESET_ACCENTS[p.platform] || ['#e8b84b', '#58a6ff', '#a78bfa', '#4ade80'][i % 4] }}
                onClick={() => { setSelectedPreset(i); setShowCreate(true) }}
              >
                <div className="social-preset-name">
                  {p.name || p.preset_id || `Preset ${i + 1}`}
                </div>
                <div className="font-mono social-preset-meta">
                  {p.export_type || ''} · {p.aspect_ratio || ''}
                </div>
              </button>
            ))}
          </div>
        </div>
      </div>

      {showCreate && (
        <GenerateSocialModal
          episodeId={epId}
          presets={presets}
          preset={presets[selectedPreset]}
          assetStatus={assetStatus}
          onClose={() => setShowCreate(false)}
          onGenerate={handleGenerate}
          generating={generating}
        />
      )}

      <Toast {...toast} />
    </div>
  )
}

function GenerateSocialModal({ episodeId, presets, preset, assetStatus, onClose, onGenerate, generating }) {
  const defaultBackground = preset?.export_type === 'audiogram' ? 'waveform_base' : 'thumbnail_base'
  const defaultBackgroundAvailable = assetStatus.find(asset => asset.id === defaultBackground)?.available
  const [form, setForm] = useState({
    export_type: preset?.export_type || 'audiogram',
    platform: preset?.platform || 'instagram',
    aspect_ratio: preset?.aspect_ratio || '1:1',
    asset_slot: defaultBackgroundAvailable ? defaultBackground : 'none',
    clip_start: 0,
    clip_duration: 60,
    quote_text: '',
    post_text: '',
    show_waveform: true,
    visual_mode: 'waveform',
    visual_asset_id: '',
    visual_asset_ids: [],
    visual_clip_start: 0,
  })
  const [visualAssets, setVisualAssets] = useState([])
  const [uploadingMedia, setUploadingMedia] = useState(false)
  const visualFileRef = useRef(null)
  useEffect(() => {
    if (!episodeId) return
    api.listAssets(episodeId).then(data => {
      const assets = Array.isArray(data) ? data : (data.assets || [])
      setVisualAssets(assets.filter(asset => ['image', 'video'].includes(String(asset.asset_type || '').toLowerCase())))
    }).catch(() => setVisualAssets([]))
  }, [episodeId])
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))
  const uploadVisualMedia = async (files) => {
    if (!files?.length) return
    setUploadingMedia(true)
    try {
      for (const file of files) {
        if (!file.type.startsWith('image/') && !file.type.startsWith('video/')) throw new Error(`${file.name} is not an image or video`)
        const data = new FormData()
        data.append('file', file)
        data.append('label', file.name)
        data.append('description', 'Social export visual source')
        data.append('role', 'social_visual')
        await api.uploadAsset(episodeId, data)
      }
      const data = await api.listAssets(episodeId)
      const assets = Array.isArray(data) ? data : (data.assets || [])
      const media = assets.filter(asset => ['image', 'video'].includes(String(asset.asset_type || '').toLowerCase()))
      setVisualAssets(media)
      const uploadedNames = new Set(Array.from(files, file => file.name))
      const uploaded = media.filter(asset => uploadedNames.has(asset.original_name || asset.filename)).map(asset => asset.asset_id)
      if (form.visual_mode === 'slideshow') set('visual_asset_ids', [...new Set([...form.visual_asset_ids, ...uploaded])])
      else if (uploaded.length) set('visual_asset_id', uploaded[uploaded.length - 1])
    } catch (error) {
      window.alert(`Media upload failed: ${error.message}`)
    } finally {
      setUploadingMedia(false)
      if (visualFileRef.current) visualFileRef.current.value = ''
    }
  }

  return (
    <Modal
      title="Generate Social Export"
      onClose={onClose}
      footer={<>
        <button className="btn btn-steel" onClick={onClose}>CANCEL</button>
        <button className="btn btn-gold" onClick={() => onGenerate(form)} disabled={generating}>
          {generating ? <Spinner size={11} /> : <Zap size={11} />} GENERATE
        </button>
      </>}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
          <Field label="Export Type">
            <select className="ds-select" value={form.export_type} onChange={e => set('export_type', e.target.value)}>
              {EXPORT_TYPES.map(t => <option key={t}>{t}</option>)}
            </select>
          </Field>
          <Field label="Platform">
            <select className="ds-select" value={form.platform} onChange={e => set('platform', e.target.value)}>
              {[...new Set([...PLATFORMS, ...presets.map(p => p.platform)])].map(p => <option key={p}>{p}</option>)}
            </select>
          </Field>
          <Field label="Aspect Ratio">
            <select className="ds-select" value={form.aspect_ratio} onChange={e => set('aspect_ratio', e.target.value)}>
              {ASPECT_OPTS.map(a => <option key={a}>{a}</option>)}
            </select>
          </Field>
          <Field label="Background Image">
            <select className="ds-select" value={form.asset_slot} onChange={e => set('asset_slot', e.target.value)}>
              <option value="none">Plain background (no brand image)</option>
              {BACKGROUND_ASSET_SLOTS.map(s => <option key={s.key} value={s.key}>{s.label}{assetStatus.find(asset => asset.id === s.key)?.available ? '' : ' — missing'}</option>)}
            </select>
          </Field>
        </div>
        <Field label="Video Visual Style">
          <select className="ds-select" value={form.visual_mode} onChange={e => set('visual_mode', e.target.value)}>
            <option value="plain">1 · Plain color background</option>
            <option value="waveform">2 · Animated waveform</option>
            <option value="image">3 · Single image</option>
            <option value="slideshow">4 · Image slideshow</option>
            <option value="video">5 · Background video clip</option>
          </select>
        </Field>
        {['image', 'video'].includes(form.visual_mode) && <Field label={form.visual_mode === 'video' ? 'Background Video' : 'Display Image'}>
          <select className="ds-select" value={form.visual_asset_id} onChange={e => set('visual_asset_id', e.target.value)}>
            <option value="">Select existing media…</option>
            {visualAssets.filter(asset => form.visual_mode === 'image' ? asset.asset_type === 'image' : asset.asset_type === 'video').map(asset => <option key={asset.asset_id} value={asset.asset_id}>{asset.label || asset.original_name || asset.filename}</option>)}
          </select>
        </Field>}
        {form.visual_mode === 'slideshow' && <Field label="Slideshow Images (Ctrl/Shift-click to select several)">
          <select className="ds-select" multiple value={form.visual_asset_ids} onChange={e => set('visual_asset_ids', Array.from(e.target.selectedOptions, option => option.value))} style={{ minHeight: 100 }}>
            {visualAssets.filter(asset => asset.asset_type === 'image').map(asset => <option key={asset.asset_id} value={asset.asset_id}>{asset.label || asset.original_name || asset.filename}</option>)}
          </select>
        </Field>}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <input ref={visualFileRef} type="file" accept="image/png,image/jpeg,image/webp,image/gif,image/bmp,video/mp4,video/webm,video/quicktime,video/x-matroska,video/x-msvideo" multiple={form.visual_mode === 'slideshow'} hidden onChange={e => uploadVisualMedia(Array.from(e.target.files || []))} />
          <button type="button" className="btn btn-steel btn-sm" disabled={uploadingMedia} onClick={() => visualFileRef.current?.click()}>
            {uploadingMedia ? <Spinner size={11} /> : <Upload size={11} />} ADD EXISTING IMAGE / VIDEO
          </button>
          <span style={{ fontSize: '.9rem', color: 'var(--steel)' }}>Choose files from TrueMark Mint or your ad folders; they are copied into this episode’s asset library.</span>
        </div>
        {form.visual_mode === 'video' && <Field label="Start video at (seconds)"><input className="ds-input" type="number" min={0} step={0.1} value={form.visual_clip_start} onChange={e => set('visual_clip_start', +e.target.value)} /></Field>}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
          <Field label="Clip Start (seconds)">
            <input className="ds-input" type="number" min={0} value={form.clip_start} onChange={e => set('clip_start', +e.target.value)} />
          </Field>
          <Field label="Clip Duration (seconds)">
            <input className="ds-input" type="number" min={5} max={300} value={form.clip_duration} onChange={e => set('clip_duration', +e.target.value)} />
          </Field>
        </div>
        <Field label="Quote Text (for quote cards)">
          <textarea className="ds-textarea" style={{ minHeight: 64 }} value={form.quote_text} onChange={e => set('quote_text', e.target.value)} placeholder="Pull quote from episode…" />
        </Field>
        <Field label="Post copy (optional; blank uses episode title and topic)"><textarea className="ds-textarea" value={form.post_text} onChange={e => set('post_text', e.target.value)} /></Field>
        <div style={{ fontSize: '0.94rem', color: 'var(--steel)' }}>Video exports use the selected visual style. Images and videos may be reused from the asset list or added from your computer. Quote text appears as a video hook.</div>
        {['image', 'slideshow', 'video'].includes(form.visual_mode) && <Field label="Options">
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: '1.01rem', color: 'var(--bone)' }}>
            <input type="checkbox" checked={form.show_waveform} onChange={e => set('show_waveform', e.target.checked)} />
            Show waveform animation
          </label>
        </Field>}
      </div>
    </Modal>
  )
}
