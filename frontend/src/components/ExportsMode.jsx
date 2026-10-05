// components/SocialTab.jsx
import { useState, useEffect, useRef } from 'react'
import { Zap, Download, RefreshCw, Image } from 'lucide-react'
import { api } from '../lib/api'
import { Modal, Field, SectionHead, Spinner, Empty, Badge, Divider, Toast } from './ui'
import { useToast } from '../hooks/useToast'

const PLATFORMS   = ['instagram', 'twitter', 'youtube', 'tiktok', 'linkedin', 'podcast_art']
const EXPORT_TYPES = ['audiogram', 'thumbnail', 'quote_card', 'promo_clip', 'show_notes']
const ASPECT_OPTS  = ['1:1', '16:9', '9:16', '4:5']

// Asset slot names from ASSET_SLOTS.md
const ASSET_SLOTS = [
  { key: 'thumbnail_base',  label: 'Thumbnail Base',    desc: 'Main official social thumbnail' },
  { key: 'waveform_base',   label: 'Waveform Base',     desc: 'Main audiogram background' },
  { key: 'alternate_cover', label: 'Alternate Cover',   desc: 'Blue countryside alternate' },
  { key: 'character_logo',  label: 'Character Logo',    desc: 'Vintage cream Phil/Jim logo' },
  { key: 'segment_tech_talk',label:'Tech Talk Card',    desc: 'Tech Talk segment card' },
  { key: 'logo',            label: 'Logo Mark',         desc: 'Main simplified mark' },
]

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
      showToast('Generate failed: ' + e.message.slice(0, 80))
    } finally { setGenerating(false) }
  }

  return (
    <div className="tab-body">

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

        <div className="scrollable" style={{ padding: '10px 14px' }}>
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
                <span className="font-display" style={{ fontSize: '.9rem', color: 'var(--bone)', letterSpacing: '.06em' }}>
                  {ex.export_type || `Export #${i + 1}`}
                </span>
                <Badge type="gold">{ex.platform || '—'}</Badge>
                <Badge type={ex.status === 'done' ? 'green' : 'steel'}>{ex.status || 'pending'}</Badge>
              </div>
              <div className="font-mono" style={{ fontSize: '.5rem', color: 'var(--steel)', marginBottom: 8 }}>
                {ex.aspect_ratio || '—'} · Asset: {ex.asset_slot || 'thumbnail_base'} · {ex.created_at || '—'}
              </div>
              {ex.preview_url && (
                <img
                  src={ex.preview_url}
                  alt="preview"
                  style={{ width: '100%', borderRadius: 'var(--radius)', border: '1px solid var(--rim)', marginBottom: 8 }}
                />
              )}
              {ex.file_path && (
                <button className="btn btn-steel btn-sm" onClick={() => window.open(api.socialDownloadUrl(ex.export_id))}>
                  <Download size={9} /> DOWNLOAD
                </button>
              )}
              {ex.post_text && <div style={{ marginTop: 10 }}><div className="field-label">Post copy</div><pre style={{ whiteSpace: 'pre-wrap', fontFamily: 'inherit', fontSize: '.8rem' }}>{ex.post_text}</pre><button className="btn btn-steel btn-sm" onClick={() => navigator.clipboard.writeText(ex.post_text).then(() => showToast('Post copy copied')).catch(() => showToast('Clipboard unavailable; use the download link'))}>COPY POST</button>{ex.post_copy_url && <a className="btn btn-steel btn-sm" href={ex.post_copy_url} download>DOWNLOAD COPY</a>}</div>}
            </div>
          ))}
        </div>
      </div>

      {/* RIGHT — asset slots & presets */}
      <div className="pane-right">
        <SectionHead label="Asset Slots" />
        <div style={{ padding: '10px 12px', borderBottom: '1px solid var(--rim)' }}>
          {ASSET_SLOTS.map(slot => (
            <div key={slot.key} style={{ marginBottom: 8 }}>
              <div style={{ fontSize: '.7rem', fontWeight: 600, color: 'var(--bone)', marginBottom: 2 }}>{slot.label}</div>
              <div className="font-mono" style={{ fontSize: '.46rem', color: 'var(--steel)' }}>{slot.desc} · {assetStatus.find(asset => asset.id === slot.key)?.available ? 'present' : 'missing / unverified'}</div>
            </div>
          ))}
        </div>

        <SectionHead label="Presets" />
        <div className="scrollable" style={{ padding: '10px 12px' }}>
          {presets.length === 0 && <Empty msg="No presets" />}
          {presets.map((p, i) => (
            <div
              key={i}
              className={`preset-card${selectedPreset === i ? ' selected' : ''}`}
              role="button" tabIndex={0}
              onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setSelectedPreset(i); setShowCreate(true) } }}
              onClick={() => { setSelectedPreset(i); setShowCreate(true) }}
            >
              <div style={{ fontSize: '.78rem', fontWeight: 600, color: 'var(--bone)', marginBottom: 3 }}>
                {p.name || p.preset_id || `Preset ${i + 1}`}
              </div>
              <div className="font-mono" style={{ fontSize: '.48rem', color: 'var(--steel)' }}>
                {p.platform || ''} {p.export_type || ''} {p.aspect_ratio || ''}
              </div>
            </div>
          ))}
        </div>
      </div>

      {showCreate && (
        <GenerateSocialModal
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

function GenerateSocialModal({ presets, preset, assetStatus, onClose, onGenerate, generating }) {
  const [form, setForm] = useState({
    export_type: preset?.export_type || 'audiogram',
    platform: preset?.platform || 'instagram',
    aspect_ratio: preset?.aspect_ratio || '1:1',
    asset_slot: 'none',
    clip_start: 0,
    clip_duration: 60,
    quote_text: '',
    post_text: '',
    show_waveform: true,
  })
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

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
          <Field label="Asset Slot">
            <select className="ds-select" value={form.asset_slot} onChange={e => set('asset_slot', e.target.value)}>
              <option value="none">Plain background (no brand image)</option>
              {ASSET_SLOTS.map(s => <option key={s.key} value={s.key}>{s.label}{assetStatus.find(asset => asset.id === s.key)?.available ? '' : ' — missing'}</option>)}
            </select>
          </Field>
        </div>
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
        <div style={{ fontSize: '.72rem', color: 'var(--steel)' }}>Clip timing and waveform apply to video exports. Quote text appears on quote cards and as a video hook. Static exports do not require episode audio. Missing selected assets are a validation error.</div>
        <Field label="Options">
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: '.78rem', color: 'var(--bone)' }}>
            <input type="checkbox" checked={form.show_waveform} onChange={e => set('show_waveform', e.target.checked)} />
            Show waveform animation
          </label>
        </Field>
      </div>
    </Modal>
  )
}
