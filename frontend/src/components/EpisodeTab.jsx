// components/EpisodeTab.jsx
import { useState, useEffect, useRef, useCallback } from 'react'
import {
  Plus, RefreshCw, Zap, Play, Download, FileText,
  Clock, History, MessageSquare, Upload, Mic, ChevronDown,
  Trash2, ArrowUp, ArrowDown, Edit2, Check, X, Wifi, Settings,
  Cpu, AlertTriangle
} from 'lucide-react'
import { api, wordsToSeconds, secondsToDisplay } from '../lib/api'
import { Modal, Field, StatBox, SectionHead, Spinner, Empty, Badge, Divider, Toast } from './ui'
import { useToast } from '../hooks/useToast'

const SPEAKERS = ['PHIL', 'JIM', 'HOST', 'GUEST', 'INTRO_MALE', 'INTRO_FEMALE']
const SPK_CLASS = {
  PHIL: 'spk-phil', JIM: 'spk-jim', HOST: 'spk-host',
  GUEST: 'spk-guest', INTRO_MALE: 'spk-ad', INTRO_FEMALE: 'spk-ad',
}

export default function EpisodeTab() {
  const { toast, showToast } = useToast()
  const [episodes, setEpisodes]     = useState([])
  const [activeEp, setActiveEp]     = useState(null)
  const [script, setScript]         = useState(null)
  const [loading, setLoading]       = useState(false)
  const [generating, setGenerating] = useState(false)
  const [producing, setProducing]   = useState(false)
  const [stoppingGenerate, setStoppingGenerate] = useState(false)
  const [stoppingProduce, setStoppingProduce]   = useState(false)

  const [showCreate,   setShowCreate]   = useState(false)
  const [showVersions, setShowVersions] = useState(false)
  const [showFeedback, setShowFeedback] = useState(false)
  const [showAssets,   setShowAssets]   = useState(false)
  const [showCue,      setShowCue]      = useState(false)
  const [showExport,   setShowExport]   = useState(false)
  const [showEditConfig, setShowEditConfig] = useState(false)

  const [selectedLine, setSelectedLine] = useState(null)
  const [editingLine,  setEditingLine] = useState(null)
  const [versions,     setVersions]     = useState([])
  const [assets,       setAssets]       = useState([])
  const [feedbackText, setFeedbackText] = useState('')

  const wsRef = useRef(null)
  const [wsLog,       setWsLog]       = useState([])
  const [wsConnected, setWsConnected] = useState(false)

  const [writerStatus, setWriterStatus] = useState(null)

  const loadWriterStatus = useCallback(async () => {
    try {
      const s = await api.writerStatus()
      setWriterStatus(s)
    } catch {
      setWriterStatus({ bridge_reachable: false, active_writer: 'unavailable', warning: 'Could not reach backend.' })
    }
  }, [])

  useEffect(() => {
    loadWriterStatus()
    const id = setInterval(loadWriterStatus, 30000)
    return () => clearInterval(id)
  }, [])

  // ── Load episodes ──────────────────────────────────────────────────
  const loadEpisodes = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.listEpisodes()
      const list = Array.isArray(data) ? data : (data.episodes || [])
      setEpisodes(list)
      if (list.length && !activeEp) selectEpisode(list[0])
    } catch {
      showToast('Could not load episodes - is the API proxy online?')
    } finally { setLoading(false) }
  }, [activeEp])

  useEffect(() => { loadEpisodes() }, [])

  const selectEpisode = async (ep) => {
    const id = ep.episode_id || ep.id
    setActiveEp(ep)
    setSelectedLine(null)
    setEditingLine(null)
    setScript(null)
    try {
      const detail = await api.getEpisode(id)
      setActiveEp({ ...ep, ...detail, config: detail.config || ep.config || {} })
    } catch {
      setActiveEp(ep)
    }
    try {
      const s = await api.getScript(id)
      setScript(s)
    } catch { setScript(null) }
    try {
      const a = await api.listAssets(id)
      setAssets(Array.isArray(a) ? a : (a.assets || []))
    } catch { setAssets([]) }
  }

  const epId = activeEp?.episode_id || activeEp?.id

  // ── Computed stats ─────────────────────────────────────────────────
  const lines     = script?.lines || script?.script || []
  const philLines = lines.filter(l => (l.speaker || '').toUpperCase() === 'PHIL').length
  const jimLines  = lines.filter(l => (l.speaker || '').toUpperCase() === 'JIM').length
  const hostLines = lines.filter(l => (l.speaker || '').toUpperCase() === 'HOST').length
  const adLines   = lines.filter(l => ['INTRO_MALE','INTRO_FEMALE'].includes((l.speaker||'').toUpperCase())).length
  const allText   = lines.map(l => l.text || l.line || '').join(' ')
  const runtimeSec  = wordsToSeconds(allText)
  const runtimeMin  = runtimeSec / 60
  const configuredTargetSeconds = Number(activeEp?.config?.target_duration || activeEp?.target_duration || 600)
  const targetMinutes = Math.max(1, Math.min(15, Math.round(configuredTargetSeconds / 60)))
  const targetOk = runtimeMin >= targetMinutes * 0.75 && runtimeMin <= targetMinutes * 1.25

  // ── Actions ────────────────────────────────────────────────────────
  const handleGenerate = async () => {
    if (!activeEp) return
    setGenerating(true)
    try {
      const result = await api.generateScript(epId)
      if (result?.status === 'cancelled') {
        showToast('Generation cancelled')
        await selectEpisode(activeEp)
        return
      }
      showToast('Script generated ✓')
      await selectEpisode(activeEp)
    } catch (e) {
      showToast('Generate failed: ' + e.message.slice(0, 80))
    } finally { setGenerating(false) }
  }

  const handleStopGenerate = async () => {
    if (!activeEp) return
    setStoppingGenerate(true)
    try {
      await api.cancelEpisodeJob(epId)
      showToast('Generate stop requested')
      await selectEpisode(activeEp)
    } catch (e) {
      showToast('Stop generate failed: ' + e.message.slice(0, 80))
    } finally { setStoppingGenerate(false) }
  }

  const handleProduce = async () => {
    if (!activeEp) return
    if (writerStatus && !writerStatus.bridge_reachable) {
      const ok = window.confirm(
        'LLM Bridge is OFFLINE.\n\nProduction will use SKG fallback — the older template-based writer.\nThis may produce lower-quality or repetitive output.\n\nContinue anyway?'
      )
      if (!ok) return
    }
    setProducing(true)
    try {
      await api.produce(epId)
      await selectEpisode(activeEp)
      showToast('Production queued ✓  — watch logs/produce_demo.log')
    } catch (e) {
      showToast('Produce failed: ' + e.message.slice(0, 80))
    } finally { setProducing(false) }
  }

  const handleStopProduce = async () => {
    if (!activeEp) return
    setStoppingProduce(true)
    try {
      await api.cancelEpisodeJob(epId)
      showToast('Production stop requested')
      await selectEpisode(activeEp)
    } catch (e) {
      showToast('Stop produce failed: ' + e.message.slice(0, 80))
    } finally { setStoppingProduce(false) }
  }

  const handleExport = async (format) => {
    if (!epId) return
    try {
      const data = await api.exportEpisode(epId, format)
      const blob = new Blob([typeof data === 'string' ? data : JSON.stringify(data, null, 2)], { type: 'text/plain' })
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = `episode_${epId}.${format}`
      a.click()
      showToast(`Exported as .${format}`)
      setShowExport(false)
    } catch (e) { showToast('Export failed: ' + e.message.slice(0, 60)) }
  }

  // ── Line editing ───────────────────────────────────────────────────
  const saveLineEdit = async () => {
    if (!editingLine || !epId) return
    try {
      await api.editScript({
        episode_id: epId,
        action: 'modify_line',
        line_index: editingLine.index,
        speaker: editingLine.speaker,
        text: editingLine.text,
      })
      showToast('Line updated')
      setEditingLine(null)
      await selectEpisode(activeEp)
    } catch (e) { showToast('Edit failed: ' + e.message.slice(0, 60)) }
  }

  const addLineAfter = async (index) => {
    if (!epId) return
    try {
      await api.editScript({ episode_id: epId, action: 'add_line', after_index: index, speaker: 'PHIL', text: '' })
      await selectEpisode(activeEp)
      showToast('Line added')
    } catch { showToast('Add line failed') }
  }

  const deleteLine = async (index) => {
    if (!epId || !window.confirm('Delete this line?')) return
    try {
      await api.editScript({ episode_id: epId, action: 'delete_line', line_index: index })
      await selectEpisode(activeEp)
      showToast('Line deleted')
    } catch { showToast('Delete failed') }
  }

  const moveLine = async (index, dir) => {
    if (!epId) return
    try {
      await api.editScript({ episode_id: epId, action: 'move_line', line_index: index, direction: dir > 0 ? 'down' : 'up' })
      await selectEpisode(activeEp)
    } catch { showToast('Move failed') }
  }

  // ── Versions ───────────────────────────────────────────────────────
  const loadVersions = async () => {
    if (!epId) return
    try {
      const v = await api.getVersions(epId)
      setVersions(Array.isArray(v) ? v : (v.versions || []))
    } catch { setVersions([]) }
    setShowVersions(true)
  }

  const doRollback = async (version) => {
    if (!epId || !window.confirm(`Rollback to version ${version}?`)) return
    try {
      await api.rollback(epId, version)
      showToast('Rolled back ✓')
      setShowVersions(false)
      await selectEpisode(activeEp)
    } catch { showToast('Rollback failed') }
  }

  // ── Feedback ───────────────────────────────────────────────────────
  const submitFeedback = async () => {
    if (!epId || !feedbackText.trim()) return
    try {
      await api.submitFeedback(epId, feedbackText)
      showToast('Feedback submitted ✓')
      setFeedbackText('')
      setShowFeedback(false)
    } catch { showToast('Feedback failed') }
  }

  // ── Assets ─────────────────────────────────────────────────────────
  const fileRef = useRef(null)
  const [assetLabel, setAssetLabel] = useState('')
  const [assetDesc,  setAssetDesc]  = useState('')
  const [assetRole,  setAssetRole]  = useState('sfx')

  // Persist asset form fields per-episode in localStorage
  useEffect(() => {
    if (!epId) return
    const saved = JSON.parse(localStorage.getItem(`dandy_asset_form_${epId}`) || '{}')
    setAssetLabel(saved.label || '')
    setAssetDesc(saved.desc || '')
    setAssetRole(saved.role || 'sfx')
  }, [epId])

  const saveAssetForm = (label, desc, role) => {
    if (!epId) return
    localStorage.setItem(`dandy_asset_form_${epId}`, JSON.stringify({ label, desc, role }))
  }

  const uploadAsset = async (file) => {
    if (!epId || !file) return
    const fd = new FormData()
    fd.append('file', file)
    fd.append('label', assetLabel || file.name)
    fd.append('description', assetDesc)
    fd.append('role', assetRole)
    try {
      await api.uploadAsset(epId, fd)
      showToast('Asset uploaded ✓')
      const a = await api.listAssets(epId)
      setAssets(Array.isArray(a) ? a : (a.assets || []))
    } catch { showToast('Upload failed') }
  }

  // ── WebSocket ──────────────────────────────────────────────────────
  const connectWs = () => {
    if (!epId) return
    if (wsRef.current) wsRef.current.close()
    const ws = new WebSocket(`ws://${location.host}/ws/${epId}`)
    ws.onopen    = () => { setWsConnected(true);  setWsLog(l => [...l, '✓ connected']) }
    ws.onmessage = e => setWsLog(l => [...l, e.data].slice(-80))
    ws.onclose   = () => { setWsConnected(false); setWsLog(l => [...l, '✗ disconnected']) }
    wsRef.current = ws
  }

  // ── Media cue ──────────────────────────────────────────────────────
  const [cueForm, setCueForm] = useState({ line_index: 0, cue_type: 'sfx', asset_id: '', note: '' })
  const addCue = async () => {
    if (!epId) return
    try {
      await api.addMediaCue(epId, cueForm)
      showToast('Cue added ✓')
      setShowCue(false)
      await selectEpisode(activeEp)
    } catch { showToast('Cue failed') }
  }

  return (
    <div className="tab-body">

      {/* ── LEFT: Episode list ── */}
      <div className="pane-left">
        <SectionHead label="Episodes">
          <button className="btn btn-gold btn-sm" onClick={() => setShowCreate(true)}>
            <Plus size={10} /> NEW
          </button>
          <button className="icon-btn" onClick={loadEpisodes} title="Refresh">
            <RefreshCw size={10} />
          </button>
        </SectionHead>

        <div className="scrollable">
          {loading && <Empty msg="Loading…" />}
          {!loading && episodes.length === 0 && <Empty msg="No episodes found" />}
          {episodes.map(ep => {
            const id     = ep.episode_id || ep.id
            const isActive = epId === id
            return (
              <div
                key={id}
                className={`ep-row${isActive ? ' active' : ''}`}
                onClick={() => selectEpisode(ep)}
              >
                <div className="ep-num">EP {String(id).slice(0, 12).toUpperCase()}</div>
                <div className="ep-title">{ep.title || ep.name || id}</div>
                <div className="ep-meta">
                  {ep.target_duration && (
                    <span className="font-mono" style={{ fontSize: '.46rem', color: 'var(--steel)' }}>
                      {Math.round(ep.target_duration / 60)}m
                    </span>
                  )}
                  <Badge type={ep.status === 'completed' ? 'green' : ep.status === 'editing' ? 'blue' : 'steel'}>
                    {ep.status || 'draft'}
                  </Badge>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* ── CENTER: Script editor ── */}
      <div className="pane-main">
        {/* Toolbar */}
        <div className="section-head" style={{ height: 'auto', padding: '.65rem 14px', flexWrap: 'wrap', gap: 6 }}>
          <div style={{ flex: 1, minWidth: 160 }}>
            <div className="font-display" style={{ fontSize: '1.25rem', letterSpacing: '.08em', color: 'var(--bone)', lineHeight: 1 }}>
              {activeEp?.title || 'Select an episode'}
            </div>
            {activeEp && (
              <div className="gap-row" style={{ marginTop: 4 }}>
                <Badge type={targetOk ? 'green' : 'gold'}>
                  {secondsToDisplay(runtimeSec)} / {targetMinutes}m target
                </Badge>
                <span className="font-mono" style={{ fontSize: '.46rem', color: 'var(--steel)' }}>
                  {lines.length} lines
                </span>
              </div>
            )}
          </div>
          <div className="gap-row" style={{ flexWrap: 'wrap' }}>
            <button className="btn btn-gold" onClick={handleGenerate} disabled={!activeEp || generating}>
              <Zap size={11} /> {generating ? 'GEN…' : 'GENERATE'}
            </button>
            <button className="btn btn-steel" onClick={handleStopGenerate} disabled={!activeEp || stoppingGenerate}>
              <X size={11} /> {stoppingGenerate ? 'STOPPING' : 'STOP GEN'}
            </button>
            <button className="btn btn-steel" onClick={() => setShowEditConfig(true)} disabled={!activeEp}>
              <Settings size={11} /> CONFIG
            </button>
            <button className="btn btn-solid" onClick={handleProduce} disabled={!activeEp || producing}>
              <Play size={11} /> {producing ? 'QUEUING…' : 'PRODUCE'}
            </button>
            <button className="btn btn-steel" onClick={handleStopProduce} disabled={!activeEp || stoppingProduce}>
              <X size={11} /> {stoppingProduce ? 'STOPPING' : 'STOP PROD'}
            </button>
            <button className="btn btn-steel" onClick={() => setShowExport(true)} disabled={!activeEp}>
              <Download size={11} /> EXPORT
            </button>
            <button className="btn btn-steel" onClick={loadVersions} disabled={!activeEp}>
              <History size={11} /> VERSIONS
            </button>
            <button className="btn btn-steel" onClick={() => setShowFeedback(true)} disabled={!activeEp}>
              <MessageSquare size={11} /> FEEDBACK
            </button>
            <button className="btn btn-steel" onClick={() => setShowAssets(true)} disabled={!activeEp}>
              <FileText size={11} /> ASSETS
            </button>
            <button
              className={`btn btn-sm ${wsConnected ? 'btn-green' : 'btn-steel'}`}
              onClick={connectWs}
              disabled={!activeEp}
              title="Connect WebSocket"
            >
              <Wifi size={10} /> {wsConnected ? 'WS ON' : 'WS'}
            </button>
          </div>
        </div>

        {/* Script Engine indicator */}
        {(() => {
          const st = writerStatus
          const isLlm     = st?.active_writer === 'llm_bridge'
          const isLoading = st === null
          const backend   = st?.writer_backend
          const bg        = isLoading ? 'var(--rim)'
                          : isLlm    ? 'rgba(34,197,94,.12)'
                          :            'rgba(234,179,8,.10)'
          const dot       = isLoading ? '#6b7280'
                          : isLlm    ? '#22c55e'
                          :            '#eab308'
          const label     = isLoading           ? 'Script Engine: Checking…'
                          : isLlm && backend === 'llamacpp' ? 'Script Engine: llama.cpp Active'
                          : isLlm              ? 'Script Engine: LLM Bridge Active'
                          : st?.active_writer === 'unavailable' ? 'Script Engine: Unavailable'
                          :                      'Script Engine: SKG Fallback Active'
          return (
            <div style={{
              display: 'flex', alignItems: 'center', gap: 8,
              padding: '5px 14px',
              background: bg,
              borderBottom: '1px solid var(--rim)',
              flexShrink: 0,
            }}>
              <span style={{
                width: 8, height: 8, borderRadius: '50%',
                background: dot, flexShrink: 0,
                boxShadow: isLlm ? `0 0 6px ${dot}` : 'none',
              }} />
              <Cpu size={10} style={{ color: dot, flexShrink: 0 }} />
              <span style={{
                fontSize: '.52rem', fontFamily: 'var(--font-mono)',
                letterSpacing: '.06em', color: dot, fontWeight: 600,
              }}>
                {label}
              </span>
              {!isLoading && !isLlm && (
                <AlertTriangle size={10} style={{ color: dot, marginLeft: 4 }} />
              )}
              <button
                onClick={loadWriterStatus}
                style={{
                  marginLeft: 'auto', background: 'none', border: 'none',
                  cursor: 'pointer', color: 'var(--steel)', padding: 2,
                }}
                title="Refresh writer status"
              >
                <RefreshCw size={9} />
              </button>
            </div>
          )
        })()}

        {/* Stats bar */}
        {activeEp && (
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(7,1fr)',
            gap: 6,
            padding: '8px 14px',
            borderBottom: '1px solid var(--rim)',
            flexShrink: 0,
          }}>
            <StatBox val={lines.length} label="Lines" />
            <StatBox val={philLines}    label="Phil" />
            <StatBox val={jimLines}     label="Jim" />
            <StatBox val={hostLines}    label="Host" />
            <StatBox val={adLines}      label="Ads" />
            <StatBox val={assets.length} label="Assets" />
            <StatBox val={secondsToDisplay(runtimeSec)} label="Runtime" tone={targetOk ? 'ok' : 'warn'} />
          </div>
        )}

        {/* Script lines */}
        <div className="scrollable" style={{ padding: '8px 14px' }}>
          {!activeEp && <Empty msg="← Select an episode to begin" />}

          {activeEp && !script && <Empty msg="Loading script…" />}

          {activeEp && script && lines.length === 0 && (
            <div style={{ textAlign: 'center', paddingTop: '3rem' }}>
              <Empty msg="No script yet — click GENERATE to create one" />
              <button
                className="btn btn-gold"
                style={{ marginTop: '1rem' }}
                onClick={handleGenerate}
                disabled={generating}
              >
                <Zap size={11} /> {generating ? 'Generating…' : 'Generate Script'}
              </button>
            </div>
          )}

          {lines.map((line, idx) => {
            const isEditing  = editingLine?.index === idx
            const isSelected = selectedLine === idx
            const text    = line.text || line.line || ''
            const speaker = (line.speaker || 'PHIL').toUpperCase()

            return (
              <div
                key={idx}
                className={`script-line${isSelected ? ' selected' : ''}`}
                onClick={() => { if (!isEditing) setSelectedLine(isSelected ? null : idx) }}
              >
                <div className="script-line-head">
                  <span className="line-num">#{idx + 1}</span>

                  {isEditing ? (
                    <select
                      className="ds-select"
                      style={{ width: 96, fontSize: '.58rem', padding: '.2rem .4rem' }}
                      value={editingLine.speaker}
                      onChange={e => setEditingLine(l => ({ ...l, speaker: e.target.value }))}
                    >
                      {SPEAKERS.map(s => <option key={s}>{s}</option>)}
                    </select>
                  ) : (
                    <span className={`line-speaker ${SPK_CLASS[speaker] || 'spk-host'}`}>
                      {speaker}
                    </span>
                  )}

                  {isEditing ? (
                    <textarea
                      className="ds-textarea"
                      style={{ minHeight: 52, flex: 1, fontSize: '.78rem' }}
                      value={editingLine.text}
                      onChange={e => setEditingLine(l => ({ ...l, text: e.target.value }))}
                      autoFocus
                    />
                  ) : (
                    <span className={`line-text${isSelected ? ' expanded' : ''}`}>{text}</span>
                  )}

                  {isEditing ? (
                    <div className="gap-row" style={{ flexShrink: 0 }}>
                      <button className="icon-btn" onClick={saveLineEdit} title="Save"><Check size={10} /></button>
                      <button className="icon-btn" onClick={() => setEditingLine(null)} title="Cancel"><X size={10} /></button>
                    </div>
                  ) : isSelected ? (
                    <div className="gap-row" style={{ flexShrink: 0 }} onClick={e => e.stopPropagation()}>
                      <button className="icon-btn" title="Edit"      onClick={() => setEditingLine({ index: idx, speaker, text })}><Edit2 size={9} /></button>
                      <button className="icon-btn" title="Move up"   onClick={() => moveLine(idx, -1)}><ArrowUp size={9} /></button>
                      <button className="icon-btn" title="Move down" onClick={() => moveLine(idx, 1)}><ArrowDown size={9} /></button>
                      <button className="icon-btn" title="Add after" onClick={() => addLineAfter(idx)}><Plus size={9} /></button>
                      <button className="icon-btn del" title="Delete" onClick={() => deleteLine(idx)}><Trash2 size={9} /></button>
                      <button className="icon-btn" title="Add media cue" onClick={() => { setCueForm(c => ({...c, line_index: idx})); setShowCue(true) }}><Mic size={9} /></button>
                    </div>
                  ) : null}
                </div>
              </div>
            )
          })}

          {wsLog.length > 0 && (
            <div style={{ marginTop: 12 }}>
              <div className="section-label" style={{ marginBottom: 6 }}>WebSocket Log</div>
              <div className="code-block">{wsLog.join('\n')}</div>
            </div>
          )}
        </div>
      </div>

      {/* ── RIGHT: Audio + Quick add ── */}
      <div className="pane-right">
        <SectionHead label="Audio" />
        <div style={{ padding: '10px 12px', borderBottom: '1px solid var(--rim)' }}>
          {activeEp ? (
            <>
              <audio controls style={{ width: '100%', marginBottom: 8 }} src={api.audioUrl(epId)} />
              <button className="btn btn-gold" style={{ width: '100%' }} onClick={() => window.open(api.audioUrl(epId))}>
                <Download size={10} /> DOWNLOAD MP3
              </button>
            </>
          ) : (
            <Empty msg="Select episode" />
          )}
        </div>

        <SectionHead label="Quick Add Line" />
        <QuickAddLine
          epId={epId}
          onDone={() => activeEp && selectEpisode(activeEp)}
          showToast={showToast}
          disabled={!activeEp}
        />
      </div>

      {/* ── Modals ── */}
      {showEditConfig && activeEp && (
        <EditConfigModal
          episode={activeEp}
          onClose={() => setShowEditConfig(false)}
          onSaved={(updated) => {
            setActiveEp(ep => ({ ...ep, ...updated, config: updated }))
            setShowEditConfig(false)
            showToast('Config saved ✓')
          }}
          showToast={showToast}
        />
      )}

      {showCreate && (
        <CreateEpisodeModal
          onClose={() => setShowCreate(false)}
          onCreated={() => { setShowCreate(false); loadEpisodes(); showToast('Segment created ✓') }}
          showToast={showToast}
        />
      )}

      {showVersions && (
        <Modal title="Script Versions" onClose={() => setShowVersions(false)}>
          {versions.length === 0 && <Empty msg="No versions found" />}
          {versions.map((v, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid var(--rim)' }}>
              <div>
                <div className="font-mono" style={{ fontSize: '.62rem', color: 'var(--bone)' }}>
                  v{v.version || v.version_id || i + 1}
                </div>
                <div className="font-mono" style={{ fontSize: '.52rem', color: 'var(--steel)' }}>
                  {v.created_at || v.timestamp || '—'} · {v.lines || '?'} lines
                </div>
              </div>
              <button className="btn btn-gold btn-sm" onClick={() => doRollback(v.version || v.version_id || i + 1)}>
                ROLLBACK
              </button>
            </div>
          ))}
        </Modal>
      )}

      {showFeedback && (
        <Modal
          title="Episode Feedback"
          onClose={() => setShowFeedback(false)}
          footer={<>
            <button className="btn btn-steel" onClick={() => setShowFeedback(false)}>CANCEL</button>
            <button className="btn btn-solid" onClick={submitFeedback}>SUBMIT</button>
          </>}
        >
          <Field label="Feedback">
            <textarea
              className="ds-textarea"
              style={{ minHeight: 120 }}
              value={feedbackText}
              onChange={e => setFeedbackText(e.target.value)}
              placeholder="Enter feedback for this episode…"
            />
          </Field>
        </Modal>
      )}

      {showAssets && (
        <Modal title="Episode Assets" onClose={() => setShowAssets(false)} wide>
          <div style={{ marginBottom: 14 }}>
            <div className="section-label" style={{ marginBottom: 8 }}>Upload New Asset</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 8 }}>
              <Field label="Label">
                <input className="ds-input" value={assetLabel} onChange={e => { setAssetLabel(e.target.value); saveAssetForm(e.target.value, assetDesc, assetRole) }} placeholder="Asset label" />
              </Field>
              <Field label="Role">
                <select className="ds-select" value={assetRole} onChange={e => { setAssetRole(e.target.value); saveAssetForm(assetLabel, assetDesc, e.target.value) }}>
                  {['sfx', 'music', 'voice', 'image', 'document'].map(r => <option key={r}>{r}</option>)}
                </select>
              </Field>
            </div>
            <Field label="Description">
              <input className="ds-input" value={assetDesc} onChange={e => { setAssetDesc(e.target.value); saveAssetForm(assetLabel, e.target.value, assetRole) }} placeholder="Optional description" />
            </Field>
            <input type="file" ref={fileRef} style={{ display: 'none' }} onChange={e => uploadAsset(e.target.files[0])} />
            <button className="btn btn-gold" style={{ marginTop: 10 }} onClick={() => fileRef.current?.click()}>
              <Upload size={11} /> CHOOSE FILE & UPLOAD
            </button>
          </div>
          <Divider />
          <div className="section-label" style={{ marginBottom: 8 }}>Attached Assets ({assets.length})</div>
          {assets.length === 0 && <Empty msg="No assets attached" />}
          {assets.map((a, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 10px', border: '1px solid var(--rim)', marginBottom: 6, borderRadius: 'var(--radius)', background: 'var(--surface)' }}>
              <div>
                <div style={{ fontSize: '.8rem', fontWeight: 600 }}>{a.label || a.filename || a.name}</div>
                <div className="font-mono" style={{ fontSize: '.5rem', color: 'var(--steel)' }}>{a.role} · {a.description || '—'}</div>
              </div>
              <a href={api.assetUrl(epId, a.asset_id || a.id)} target="_blank" rel="noreferrer">
                <button className="btn btn-steel btn-sm"><Download size={9} /> OPEN</button>
              </a>
            </div>
          ))}
        </Modal>
      )}

      {showExport && (
        <Modal title="Export Script" onClose={() => setShowExport(false)}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {['json', 'txt', 'srt'].map(fmt => (
              <button key={fmt} className="btn btn-steel" style={{ width: '100%', justifyContent: 'flex-start', height: 40 }} onClick={() => handleExport(fmt)}>
                <Download size={12} /> Export as .{fmt.toUpperCase()}
              </button>
            ))}
          </div>
        </Modal>
      )}

      {showCue && (
        <Modal
          title="Add Media Cue"
          onClose={() => setShowCue(false)}
          footer={<>
            <button className="btn btn-steel" onClick={() => setShowCue(false)}>CANCEL</button>
            <button className="btn btn-solid" onClick={addCue}>ADD CUE</button>
          </>}
        >
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <Field label="Line Index">
              <input className="ds-input" type="number" value={cueForm.line_index} onChange={e => setCueForm(c => ({ ...c, line_index: +e.target.value }))} />
            </Field>
            <Field label="Cue Type">
              <select className="ds-select" value={cueForm.cue_type} onChange={e => setCueForm(c => ({ ...c, cue_type: e.target.value }))}>
                {['sfx', 'music', 'voice', 'transition'].map(t => <option key={t}>{t}</option>)}
              </select>
            </Field>
            <Field label="Asset">
              <select className="ds-select" value={cueForm.asset_id} onChange={e => setCueForm(c => ({ ...c, asset_id: e.target.value }))}>
                <option value="">— none —</option>
                {assets.map(a => <option key={a.asset_id || a.id} value={a.asset_id || a.id}>{a.label || a.filename}</option>)}
              </select>
            </Field>
            <Field label="Note">
              <input className="ds-input" value={cueForm.note} onChange={e => setCueForm(c => ({ ...c, note: e.target.value }))} placeholder="Optional note" />
            </Field>
          </div>
        </Modal>
      )}

      <Toast {...toast} />
    </div>
  )
}

// ── Edit Config Modal ─────────────────────────────────────────────────────────
function EditConfigModal({ episode, onClose, onSaved, showToast }) {
  const config = episode.config || episode
  const [form, setForm] = useState({
    title:               config.title || episode.title || '',
    topic:               config.topic || episode.topic || '',
    description:         config.description || '',
    key_points:          (Array.isArray(config.key_points) ? config.key_points : []).join('\n'),
    custom_instructions: config.custom_instructions || '',
    target_minutes:      Math.max(1, Math.min(15, Math.round((Number(config.target_duration) || 600) / 60))),
    intensity:           config.intensity || 'medium',
  })
  const [busy, setBusy] = useState(false)
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))
  const epId = episode.episode_id || episode.id

  const submit = async () => {
    if (!form.title.trim()) { showToast('Title required'); return }
    setBusy(true)
    try {
      const body = {
        ...form,
        target_duration: form.target_minutes * 60,
        target_word_count: form.target_minutes * 155,
        key_points: form.key_points.split('\n').map(s => s.trim()).filter(Boolean),
      }
      const res = await api.updateEpisodeConfig(epId, body)
      onSaved(res.config || body)
    } catch (e) {
      showToast('Save failed: ' + e.message.slice(0, 80))
    } finally { setBusy(false) }
  }

  return (
    <Modal
      title={`Edit Config — ${epId}`}
      onClose={onClose}
      footer={<>
        <button className="btn btn-steel" onClick={onClose}>CANCEL</button>
        <button className="btn btn-solid" onClick={submit} disabled={busy}>
          {busy ? <Spinner size={11} /> : <Check size={11} />} SAVE CONFIG
        </button>
      </>}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
          <Field label="Title">
            <input className="ds-input" value={form.title} onChange={e => set('title', e.target.value)} />
          </Field>
          <Field label="Intensity">
            <select className="ds-select" value={form.intensity} onChange={e => set('intensity', e.target.value)}>
              {['low', 'medium', 'high'].map(v => <option key={v}>{v}</option>)}
            </select>
          </Field>
        </div>
        <Field label="Main Topic">
          <input className="ds-input" value={form.topic} onChange={e => set('topic', e.target.value)} />
        </Field>
        <Field label="Description">
          <textarea className="ds-textarea" value={form.description} onChange={e => set('description', e.target.value)} />
        </Field>
        <Field label="Key Points (one per line)">
          <textarea className="ds-textarea" value={form.key_points} onChange={e => set('key_points', e.target.value)} placeholder={'Point 1\nPoint 2\nPoint 3'} />
        </Field>
        <Field label="Custom Instructions">
          <textarea className="ds-textarea" style={{ minHeight: 56 }} value={form.custom_instructions} onChange={e => set('custom_instructions', e.target.value)} placeholder="Special tone or format instructions…" />
        </Field>
        <Field label={`Segment Length: ${form.target_minutes}m`}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span className="font-mono" style={{ fontSize: '.5rem', color: 'var(--steel)' }}>1m</span>
            <input type="range" min={1} max={15} step={1} value={form.target_minutes} onChange={e => set('target_minutes', +e.target.value)} />
            <span className="font-mono" style={{ fontSize: '.5rem', color: 'var(--steel)' }}>15m</span>
          </div>
        </Field>
      </div>
    </Modal>
  )
}

// ── Create Episode Modal ──────────────────────────────────────────────────────
function CreateEpisodeModal({ onClose, onCreated, showToast }) {
  const [form, setForm] = useState({
    episode_id: '', title: '', topic: '', description: '',
    key_points: '', custom_instructions: '', target_minutes: 10,
  })
  const [busy, setBusy] = useState(false)
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))
  const targetWords = Math.round(form.target_minutes * 155)

  const submit = async () => {
    if (!form.title.trim()) { showToast('Title required'); return }
    setBusy(true)
    try {
      const body = {
        ...form,
        target_duration: form.target_minutes * 60,
        key_points: form.key_points.split('\n').map(s => s.trim()).filter(Boolean),
        target_word_count: targetWords,
      }
      const res = await api.createEpisode(body)
      onCreated(res)
    } catch (e) {
      showToast('Create failed: ' + e.message.slice(0, 80))
    } finally { setBusy(false) }
  }

  return (
    <Modal
      title="Create Segment"
      onClose={onClose}
      footer={<>
        <button className="btn btn-steel" onClick={onClose}>CANCEL</button>
        <button className="btn btn-solid" onClick={submit} disabled={busy}>
          {busy ? <Spinner size={11} /> : <Plus size={11} />} CREATE
        </button>
      </>}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
          <Field label="Episode ID">
            <input className="ds-input" value={form.episode_id} onChange={e => set('episode_id', e.target.value)} placeholder="e.g. ep_042" />
          </Field>
          <Field label="Title">
            <input className="ds-input" value={form.title} onChange={e => set('title', e.target.value)} placeholder="Segment title" />
          </Field>
        </div>
        <Field label="Main Topic">
          <input className="ds-input" value={form.topic} onChange={e => set('topic', e.target.value)} placeholder="What's this segment about?" />
        </Field>
        <Field label="Description">
          <textarea className="ds-textarea" value={form.description} onChange={e => set('description', e.target.value)} placeholder="Longer description / context…" />
        </Field>
        <Field label="Key Points (one per line)">
          <textarea className="ds-textarea" value={form.key_points} onChange={e => set('key_points', e.target.value)} placeholder={"Point 1\nPoint 2\nPoint 3"} />
        </Field>
        <Field label="Custom Instructions">
          <textarea className="ds-textarea" style={{ minHeight: 56 }} value={form.custom_instructions} onChange={e => set('custom_instructions', e.target.value)} placeholder="Any special tone/format instructions…" />
        </Field>
        <Field label={`Segment Length: ${form.target_minutes}m (~${targetWords.toLocaleString()} words)`}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span className="font-mono" style={{ fontSize: '.5rem', color: 'var(--steel)' }}>1m</span>
            <input type="range" min={1} max={15} step={1} value={form.target_minutes} onChange={e => set('target_minutes', +e.target.value)} />
            <span className="font-mono" style={{ fontSize: '.5rem', color: 'var(--steel)' }}>15m</span>
          </div>
        </Field>
      </div>
    </Modal>
  )
}

// ── Quick Add Line ────────────────────────────────────────────────────────────
function QuickAddLine({ epId, onDone, showToast, disabled }) {
  const [speaker, setSpeaker] = useState('PHIL')
  const [text,    setText]    = useState('')
  const [busy,    setBusy]    = useState(false)

  const submit = async () => {
    if (!epId || !text.trim()) return
    setBusy(true)
    try {
      await api.editScript({ episode_id: epId, action: 'add_line', speaker, text })
      setText('')
      onDone()
      showToast('Line added')
    } catch { showToast('Failed') }
    finally { setBusy(false) }
  }

  return (
    <div style={{ padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: 8 }}>
      <Field label="Speaker">
        <select className="ds-select" value={speaker} onChange={e => setSpeaker(e.target.value)} disabled={disabled}>
          {SPEAKERS.map(s => <option key={s}>{s}</option>)}
        </select>
      </Field>
      <Field label="Line">
        <textarea className="ds-textarea" style={{ minHeight: 64 }} value={text} onChange={e => setText(e.target.value)} placeholder="Dialogue text…" disabled={disabled} />
      </Field>
      <button className="btn btn-gold" onClick={submit} disabled={disabled || busy || !text.trim()}>
        {busy ? <Spinner size={11} /> : <Plus size={11} />} ADD LINE
      </button>
    </div>
  )
}
