// components/AdTab.jsx
import { useState, useEffect } from 'react'
import { RefreshCw, Zap, Download, Upload } from 'lucide-react'
import { api } from '../lib/api'
import { Modal, Field, SectionHead, Spinner, Empty, Badge, Toast } from './ui'
import { useToast } from '../hooks/useToast'

const AD_TYPES    = ['sponsor_60s', 'product_teaser', 'cta_closer', 'promo_15s', 'custom']
const AD_VOICES   = ['INTRO_MALE', 'INTRO_FEMALE', 'PHIL', 'JIM']
const TONE_OPTS   = ['confident', 'warm', 'urgent', 'playful', 'professional']

export default function AdTab() {
  const { toast, showToast } = useToast()
  const [episodes,  setEpisodes]  = useState([])
  const [activeEp,  setActiveEp]  = useState(null)
  const [ads,       setAds]       = useState([])
  const [presets,   setPresets]   = useState([])
  const [selectedAd, setSelectedAd] = useState(null)
  const [generating, setGenerating] = useState(false)
  const [showCreate, setShowCreate] = useState(false)
  const [scriptLength, setScriptLength] = useState(0)
  const [adAssets, setAdAssets] = useState({})
  const [insertLines, setInsertLines] = useState({})
  const [assetLabels, setAssetLabels] = useState({})
  const [assetFiles, setAssetFiles] = useState({})
  const [producingAdId, setProducingAdId] = useState('')
  const [insertingAdId, setInsertingAdId] = useState('')
  const [uploadingAdId, setUploadingAdId] = useState('')

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
      const p = await api.adPresets()
      setPresets(Array.isArray(p) ? p : (p.presets || []))
    } catch { setPresets([]) }
  }

  const selectEpisode = async (ep) => {
    setActiveEp(ep)
    setSelectedAd(null)
    const id = ep.episode_id || ep.id
    // Restore persisted insert lines for this episode from localStorage
    const savedLines = JSON.parse(localStorage.getItem(`dandy_insert_lines_${id}`) || '{}')
    try {
      const [adData, scriptData] = await Promise.all([
        api.listAds(id),
        api.getScript(id).catch(() => ({ script: [] })),
      ])
      const nextAds = Array.isArray(adData) ? adData : (adData.ads || [])
      setAds(nextAds)
      setScriptLength(Array.isArray(scriptData?.script) ? scriptData.script.length : 0)
      setAdAssets({})
      setInsertLines(savedLines)
      setAssetLabels({})
      setAssetFiles({})
    } catch {
      setAds([])
      setScriptLength(0)
      setInsertLines(savedLines)
    }
  }

  const epId = activeEp?.episode_id || activeEp?.id

  const handleGenerate = async (form) => {
    if (!epId) return
    setGenerating(true)
    try {
      const res = await api.generateAd(epId, form)
      showToast('Ad generated ✓')
      setShowCreate(false)
      await selectEpisode(activeEp)
      setSelectedAd(res)
    } catch (e) {
      showToast('Generate failed: ' + e.message.slice(0, 80))
    } finally { setGenerating(false) }
  }

  const loadAdAssets = async (adId) => {
    if (!epId || !adId) return
    try {
      const items = await api.listAdAssets(epId, adId)
      setAdAssets((prev) => ({ ...prev, [adId]: items }))
    } catch {
      setAdAssets((prev) => ({ ...prev, [adId]: [] }))
    }
  }

  const toggleAd = async (ad) => {
    const next = selectedAd?.ad_id === ad.ad_id ? null : ad
    setSelectedAd(next)
    if (next && !(next.ad_id in adAssets)) {
      await loadAdAssets(next.ad_id)
    }
  }

  const handleProduce = async (adId) => {
    if (!epId || !adId) return
    setProducingAdId(adId)
    try {
      const produced = await api.produceAd(epId, adId)
      setAds((prev) => prev.map((ad) => (ad.ad_id === adId ? { ...ad, ...produced } : ad)))
      setSelectedAd((prev) => (prev?.ad_id === adId ? { ...prev, ...produced } : prev))
      showToast('Ad audio produced ✓')
    } catch (e) {
      showToast('Produce failed: ' + e.message.slice(0, 80))
    } finally {
      setProducingAdId('')
    }
  }

  const handleInsert = async (adId) => {
    if (!epId || !adId) return
    setInsertingAdId(adId)
    try {
      const lineIndex = Number(insertLines[adId] ?? scriptLength)
      await api.insertAd(epId, adId, lineIndex)
      setScriptLength((prev) => prev + (ads.find((ad) => ad.ad_id === adId)?.script?.split(' ').length ? 0 : 0))
      showToast(`Inserted ad at line ${lineIndex + 1} ✓`)
      const scriptData = await api.getScript(epId).catch(() => ({ script: [] }))
      setScriptLength(Array.isArray(scriptData?.script) ? scriptData.script.length : scriptLength)
    } catch (e) {
      showToast('Insert failed: ' + e.message.slice(0, 80))
    } finally {
      setInsertingAdId('')
    }
  }

  const handleAssetUpload = async (adId) => {
    const file = assetFiles[adId]
    if (!epId || !adId || !file) return
    setUploadingAdId(adId)
    try {
      await api.uploadAdAsset(epId, adId, file, assetLabels[adId] || '')
      setAssetFiles((prev) => ({ ...prev, [adId]: null }))
      setAssetLabels((prev) => ({ ...prev, [adId]: '' }))
      await loadAdAssets(adId)
      showToast('Ad asset uploaded ✓')
    } catch (e) {
      showToast('Upload failed: ' + e.message.slice(0, 80))
    } finally {
      setUploadingAdId('')
    }
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

      {/* CENTER — ad list */}
      <div className="pane-main">
        <div className="section-head">
          <span className="section-label">
            {activeEp ? `${activeEp.title || epId} — Ads (${ads.length})` : 'Select an episode'}
          </span>
          <button className="btn btn-gold btn-sm" onClick={() => setShowCreate(true)} disabled={!activeEp}>
            <Zap size={10} /> GENERATE AD
          </button>
          <button className="icon-btn" onClick={() => activeEp && selectEpisode(activeEp)} title="Refresh">
            <RefreshCw size={10} />
          </button>
        </div>

        <div className="scrollable" style={{ padding: '10px 14px' }}>
          {!activeEp && <Empty msg="← Select an episode" />}
          {activeEp && ads.length === 0 && (
            <div style={{ textAlign: 'center', paddingTop: '3rem' }}>
              <Empty msg="No ads yet — generate one above" />
              <button className="btn btn-gold" style={{ marginTop: 14 }} onClick={() => setShowCreate(true)}>
                <Zap size={11} /> Generate First Ad
              </button>
            </div>
          )}
          {ads.map((ad, i) => (
            <div
              key={ad.ad_id || i}
              className={`ad-card${selectedAd?.ad_id === ad.ad_id ? ' selected' : ''}`}
              onClick={() => toggleAd(ad)}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                <span className="font-display" style={{ fontSize: '.9rem', color: 'var(--bone)', letterSpacing: '.06em' }}>
                  {ad.title || ad.ad_type || `Ad #${i + 1}`}
                </span>
                <Badge type="gold">{ad.ad_type || 'custom'}</Badge>
                <Badge type={ad.audio_file ? 'green' : 'steel'}>{ad.audio_file ? 'produced' : (ad.status || 'draft')}</Badge>
              </div>
              <div className="font-mono" style={{ fontSize: '.55rem', color: 'var(--steel)', marginBottom: 6 }}>
                Voice: {ad.voice || '—'} · Tone: {ad.tone || '—'} · {ad.duration_seconds ? `${ad.duration_seconds}s` : '—'}
              </div>
              {ad.script && (
                <div style={{ fontSize: '.75rem', color: 'var(--bone)', opacity: .7, lineHeight: 1.5, maxHeight: selectedAd?.ad_id === ad.ad_id ? 'none' : 48, overflow: 'hidden' }}>
                  {ad.script}
                </div>
              )}
              {selectedAd?.ad_id === ad.ad_id && (
                <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 10 }} onClick={(e) => e.stopPropagation()}>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                    <button className="btn btn-gold btn-sm" onClick={() => handleProduce(ad.ad_id)} disabled={producingAdId === ad.ad_id}>
                      {producingAdId === ad.ad_id ? <Spinner size={11} /> : <Zap size={10} />} PRODUCE AUDIO
                    </button>
                    {ad.audio_file && (
                      <button className="btn btn-steel btn-sm" onClick={() => window.open(api.adAudioUrl(epId, ad.ad_id), '_blank')}>
                        <Download size={9} /> DOWNLOAD
                      </button>
                    )}
                  </div>

                  {ad.audio_file && (
                    <audio controls style={{ width: '100%' }} src={api.adAudioUrl(epId, ad.ad_id)} />
                  )}

                  <div style={{ display: 'grid', gridTemplateColumns: '160px 1fr auto', gap: 8, alignItems: 'end' }}>
                    <Field label={`Insert Before Line (${scriptLength} total)`}>
                      <input
                        className="ds-input"
                        type="number"
                        min="0"
                        max={scriptLength}
                        value={insertLines[ad.ad_id] ?? scriptLength}
                        onChange={(e) => {
                          const next = { ...insertLines, [ad.ad_id]: e.target.value }
                          setInsertLines(next)
                          if (epId) localStorage.setItem(`dandy_insert_lines_${epId}`, JSON.stringify(next))
                        }}
                      />
                    </Field>
                    <div />
                    <button className="btn btn-steel btn-sm" onClick={() => handleInsert(ad.ad_id)} disabled={insertingAdId === ad.ad_id}>
                      {insertingAdId === ad.ad_id ? <Spinner size={11} /> : null} INSERT INTO EPISODE
                    </button>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr auto', gap: 8, alignItems: 'end' }}>
                    <Field label="Ad Asset Label">
                      <input
                        className="ds-input"
                        value={assetLabels[ad.ad_id] || ''}
                        onChange={(e) => setAssetLabels((prev) => ({ ...prev, [ad.ad_id]: e.target.value }))}
                        placeholder="product shot, infographic, slide"
                      />
                    </Field>
                    <Field label="Upload File">
                      <input
                        className="ds-input"
                        type="file"
                        onChange={(e) => setAssetFiles((prev) => ({ ...prev, [ad.ad_id]: e.target.files?.[0] || null }))}
                      />
                    </Field>
                    <button className="btn btn-steel btn-sm" onClick={() => handleAssetUpload(ad.ad_id)} disabled={uploadingAdId === ad.ad_id || !assetFiles[ad.ad_id]}>
                      {uploadingAdId === ad.ad_id ? <Spinner size={11} /> : <Upload size={10} />} UPLOAD ASSET
                    </button>
                  </div>

                  <div>
                    <div className="font-mono" style={{ fontSize: '.55rem', color: 'var(--steel)', marginBottom: 6 }}>
                      Assets: {(adAssets[ad.ad_id] || []).length}
                    </div>
                    {(adAssets[ad.ad_id] || []).length === 0 ? (
                      <div style={{ fontSize: '.72rem', color: 'var(--steel)' }}>No ad assets uploaded.</div>
                    ) : (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                        {(adAssets[ad.ad_id] || []).map((asset) => (
                          <div key={asset.asset_id} style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'center' }}>
                            <div style={{ minWidth: 0 }}>
                              <div style={{ fontSize: '.72rem', color: 'var(--bone)', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                {asset.label || asset.original_name}
                              </div>
                              <div className="font-mono" style={{ fontSize: '.52rem', color: 'var(--steel)' }}>
                                {asset.original_name}
                              </div>
                            </div>
                            <button className="btn btn-steel btn-sm" onClick={() => window.open(api.adAssetFileUrl(epId, ad.ad_id, asset.asset_id), '_blank')}>
                              OPEN
                            </button>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* RIGHT — presets */}
      <div className="pane-right">
        <SectionHead label="Presets" />
        <div className="scrollable" style={{ padding: '10px 12px' }}>
          {presets.length === 0 && <Empty msg="No presets loaded" />}
          {presets.map((p, i) => (
            <div key={i} className="preset-card" onClick={() => { setShowCreate(true) }}>
              <div style={{ fontSize: '.78rem', fontWeight: 600, color: 'var(--bone)', marginBottom: 4 }}>
                {p.name || p.preset_id || `Preset ${i + 1}`}
              </div>
              <div className="font-mono" style={{ fontSize: '.5rem', color: 'var(--steel)' }}>
                {p.duration_seconds ? `${p.duration_seconds}s` : ''} {p.tone || ''}
              </div>
            </div>
          ))}
        </div>
      </div>

      {showCreate && (
        <GenerateAdModal
          epId={epId}
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

function GenerateAdModal({ epId, presets, onClose, onGenerate, generating }) {
  const [form, setForm] = useState({
    ad_type: 'sponsor_60s',
    voice: 'INTRO_MALE',
    tone: 'confident',
    product: '',
    tagline: '',
    cta: '',
    duration_seconds: 60,
    custom_script: '',
  })
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  return (
    <Modal
      title="Generate Ad"
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
          <Field label="Ad Type">
            <select className="ds-select" value={form.ad_type} onChange={e => set('ad_type', e.target.value)}>
              {AD_TYPES.map(t => <option key={t}>{t}</option>)}
            </select>
          </Field>
          <Field label="Voice">
            <select className="ds-select" value={form.voice} onChange={e => set('voice', e.target.value)}>
              {AD_VOICES.map(v => <option key={v}>{v}</option>)}
            </select>
          </Field>
          <Field label="Tone">
            <select className="ds-select" value={form.tone} onChange={e => set('tone', e.target.value)}>
              {TONE_OPTS.map(t => <option key={t}>{t}</option>)}
            </select>
          </Field>
          <Field label={`Duration: ${form.duration_seconds}s`}>
            <input type="range" min={10} max={90} step={5} value={form.duration_seconds} onChange={e => set('duration_seconds', +e.target.value)} />
          </Field>
        </div>
        <Field label="Product / Show Name">
          <input className="ds-input" value={form.product} onChange={e => set('product', e.target.value)} placeholder="e.g. Dandy Studio" />
        </Field>
        <Field label="Tagline">
          <input className="ds-input" value={form.tagline} onChange={e => set('tagline', e.target.value)} placeholder="e.g. Spin episodes in minutes" />
        </Field>
        <Field label="Call to Action">
          <input className="ds-input" value={form.cta} onChange={e => set('cta', e.target.value)} placeholder="e.g. Try Dandy Studio" />
        </Field>
        <Field label="Custom Script (optional — overrides generated)">
          <textarea className="ds-textarea" value={form.custom_script} onChange={e => set('custom_script', e.target.value)} placeholder="Paste a custom ad script here, or leave blank to generate one…" />
        </Field>
      </div>
    </Modal>
  )
}
