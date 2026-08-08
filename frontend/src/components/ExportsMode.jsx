// components/SocialTab.jsx
import { useState, useEffect } from 'react'
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

export default function ExportsMode() {
  const { toast, showToast } = useToast()
  const [episodes,  setEpisodes]  = useState([])
  const [activeEp,  setActiveEp]  = useState(null)
  const [exports,   setExports]   = useState([])
  const [presets,   setPresets]   = useState([])
  const [generating, setGenerating] = useState(false)
  const [showCreate, setShowCreate] = useState(false)
  const [selectedPreset, setSelectedPreset] = useState(null)

  useEffect(() => {
    loadEpisodes()
    loadPresets()
  }, [])

  const loadEpisodes = async () => {
    try {
      const data = await api.listEpisodes()
      const list = Array.isArray(data) ? data : (data.episodes || [])
      setEpisodes(list)
      if (list.length) selectEpisode(list[0])
    } catch { showToast('Could not load episodes') }
  }

  const loadPresets = async () => {
    try {
      const p = await api.socialPresets()
      setPresets(Array.isArray(p) ? p : (p.presets || []))
    } catch { setPresets([]) }
  }

  const selectEpisode = async (ep) => {
    setActiveEp(ep)
    try {
      const data = await api.listSocialExports(ep.episode_id || ep.id)
      setExports(Array.isArray(data) ? data : (data.exports || []))
    } catch { setExports([]) }
  }

  const epId = activeEp?.episode_id || activeEp?.id

  const handleGenerate = async (form) => {
    if (!epId) return
    setGenerating(true)
    try {
      await api.generateSocial({ ...form, episode_id: epId })
      showToast('Social export queued ✓')
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
              <div className="font-mono" style={{ fontSize: '.46rem', color: 'var(--steel)' }}>{slot.desc}</div>
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
              onClick={() => setSelectedPreset(selectedPreset === i ? null : i)}
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
          onClose={() => setShowCreate(false)}
          onGenerate={handleGenerate}
          generating={generating}
        />
      )}

      <Toast {...toast} />
    </div>
  )
}

function GenerateSocialModal({ presets, onClose, onGenerate, generating }) {
  const [form, setForm] = useState({
    export_type: 'audiogram',
    platform: 'instagram',
    aspect_ratio: '1:1',
    asset_slot: 'thumbnail_base',
    clip_start: 0,
    clip_duration: 60,
    quote_text: '',
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
              {PLATFORMS.map(p => <option key={p}>{p}</option>)}
            </select>
          </Field>
          <Field label="Aspect Ratio">
            <select className="ds-select" value={form.aspect_ratio} onChange={e => set('aspect_ratio', e.target.value)}>
              {ASPECT_OPTS.map(a => <option key={a}>{a}</option>)}
            </select>
          </Field>
          <Field label="Asset Slot">
            <select className="ds-select" value={form.asset_slot} onChange={e => set('asset_slot', e.target.value)}>
              {ASSET_SLOTS.map(s => <option key={s.key} value={s.key}>{s.label}</option>)}
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
