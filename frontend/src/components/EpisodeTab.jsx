// components/EpisodeTab.jsx
import { useState, useEffect, useRef, useCallback } from 'react'
import {
  Plus, RefreshCw, Zap, Play, Download, FileText,
  History, MessageSquare, Upload, Mic,
  Trash2, ArrowUp, ArrowDown, Edit2, Check, X, Wifi, Settings,
  Cpu, AlertTriangle, Square
} from 'lucide-react'
import { api, wordsToSeconds, secondsToDisplay } from '../lib/api'
import { Modal, Field, StatBox, SectionHead, Spinner, Empty, Badge, Divider, Toast } from './ui'
import { useToast } from '../hooks/useToast'

const SPEAKERS = ['PHIL', 'JIM', 'BRYAN', 'HOST', 'GUEST', 'INTRO_MALE', 'INTRO_FEMALE']
const SPK_CLASS = {
  PHIL: 'spk-phil', JIM: 'spk-jim', HOST: 'spk-host',
  BRYAN: 'spk-host', GUEST: 'spk-guest', INTRO_MALE: 'spk-ad', INTRO_FEMALE: 'spk-ad',
}
const CUE_TYPES = ['sfx', 'ad', 'bumper', 'transition', 'intro', 'outro', 'music', 'voice']

export default function EpisodeTab({ episodeId, onEpisodeChange, onNavigate }) {
  const { toast, showToast } = useToast()
  const [episodes, setEpisodes]     = useState([])
  const [activeEp, setActiveEp]     = useState(null)
  const [script, setScript]         = useState(null)
  const [loading, setLoading]       = useState(false)
  const [generating, setGenerating] = useState(false)
  const [producing, setProducing]   = useState(false)
  const [generationProgress, setGenerationProgress] = useState(null)
  const [stage, setStage] = useState('generate')

  const [showCreate,   setShowCreate]   = useState(false)
  const [showVersions, setShowVersions] = useState(false)
  const [showFeedback, setShowFeedback] = useState(false)
  const [showAssets,   setShowAssets]   = useState(false)
  const [showCue,      setShowCue]      = useState(false)
  const [showExport,   setShowExport]   = useState(false)
  const [showEditConfig, setShowEditConfig] = useState(false)
  const [showScriptOverride, setShowScriptOverride] = useState(false)

  const [selectedLine, setSelectedLine] = useState(null)
  const [editingLine,  setEditingLine] = useState(null)
  const [versions,     setVersions]     = useState([])
  const [assets,       setAssets]       = useState([])
  const [feedbackText, setFeedbackText] = useState('')
  const [assetSearch, setAssetSearch] = useState('')
  const [overrideText, setOverrideText] = useState('')
  const [overrideBusy, setOverrideBusy] = useState(false)

  const wsRef = useRef(null)
  const [wsLog,       setWsLog]       = useState([])
  const [wsConnected, setWsConnected] = useState(false)
  const [writerStatus, setWriterStatus] = useState(null)
  const [productionManifest, setProductionManifest] = useState(null)
  const [editorReport, setEditorReport] = useState(null)
  const [revisionStatus, setRevisionStatus] = useState(null)
  const [audioRevision, setAudioRevision] = useState(0)
  const [canonicalVersions, setCanonicalVersions] = useState([])
  const [selectedCanonicalId, setSelectedCanonicalId] = useState('')
  const [productionDraft, setProductionDraft] = useState(null)
  const [editorDirty, setEditorDirty] = useState(false)
  const [editorBusy, setEditorBusy] = useState(false)

  const loadWriterStatus = useCallback(async () => {
    try {
      const s = await api.writerStatus()
      setWriterStatus(s)
    } catch {
      setWriterStatus({ bridge_reachable: false, active_writer: 'offline', warning: 'Could not reach backend.' })
    }
  }, [])

  useEffect(() => {
    loadWriterStatus()
    const id = setInterval(loadWriterStatus, 30000)
    return () => clearInterval(id)
  }, [loadWriterStatus])

  const loadEpisodes = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.listEpisodes()
      const list = Array.isArray(data) ? data : (data.episodes || [])
      setEpisodes(list)
      if (list.length && !activeEp) selectEpisode(list.find(ep => (ep.episode_id || ep.id) === episodeId) || list[0])
    } catch {
      showToast('Could not load episodes - is the API proxy online?')
    } finally { setLoading(false) }
  }, [activeEp])

  useEffect(() => { loadEpisodes() }, [])

  const selectEpisode = async (ep) => {
    const id = ep.episode_id || ep.id
    onEpisodeChange?.(id)
    setActiveEp(ep)
    setSelectedLine(null)
    setEditingLine(null)
    setStage('generate')
    setScript(null)
    setProductionManifest(null)
    setEditorReport(null)
    setProductionDraft(null)
    setEditorDirty(false)
    setRevisionStatus(null)
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
    try { setProductionManifest(await api.productionManifest(id)) }
    catch { setProductionManifest(null) }
    try {
      const canonical = await api.canonicalScripts(id)
      setCanonicalVersions(canonical.versions || [])
      setSelectedCanonicalId(canonical.active_version_id || '')
    } catch { setCanonicalVersions([]); setSelectedCanonicalId('') }
    try {
      const state = await api.productionEditor(id)
      setEditorReport(state)
      setProductionDraft(state.draft || null)
    } catch { setEditorReport(null); setProductionDraft(null) }
    try { setRevisionStatus(await api.productionRevision(id)) }
    catch { setRevisionStatus(null) }
  }

  const epId = activeEp?.episode_id || activeEp?.id
  useEffect(() => {
    if (!epId || revisionStatus?.status !== 'running') return undefined
    let active = true
    const poll = async () => {
      try {
        const state = await api.productionRevision(epId)
        if (!active) return
        setRevisionStatus(state)
        if (['completed', 'completed_with_warnings'].includes(state.status)) {
          setAudioRevision(Date.now())
          setProductionManifest(await api.productionManifest(epId))
          try { setEditorReport(await api.productionEditor(epId)) } catch { /* report remains available after production */ }
          showToast(state.error ? `Line take ${state.take} ready; metadata warning: ${state.error}` : `Line take ${state.take} ready`)
        } else if (['failed', 'interrupted'].includes(state.status)) {
          showToast(`Line revision failed: ${state.error}`)
        }
      } catch (error) {
        if (active) { setRevisionStatus({ status: 'failed', error: error.message }); showToast(`Line revision failed: ${error.message}`) }
      }
    }
    const timer = setInterval(poll, 2000)
    return () => { active = false; clearInterval(timer) }
  }, [epId, revisionStatus?.status])
  useEffect(() => {
    if (!epId || (!generating && !producing)) return undefined
    let active = true
    const poll = async () => {
      try {
        const state = await api.generationStatus(epId)
        if (!active) return
        setGenerationProgress(state)
        const status = state?.status || (typeof state?.episode_status === 'string' ? state.episode_status : state?.episode_status?.status)
        if (producing && ['produced', 'failed', 'cancelled'].includes(status)) {
          setProducing(false)
          if (status === 'produced') {
            setAudioRevision(Date.now())
            try { setProductionManifest(await api.productionManifest(epId)) } catch { setProductionManifest(null) }
            try { setEditorReport(await api.productionEditor(epId)) } catch { setEditorReport(null) }
          }
        }
      } catch { /* the main request reports the final error */ }
    }
    poll()
    const timer = setInterval(poll, 1000)
    return () => { active = false; clearInterval(timer) }
  }, [epId, generating, producing])

  const lines = script?.lines || script?.script || []
  const editorLines = productionDraft?.script || []
  const displayLines = stage === 'editor' ? editorLines
    : stage === 'produce' && editorReport?.approved?.script ? editorReport.approved.script : lines
  const philLines = displayLines.filter(l => (l.speaker || '').toUpperCase() === 'PHIL').length
  const jimLines  = displayLines.filter(l => (l.speaker || '').toUpperCase() === 'JIM').length
  const hostLines = displayLines.filter(l => (l.speaker || '').toUpperCase() === 'HOST').length
  const adLines   = displayLines.filter(l => ['INTRO_MALE','INTRO_FEMALE'].includes((l.speaker||'').toUpperCase())).length
  const allText   = displayLines.map(l => l.spoken_text || l.text || l.line || '').join(' ')
  const runtimeSec  = Math.round(wordsToSeconds(allText) + displayLines.reduce((sum, line) => sum + Number(line.pause_after || 0), 0))
  const runtimeMin  = runtimeSec / 60
  const configuredTargetSeconds = Number(activeEp?.config?.target_duration || activeEp?.target_duration || 1800)
  const targetMinutes = Math.max(5, Math.min(45, Math.round(configuredTargetSeconds / 60)))
  const targetOk = runtimeMin >= targetMinutes * 0.75 && runtimeMin <= targetMinutes * 1.25

  const visibleAssets = assets.filter((a) => {
    const q = assetSearch.trim().toLowerCase()
    if (!q) return true
    return [a.label, a.filename, a.original_name, a.role, a.relative_path, a.description]
      .filter(Boolean).join(' ').toLowerCase().includes(q)
  })

  const handleGenerate = async () => {
    if (!activeEp) return
    setGenerating(true)
    setGenerationProgress({ status: 'starting' })
    try {
      const result = await api.generateScript(epId)
      if (result?.status === 'cancelled') {
        showToast('Generation cancelled')
        await selectEpisode(activeEp)
        return
      }
      showToast('Script generated ✓')
      await selectEpisode(activeEp)
      setStage('generate')
    } catch (e) {
      showToast('Generate failed: ' + e.message.slice(0, 80))
    } finally { setGenerating(false) }
  }

  const handleProduce = async () => {
    if (!activeEp) return
    const approvedVersionId = editorReport?.current_approved_version_id
    if (!approvedVersionId || editorReport?.approval_state !== 'approved') {
      showToast('Open Production Editor and approve a production version first')
      setStage('editor')
      return
    }
    if (writerStatus && !writerStatus.bridge_reachable && lines.some(l => (l.generated_by || '') === 'llamacpp')) {
      showToast('Local llama.cpp writer is offline; saved script can still be produced')
    }
    setProducing(true)
    setGenerationProgress({ status: 'starting production' })
    try {
      await api.produce(epId, { approved_version_id: approvedVersionId })
      await selectEpisode(activeEp)
      showToast('Production queued ✓')
    } catch (e) {
      setProducing(false)
      showToast('Produce failed: ' + e.message.slice(0, 80))
    }
  }

  const regenerateLine = async (segmentId) => {
    if (!epId || revisionStatus?.status === 'running') return
    try {
      const result = await api.regenerateProductionLine(epId, segmentId, {
        reason: 'Operator requested a new voice take',
        text_change: null,
      })
      setRevisionStatus({ status: 'running', revision_id: result.revision_id, segment_id: segmentId })
      showToast(`Regenerating ${segmentId} only`)
    } catch (error) { showToast(`Regenerate failed: ${error.message}`) }
  }

  const handleStop = async () => {
    if (!epId || (!generating && !producing)) return
    try {
      await api.cancelJob(epId)
      setGenerationProgress(prev => ({ ...prev, status: 'cancellation_requested' }))
      showToast(generating ? 'Generation stop requested' : 'Production stop requested')
    } catch (e) {
      showToast('Stop failed: ' + e.message.slice(0, 100))
    }
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

  const openScriptOverride = () => {
    setOverrideText(lines.map((line) => `${String(line.speaker || 'PHIL').toUpperCase()}: ${line.text || line.line || ''}`).join('\n'))
    setShowScriptOverride(true)
  }

  const saveScriptOverride = async () => {
    if (!epId || !overrideText.trim()) return
    setOverrideBusy(true)
    try {
      const result = await api.replaceScript(epId, overrideText)
      showToast(`Script replaced ✓ — ${result.line_count || 0} lines`)
      setShowScriptOverride(false)
      await selectEpisode(activeEp)
    } catch (e) {
      showToast('Script replace failed: ' + e.message.slice(0, 90))
    } finally { setOverrideBusy(false) }
  }

  const saveLineEdit = async () => {
    if (!editingLine || !productionDraft) return
    const updated = productionDraft.script.map(line => line.production_line_id === editingLine.production_line_id
      ? { ...line, ...editingLine } : line)
    setProductionDraft({ ...productionDraft, script: updated })
    setEditorDirty(true)
    setEditingLine(null)
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

  const submitFeedback = async () => {
    if (!epId || !feedbackText.trim()) return
    try {
      await api.submitFeedback(epId, feedbackText)
      showToast('Feedback submitted ✓')
      setFeedbackText('')
      setShowFeedback(false)
    } catch { showToast('Feedback failed') }
  }

  const fileRef = useRef(null)
  const [assetLabel, setAssetLabel] = useState('')
  const [assetDesc,  setAssetDesc]  = useState('')
  const [assetRole,  setAssetRole]  = useState('sfx')

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

  const connectWs = () => {
    if (!epId) return
    if (wsRef.current) wsRef.current.close()
    const ws = new WebSocket(`ws://${location.host}/ws/${epId}`)
    ws.onopen    = () => { setWsConnected(true);  setWsLog(l => [...l, '✓ connected']) }
    ws.onmessage = e => setWsLog(l => [...l, e.data].slice(-80))
    ws.onclose   = () => { setWsConnected(false); setWsLog(l => [...l, '✗ disconnected']) }
    wsRef.current = ws
  }

  const [cueForm, setCueForm] = useState({ line_index: 0, cue_type: 'sfx', asset_id: '', note: '' })
  const addCue = async () => {
    if (!epId || !cueForm.asset_id || !productionDraft) return
    try {
      const media_cues = [...(productionDraft.media_cues || []), {
        cue_id: `cue_${Date.now()}`, cue_type: cueForm.cue_type, asset_id: cueForm.asset_id,
        line_number: cueForm.line_index, notes: cueForm.note,
      }]
      setProductionDraft({ ...productionDraft, media_cues })
      setEditorDirty(true)
      showToast('Media cue added ✓')
      setShowCue(false)
      await selectEpisode(activeEp)
    } catch (e) { showToast('Cue failed: ' + e.message.slice(0, 70)) }
  }

  const openProductionEditor = async () => {
    if (!epId || !selectedCanonicalId) return
    setEditorBusy(true)
    try {
      const state = await api.createProductionDraft(epId, selectedCanonicalId)
      setEditorReport(state)
      setProductionDraft(state.draft || null)
      setEditorDirty(false)
      setStage('editor')
      showToast('Production draft opened from ' + selectedCanonicalId)
    } catch (error) { showToast('Could not open editor: ' + error.message) }
    finally { setEditorBusy(false) }
  }

  const navigateStage = (nextStage) => {
    setStage(nextStage)
    if (nextStage === 'preview') onNavigate?.('preview')
    if (nextStage === 'editor') onNavigate?.('production-editor')
  }

  const saveProductionDraft = async () => {
    if (!epId || !productionDraft) return
    setEditorBusy(true)
    try {
      const state = await api.saveProductionDraft(epId, {
        draft_id: productionDraft.draft_id,
        canonical_version_id: productionDraft.canonical_version_id,
        script: productionDraft.script,
        media_cues: productionDraft.media_cues || [],
        morb_proposals: productionDraft.morb_proposals || [],
      })
      setEditorReport(state)
      setProductionDraft(state.draft || null)
      setEditorDirty(false)
      showToast('Production draft saved')
    } catch (error) { showToast('Draft save failed: ' + error.message) }
    finally { setEditorBusy(false) }
  }

  const approveProductionDraft = async () => {
    if (!epId || !productionDraft || editorDirty) return
    setEditorBusy(true)
    try {
      const state = await api.approveProductionDraft(epId, productionDraft.draft_id)
      setEditorReport(state)
      setProductionDraft(state.draft || null)
      setStage('produce')
      showToast(`Approved ${state.current_approved_version_id}`)
    } catch (error) { showToast('Approval failed: ' + error.message) }
    finally { setEditorBusy(false) }
  }

  const updateProductionLine = (lineId, field, value) => {
    setProductionDraft(current => current && ({
      ...current,
      script: current.script.map(line => line.production_line_id === lineId ? { ...line, [field]: value } : line),
    }))
    setEditorDirty(true)
  }

  const reviewMorb = (proposalId, decision) => {
    if (!productionDraft) return
    setProductionDraft(current => ({ ...current, morb_proposals: current.morb_proposals.map(item =>
      item.proposal_id === proposalId ? { ...item, reviewed: true, operator_decision: decision } : item
    ) }))
    setEditorDirty(true)
  }

  const removeProductionLine = (lineId) => {
    if (!productionDraft) return
    setProductionDraft({ ...productionDraft, script: productionDraft.script.filter(line => line.production_line_id !== lineId) })
    setEditorDirty(true)
  }

  const moveProductionLine = (lineId, direction) => {
    if (!productionDraft) return
    const list = [...productionDraft.script]
    const index = list.findIndex(line => line.production_line_id === lineId)
    const target = index + direction
    if (index < 0 || target < 0 || target >= list.length) return
    ;[list[index], list[target]] = [list[target], list[index]]
    setProductionDraft({ ...productionDraft, script: list })
    setEditorDirty(true)
  }

  const addProductionLineAfter = (index) => {
    if (!productionDraft) return
    const line = { production_line_id: `pl_${crypto.randomUUID()}`, source_canonical_line_id: null,
      speaker: 'phil', text: '', spoken_text: '', original_text: '', emotion: 'neutral',
      delivery_notes: '', pause_after: 0.35, production_cues: [], generated_by: 'production_editor' }
    const script = [...productionDraft.script]
    script.splice(index + 1, 0, line)
    setProductionDraft({ ...productionDraft, script })
    setEditorDirty(true)
  }

  return (
    <div className="tab-body">
      <div className="pane-left">
        <SectionHead label="Episodes">
          <button className="btn btn-gold btn-sm" onClick={() => setShowCreate(true)}><Plus size={10} /> NEW</button>
          <button className="icon-btn" onClick={loadEpisodes} title="Refresh"><RefreshCw size={10} /></button>
        </SectionHead>
        <div className="scrollable">
          {loading && <Empty msg="Loading…" />}
          {!loading && episodes.length === 0 && <Empty msg="No episodes found" />}
          {episodes.map(ep => {
            const id = ep.episode_id || ep.id
            const isActive = epId === id
            return (
              <div key={id} className={`ep-row${isActive ? ' active' : ''}`} onClick={() => selectEpisode(ep)}>
                <div className="ep-num">EP {String(id).slice(0, 12).toUpperCase()}</div>
                <div className="ep-title">{ep.title || ep.name || id}</div>
                <div className="ep-meta">
                  {ep.target_duration && <span className="font-mono" style={{ fontSize: '0.68rem', color: 'var(--steel)' }}>{Math.round(ep.target_duration / 60)}m</span>}
                  <Badge type={ep.status === 'completed' ? 'green' : ep.status === 'editing' ? 'blue' : 'steel'}>{ep.status || 'draft'}</Badge>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      <div className="pane-main">
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,minmax(0,1fr))', borderBottom: '1px solid var(--rim)', background: 'var(--surface)' }}>
          {[
            ['generate', '01 GENERATE', Boolean(activeEp), lines.length ? 'Canonical ready' : 'Generate a script'],
            ['preview', '02 PREVIEW', Boolean(activeEp && lines.length), 'Review and annotate'],
            ['editor', '03 PRODUCTION EDITOR', Boolean(activeEp && lines.length), editorReport?.approval_state === 'approved' ? 'Approved version' : 'Editor draft'],
            ['produce', '04 PRODUCE', Boolean(activeEp), editorReport?.approval_state === 'approved' ? 'Ready for approved plan' : 'Requires approval'],
          ].map(([key, label, enabled, stateLabel]) => <button key={key} onClick={() => navigateStage(key)} disabled={!enabled}
            aria-current={stage === key ? 'step' : undefined}
            style={{ padding: '10px 8px', border: 0, borderBottom: stage === key ? '2px solid var(--gold)' : '2px solid transparent',
              background: 'transparent', color: stage === key ? 'var(--gold)' : 'var(--steel)', cursor: enabled ? 'pointer' : 'not-allowed',
              fontFamily: 'var(--font-mono)', fontSize: '0.77rem', letterSpacing: '.06em', fontWeight: 700 }}>
            <span>{label}<small style={{ display: 'block', marginTop: 3, fontSize: '0.68rem', letterSpacing: '.02em', fontWeight: 400, color: 'var(--steel)' }}>{stateLabel}</small></span>
          </button>)}
        </div>
        <div className="section-head" style={{ height: 'auto', padding: '.65rem 14px', flexWrap: 'wrap', gap: 6 }}>
          <div style={{ flex: 1, minWidth: 160 }}>
            <div className="font-display" style={{ fontSize: '1.62rem', letterSpacing: '.08em', color: 'var(--bone)', lineHeight: 1 }}>{activeEp?.title || 'Select an episode'}</div>
            {activeEp && <div className="gap-row" style={{ marginTop: 4 }}>
              <Badge type={targetOk ? 'green' : 'gold'}>{secondsToDisplay(runtimeSec)} / {targetMinutes}m target</Badge>
              <span className="font-mono" style={{ fontSize: '0.68rem', color: 'var(--steel)' }}>{lines.length} lines</span>
            </div>}
          </div>
          <div className="gap-row" style={{ flexWrap: 'wrap' }}>
            {stage === 'generate' && <>
              {generating ? <button className="btn btn-stop" onClick={handleStop}><Square size={11} /> STOP GENERATION</button> : <button className="btn btn-gold" onClick={handleGenerate} disabled={!activeEp}><Zap size={11} /> GENERATE CANONICAL</button>}
              <button className="btn btn-steel" onClick={() => setShowEditConfig(true)} disabled={!activeEp}><Settings size={11} /> CONFIG</button>
              <button className="btn btn-steel" onClick={openScriptOverride} disabled={!activeEp}><FileText size={11} /> SCRIPT OVERRIDE</button>
              <button className="btn btn-steel" onClick={loadVersions} disabled={!activeEp}><History size={11} /> VERSIONS</button>
            </>}
            {stage === 'editor' && <>
              <select className="ds-select" value={selectedCanonicalId} onChange={event => setSelectedCanonicalId(event.target.value)} aria-label="Canonical script version">
                {canonicalVersions.map(version => <option key={version.version_id} value={version.version_id}>{version.version_id} · {version.word_count} words</option>)}
              </select>
              <button className="btn btn-gold" onClick={openProductionEditor} disabled={!selectedCanonicalId || editorBusy}>
                {editorBusy ? <Spinner size={10} /> : <FileText size={10} />} OPEN AS NEW DRAFT
              </button>
              <button className="btn btn-steel" onClick={saveProductionDraft} disabled={!productionDraft || !editorDirty || editorBusy}>SAVE DRAFT</button>
              <button className="btn btn-solid" onClick={approveProductionDraft}
                disabled={!productionDraft || editorDirty || editorBusy || editorReport?.approval_state === 'approved' || (productionDraft.morb_proposals || []).some(item => !item.reviewed)}>APPROVE VERSION</button>
            </>}
            {stage === 'produce' && <>
              <Badge type={editorReport?.approval_state === 'approved' ? 'green' : 'gold'}>
                {editorReport?.approval_state === 'approved' ? `APPROVED ${editorReport.current_approved_version_id}` : (editorReport?.approval_state || 'approval required').toUpperCase()}
              </Badge>
              {producing ? <button className="btn btn-stop" onClick={handleStop}><Square size={11} /> STOP PRODUCTION</button>
                : <button className="btn btn-solid" onClick={handleProduce}
                  disabled={!activeEp || editorReport?.approval_state !== 'approved'}><Play size={11} /> PRODUCE APPROVED VERSION</button>}
            </>}
            <button className="btn btn-steel" onClick={() => setShowExport(true)} disabled={!activeEp}><Download size={11} /> EXPORT</button>
            <button className="btn btn-steel" onClick={() => setShowFeedback(true)} disabled={!activeEp}><MessageSquare size={11} /> FEEDBACK</button>
            <button className="btn btn-steel" onClick={() => setShowAssets(true)} disabled={!activeEp}><FileText size={11} /> ASSETS</button>
            <button className={`btn btn-sm ${wsConnected ? 'btn-green' : 'btn-steel'}`} onClick={connectWs} disabled={!activeEp} title="Connect WebSocket"><Wifi size={10} /> {wsConnected ? 'WS ON' : 'WS'}</button>
          </div>
        </div>

        {(generating || producing) && (() => {
          const episodeStatus = generationProgress?.episode_status || {}
          const section = generationProgress?.section || episodeStatus.section
          const sectionCount = generationProgress?.section_count || episodeStatus.section_count
          const stage = generationProgress?.stage || episodeStatus.stage
          const accepted = generationProgress?.accepted_words ?? episodeStatus.accepted_words
          const label = producing
            ? (episodeStatus.status === 'producing' ? 'PRODUCTION IN PROGRESS' : 'STARTING PRODUCTION')
            : (stage ? `GENERATING · ${stage.toUpperCase()}` : 'STARTING GENERATION')
          return <div role="status" aria-live="polite" style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '8px 14px', background: 'rgba(214,164,74,.12)', borderBottom: '1px solid var(--gold)', color: 'var(--gold)', fontFamily: 'var(--font-mono)', fontSize: '0.81rem', letterSpacing: '.06em' }}>
            <Spinner size={13} />
            <strong>{label}</strong>
            {section && sectionCount ? <span>SECTION {section}/{sectionCount}</span> : null}
            {accepted != null ? <span>{accepted} WORDS ACCEPTED</span> : null}
            {!generating && producing ? <span>Audio, assembly, and final export are running in the background.</span> : null}
          </div>
        })()}

        {(() => {
          const st = writerStatus
          const isLlm = st?.active_writer === 'llamacpp' || st?.active_writer === 'llm_bridge'
          const isLoading = st === null
          const backend = st?.writer_backend
            const modelName = String(st?.model || 'Local model').split(/[\\/]/).pop().replace(/\.gguf$/i, '')
          const bg = isLoading ? 'var(--rim)' : isLlm ? 'rgba(34,197,94,.12)' : 'rgba(234,179,8,.10)'
          const dot = isLoading ? '#6b7280' : isLlm ? '#22c55e' : '#eab308'
          const label = isLoading ? 'Script Engine: Checking…'
            : isLlm && backend === 'llamacpp' ? `Script Engine: llama.cpp / ${modelName} Active`
            : isLlm ? 'Script Engine: LLM Active'
            : 'Script Engine: Unavailable'
          return <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '5px 14px', background: bg, borderBottom: '1px solid var(--rim)', flexShrink: 0 }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: dot, flexShrink: 0, boxShadow: isLlm ? `0 0 6px ${dot}` : 'none' }} />
            <Cpu size={10} style={{ color: dot, flexShrink: 0 }} />
            <span style={{ fontSize: '0.68rem', fontFamily: 'var(--font-mono)', letterSpacing: '.06em', color: dot, fontWeight: 600 }}>{label}</span>
            {!isLoading && !isLlm && <AlertTriangle size={10} style={{ color: dot, marginLeft: 4 }} />}
            <button onClick={loadWriterStatus} style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer', color: 'var(--steel)', padding: 2 }} title="Refresh writer status"><RefreshCw size={9} /></button>
          </div>
        })()}

        {activeEp && <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7,1fr)', gap: 6, padding: '8px 14px', borderBottom: '1px solid var(--rim)', flexShrink: 0 }}>
          <StatBox val={lines.length} label="Lines" />
          <StatBox val={philLines} label="Phil" />
          <StatBox val={jimLines} label="Jim" />
          <StatBox val={hostLines} label="Host" />
          <StatBox val={adLines} label="Ads" />
          <StatBox val={assets.length} label="Assets" />
          <StatBox val={secondsToDisplay(runtimeSec)} label="Runtime" tone={targetOk ? 'ok' : 'warn'} />
        </div>}

        <div className="scrollable" style={{ padding: '8px 14px' }}>
          {!activeEp && <Empty msg="← Select an episode to begin" />}
          {activeEp && stage === 'generate' && !script && <Empty msg="Loading canonical script…" />}
          {activeEp && stage === 'generate' && script && lines.length === 0 && <div style={{ textAlign: 'center', paddingTop: '3rem' }}>
            <Empty msg="No canonical script yet — generate one to begin" />
            <button className="btn btn-gold" style={{ marginTop: '1rem' }} onClick={handleGenerate} disabled={generating}><Zap size={11} /> {generating ? 'Generating…' : 'Generate Script'}</button>
          </div>}
          {stage === 'editor' && !productionDraft && <div style={{ textAlign: 'center', padding: '2rem 1rem', color: 'var(--steel)' }}>
            <div className="section-label">PRODUCTION EDITOR</div>
            <p>Select a canonical snapshot above, then open it as a separate production draft.</p>
          </div>}
          {stage === 'editor' && productionDraft && <div className="font-mono" style={{ padding: '8px 10px', marginBottom: 8, border: '1px solid var(--rim)', color: 'var(--steel)', fontSize: '0.75rem' }}>
            SOURCE {productionDraft.canonical_version_id} · SHA {productionDraft.canonical_source_hash?.slice(0, 12)} · COPY SHA {productionDraft.production_copy_hash?.slice(0, 12)} · {editorDirty ? 'UNSAVED EDITS' : (editorReport?.approval_state || 'draft').toUpperCase()}
          </div>}

          {displayLines.map((line, idx) => {
            const isEditor = stage === 'editor'
            const isSelected = selectedLine === idx
            const text = line.text || line.line || ''
            const speaker = (line.speaker || 'PHIL').toUpperCase()
            const lineId = line.production_line_id
            const lineFindings = editorReport?.qc_report?.take_findings?.filter(finding => finding.segment_id === (lineId || `line_${String(idx + 1).padStart(3, '0')}`)) || []
            const morbFindings = (productionDraft?.morb_proposals || []).filter(proposal => proposal.production_line_id === lineId)
            return <div key={lineId || line.canonical_line_id || idx} className={`script-line${isSelected ? ' selected' : ''}`} onClick={() => setSelectedLine(isSelected ? null : idx)}>
              <div className="script-line-head">
                <span className="line-num">#{idx + 1}</span>
                <span className={`line-speaker ${SPK_CLASS[speaker] || 'spk-host'}`}>{speaker}</span>
                {line.repetition_warning && <span title="Possible repetition — review before production" style={{ color: 'var(--amber)', display: 'inline-flex', marginLeft: 4 }}><AlertTriangle size={11} /></span>}
                {(lineFindings.length > 0 || morbFindings.some(item => item.decision === 'flagged')) && <span title={[...lineFindings.map(item => item.finding), ...morbFindings.filter(item => item.decision === 'flagged').map(item => item.reason)].join('; ')} style={{ color: 'var(--amber)', display: 'inline-flex', marginLeft: 4 }}><AlertTriangle size={11} /></span>}
                <span className={`line-text${isSelected ? ' expanded' : ''}`}>{isEditor && line.spoken_text && line.spoken_text !== text ? line.spoken_text : text}</span>
                {isSelected && <div className="gap-row" style={{ flexShrink: 0 }} onClick={event => event.stopPropagation()}>
                  {isEditor ? <>
                    <button className="icon-btn" title="Move up" onClick={() => moveProductionLine(lineId, -1)}><ArrowUp size={9} /></button>
                    <button className="icon-btn" title="Move down" onClick={() => moveProductionLine(lineId, 1)}><ArrowDown size={9} /></button>
                    <button className="icon-btn" title="Add production line after" onClick={() => addProductionLineAfter(idx)}><Plus size={9} /></button>
                    <button className="icon-btn del" title="Delete production line" onClick={() => removeProductionLine(lineId)}><Trash2 size={9} /></button>
                    <button className="icon-btn" title="Add production cue after this line" onClick={() => { setCueForm(c => ({ ...c, line_index: idx, anchor_line_id: lineId })); setShowCue(true) }}><Mic size={9} /></button>
                  </> : productionManifest?.script_current && productionManifest.segments?.some(s => s.production_line_id === lineId) &&
                    <button className="icon-btn" title="Regenerate this approved line's Qwen take" disabled={revisionStatus?.status === 'running' || producing} onClick={() => regenerateLine(lineId)}><RefreshCw size={9} /></button>}
                </div>}
              </div>
              {isEditor && isSelected && <div onClick={event => event.stopPropagation()} style={{ display: 'grid', gridTemplateColumns: 'repeat(2,minmax(0,1fr))', gap: 7, padding: '8px 12px 12px 44px' }}>
                <Field label="Speaker"><select className="ds-select" value={line.speaker?.toUpperCase() || 'PHIL'} onChange={event => updateProductionLine(lineId, 'speaker', event.target.value.toLowerCase())}>{SPEAKERS.map(value => <option key={value} value={value.toLowerCase()}>{value}</option>)}</select></Field>
                <Field label="Pause After (seconds)"><input className="ds-input" type="number" min="0" max="3" step="0.05" value={line.pause_after ?? 0.4} onChange={event => updateProductionLine(lineId, 'pause_after', Number(event.target.value))} /></Field>
                <div style={{ gridColumn: '1 / -1' }}><Field label="Production Dialogue"><textarea className="ds-textarea" value={line.text} onChange={event => updateProductionLine(lineId, 'text', event.target.value)} /></Field></div>
                <div style={{ gridColumn: '1 / -1' }}><Field label="Spoken / Pronunciation Form"><textarea className="ds-textarea" value={line.spoken_text || line.text} onChange={event => updateProductionLine(lineId, 'spoken_text', event.target.value)} /></Field></div>
                <Field label="Emotion"><select className="ds-select" value={line.emotion || 'neutral'} onChange={event => updateProductionLine(lineId, 'emotion', event.target.value)}>{['neutral','warm','measured','confident','skeptical','pragmatic','excited','reflective'].map(value => <option key={value}>{value}</option>)}</select></Field>
                <Field label="Delivery Notes"><input className="ds-input" value={line.delivery_notes || ''} onChange={event => updateProductionLine(lineId, 'delivery_notes', event.target.value)} placeholder="Short performance direction" /></Field>
                {morbFindings.length > 0 && <div style={{ gridColumn: '1 / -1', fontSize: '0.75rem', color: 'var(--steel)' }}>{morbFindings.map((item, itemIndex) => <div key={itemIndex}>{item.morb} · {item.action} · {item.decision}: {item.reason}</div>)}</div>}
              </div>}
            </div>
          })}

          {stage === 'editor' && productionDraft && <div style={{ marginTop: 12, padding: 10, border: '1px solid var(--rim)', background: 'var(--surface)' }}>
            <div className="section-label">PRODUCTION CUES · {productionDraft.media_cues?.length || 0}</div>
            {(productionDraft.media_cues || []).map((cue, index) => <div key={cue.cue_id || index} className="gap-row" style={{ justifyContent: 'space-between', padding: '5px 0', fontSize: '0.75rem', borderBottom: '1px solid var(--rim)' }}>
              <span>{cue.cue_type} · {cue.asset_id} · after line {Number(cue.line_number ?? 0) + 1}</span>
              <button className="icon-btn del" title="Remove cue from production draft" onClick={() => {
                setProductionDraft(current => ({ ...current, media_cues: current.media_cues.filter((_, cueIndex) => cueIndex !== index) }))
                setEditorDirty(true)
              }}><Trash2 size={9} /></button>
            </div>)}
            <details style={{ marginTop: 8, color: 'var(--steel)', fontSize: '0.75rem' }}>
              <summary>EDITOR REVIEW · {productionDraft.morb_proposals?.length || 0} proposals · {productionDraft.change_ledger?.length || 0} operator changes</summary>
              {(productionDraft.morb_proposals || []).map((item, index) => <div key={`morb-${index}`} className="gap-row" style={{ padding: '5px 0', borderBottom: '1px solid var(--rim)', flexWrap: 'wrap' }}>
                <span style={{ flex: 1, minWidth: 220 }}>{item.production_line_id} · {item.morb} · {item.action} · {item.decision}: {item.reason} · {item.reviewed ? `OPERATOR ${item.operator_decision?.toUpperCase()}` : 'REVIEW REQUIRED'}</span>
                {!item.reviewed && <><button className="btn btn-steel btn-sm" onClick={() => reviewMorb(item.proposal_id, 'accept')}>ACCEPT</button><button className="btn btn-steel btn-sm" onClick={() => reviewMorb(item.proposal_id, 'reject')}>REJECT</button></>}
              </div>)}
              {(productionDraft.change_ledger || []).map((item, index) => <div key={`change-${index}`} style={{ padding: '4px 0' }}>
                {item.action} · {item.production_line_id || 'episode'} · {item.field || ''}
              </div>)}
            </details>
          </div>}

          {wsLog.length > 0 && <div style={{ marginTop: 12 }}><div className="section-label" style={{ marginBottom: 6 }}>WebSocket Log</div><div className="code-block">{wsLog.join('\n')}</div></div>}
        </div>
      </div>

      <div className="pane-right">
        <SectionHead label="Audio" />
        <div style={{ padding: '10px 12px', borderBottom: '1px solid var(--rim)' }}>
          {activeEp ? <><audio controls style={{ width: '100%', marginBottom: 8 }} src={`${api.audioUrl(epId)}?v=${audioRevision}`} /><button className="btn btn-gold" style={{ width: '100%' }} onClick={() => window.open(`${api.audioUrl(epId)}?download=1&v=${audioRevision}`)}><Download size={10} /> DOWNLOAD MP3</button>{revisionStatus?.status === 'running' && <div role="status" style={{ fontSize: '0.85rem', marginTop: 8 }}>Regenerating {revisionStatus.segment_id} and rebuilding the master…</div>}</> : <Empty msg="Select episode" />}
          {stage === 'produce' && editorReport?.qc_report && <details style={{ marginTop: 10, fontSize: '0.85rem', color: 'var(--steel)' }}>
            <summary style={{ cursor: 'pointer' }}>PRODUCTION QC · {editorReport.qc_report.status} · {editorReport.qc_report.take_findings?.length || 0} line findings</summary>
            {(editorReport.qc_report?.take_findings || []).map((finding, index) => <div key={`qc-${index}`} style={{ padding: '5px 0', borderBottom: '1px solid var(--rim)' }}>
              {finding.segment_id} · {finding.finding}
            </div>)}
          </details>}
        </div>
        {stage === 'editor' && <div style={{ padding: '10px 12px', color: 'var(--steel)', fontSize: '0.75rem' }}>
          Canonical source: {productionDraft?.canonical_version_id || selectedCanonicalId || 'select a snapshot'}
          {productionDraft && <div style={{ marginTop: 6 }}>Edits here stay in the production copy. Save the draft, then approve it before Produce is enabled.</div>}
        </div>}
      </div>

      {showEditConfig && activeEp && <EditConfigModal episode={activeEp} onClose={() => setShowEditConfig(false)} onSaved={async (updated) => { setActiveEp(ep => ({ ...ep, ...updated, config: updated })); setShowEditConfig(false); try { setEditorReport(await api.productionEditor(epId)) } catch { setEditorReport(null) }; showToast('Config saved ✓') }} showToast={showToast} />}
      {showCreate && <CreateEpisodeModal onClose={() => setShowCreate(false)} onCreated={() => { setShowCreate(false); loadEpisodes(); showToast('Segment created ✓') }} showToast={showToast} />}

      {showScriptOverride && <Modal title="Full Script Override" onClose={() => setShowScriptOverride(false)} wide footer={<>
        <button className="btn btn-steel" onClick={() => setShowScriptOverride(false)}>CANCEL</button>
        <button className="btn btn-solid" onClick={saveScriptOverride} disabled={overrideBusy || !overrideText.trim()}>{overrideBusy ? <Spinner size={10} /> : <Check size={10} />} REPLACE SCRIPT</button>
      </>}>
        <div className="font-mono" style={{ fontSize: '0.72rem', color: 'var(--steel)', marginBottom: 10, lineHeight: 1.6 }}>
          Emergency/manual lane. Paste a finished script using PHIL: and JIM: lines. This does not call the LLM. The saved script becomes production-ready and remains rollbackable through Versions.
        </div>
        <textarea className="ds-textarea" style={{ minHeight: 360, fontFamily: 'var(--font-mono)', fontSize: '0.94rem' }} value={overrideText} onChange={e => setOverrideText(e.target.value)} placeholder={'PHIL: Opening line…\nJIM: Response…\nPHIL: Next point…'} />
        <div className="font-mono" style={{ fontSize: '0.68rem', color: 'var(--steel)', marginTop: 8 }}>
          {overrideText.split('\n').filter(line => /^(?:#\s*\d+\s*)?(?:\*\*)?(PHIL|JIM|BRYAN|HOST|GUEST|INTRO_MALE|INTRO_FEMALE)/i.test(line.trim())).length} recognized speaker lines
        </div>
      </Modal>}

      {showVersions && <Modal title="Script Versions" onClose={() => setShowVersions(false)}>
        {versions.length === 0 && <Empty msg="No versions found" />}
        {versions.map((v, i) => <div key={i} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid var(--rim)' }}>
          <div><div className="font-mono" style={{ fontSize: '0.81rem', color: 'var(--bone)' }}>v{v.version || v.version_id || i + 1}</div><div className="font-mono" style={{ fontSize: '0.68rem', color: 'var(--steel)' }}>{v.saved_at || v.created_at || v.timestamp || '—'} · {v.word_count || '?'} words</div></div>
          <button className="btn btn-gold btn-sm" onClick={() => doRollback(v.version || v.version_id || i + 1)}>ROLLBACK</button>
        </div>)}
      </Modal>}

      {showFeedback && <Modal title="Episode Feedback" onClose={() => setShowFeedback(false)} footer={<><button className="btn btn-steel" onClick={() => setShowFeedback(false)}>CANCEL</button><button className="btn btn-solid" onClick={submitFeedback}>SUBMIT</button></>}>
        <Field label="Feedback"><textarea className="ds-textarea" style={{ minHeight: 120 }} value={feedbackText} onChange={e => setFeedbackText(e.target.value)} placeholder="Enter feedback for this episode…" /></Field>
      </Modal>}

      {showAssets && <Modal title="Episode + Reusable Asset Library" onClose={() => setShowAssets(false)} wide>
        <div className="font-mono" style={{ fontSize: '0.68rem', color: 'var(--steel)', marginBottom: 10 }}>
          Global assets are indexed from asset_library/ plus audio/sfx, audio/jingles, audio/ads, social/assets and social/templates. Episode uploads remain episode-specific.
        </div>
        <Field label="Search Asset Library"><input className="ds-input" value={assetSearch} onChange={e => setAssetSearch(e.target.value)} placeholder="Search sfx, ad, bumper, music, filename…" /></Field>
        <div style={{ margin: '14px 0' }}>
          <div className="section-label" style={{ marginBottom: 8 }}>Upload Episode-Specific Asset</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 8 }}>
            <Field label="Label"><input className="ds-input" value={assetLabel} onChange={e => { setAssetLabel(e.target.value); saveAssetForm(e.target.value, assetDesc, assetRole) }} placeholder="Asset label" /></Field>
            <Field label="Role"><select className="ds-select" value={assetRole} onChange={e => { setAssetRole(e.target.value); saveAssetForm(assetLabel, assetDesc, e.target.value) }}>{['sfx', 'music', 'voice', 'image', 'document', 'ad', 'jingle'].map(r => <option key={r}>{r}</option>)}</select></Field>
          </div>
          <Field label="Description"><input className="ds-input" value={assetDesc} onChange={e => { setAssetDesc(e.target.value); saveAssetForm(assetLabel, e.target.value, assetRole) }} placeholder="Optional description" /></Field>
          <input type="file" ref={fileRef} style={{ display: 'none' }} onChange={e => uploadAsset(e.target.files[0])} />
          <button className="btn btn-gold" style={{ marginTop: 10 }} onClick={() => fileRef.current?.click()}><Upload size={11} /> CHOOSE FILE & UPLOAD</button>
        </div>
        <Divider />
        <div className="section-label" style={{ marginBottom: 8 }}>Callable Assets ({visibleAssets.length}/{assets.length})</div>
        {visibleAssets.length === 0 && <Empty msg="No matching assets" />}
        {visibleAssets.map((a, i) => <div key={a.asset_id || i} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 10px', border: '1px solid var(--rim)', marginBottom: 6, borderRadius: 'var(--radius)', background: 'var(--surface)' }}>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: '1.04rem', fontWeight: 600 }}>{a.label || a.filename || a.name}</div>
            <div className="font-mono" style={{ fontSize: '0.68rem', color: 'var(--steel)' }}>{(a.scope || 'episode').toUpperCase()} · {a.role || a.asset_type || 'asset'} · {a.relative_path || a.description || '—'}</div>
          </div>
          <a href={api.assetUrl(epId, a.asset_id || a.id)} target="_blank" rel="noreferrer"><button className="btn btn-steel btn-sm"><Download size={9} /> OPEN</button></a>
        </div>)}
      </Modal>}

      {showExport && <Modal title="Export Script" onClose={() => setShowExport(false)}><div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>{['json', 'txt', 'srt'].map(fmt => <button key={fmt} className="btn btn-steel" style={{ width: '100%', justifyContent: 'flex-start', height: 40 }} onClick={() => handleExport(fmt)}><Download size={12} /> Export as .{fmt.toUpperCase()}</button>)}</div></Modal>}

      {showCue && <Modal title={`Insert Media Cue After Line ${cueForm.line_index + 1}`} onClose={() => setShowCue(false)} footer={<><button className="btn btn-steel" onClick={() => setShowCue(false)}>CANCEL</button><button className="btn btn-solid" onClick={addCue} disabled={!cueForm.asset_id}>ADD CUE</button></>}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
          <Field label="Cue Type"><select className="ds-select" value={cueForm.cue_type} onChange={e => setCueForm(c => ({ ...c, cue_type: e.target.value }))}>{CUE_TYPES.map(t => <option key={t}>{t}</option>)}</select></Field>
          <Field label="Asset"><select className="ds-select" value={cueForm.asset_id} onChange={e => setCueForm(c => ({ ...c, asset_id: e.target.value }))}><option value="">— choose asset —</option>{assets.map(a => <option key={a.asset_id || a.id} value={a.asset_id || a.id}>[{String(a.role || a.asset_type || 'asset').toUpperCase()}] {a.label || a.filename || a.original_name}</option>)}</select></Field>
          <div style={{ gridColumn: '1 / -1' }}><Field label="Note"><input className="ds-input" value={cueForm.note} onChange={e => setCueForm(c => ({ ...c, note: e.target.value }))} placeholder="Optional. Put 'overlay' here to force overlay instead of insert." /></Field></div>
        </div>
      </Modal>}

      <Toast {...toast} />
    </div>
  )
}

function EditConfigModal({ episode, onClose, onSaved, showToast }) {
  const config = episode.config || episode
  const [form, setForm] = useState({
    title: config.title || episode.title || '',
    topic: config.topic || episode.topic || '',
    description: config.description || '',
    key_points: (Array.isArray(config.key_points) ? config.key_points : []).join('\n'),
    custom_instructions: config.custom_instructions || '',
    target_minutes: Math.max(5, Math.min(45, Math.round((Number(config.target_duration) || 300) / 60))),
    intensity: config.intensity || 'medium',
  })
  const [busy, setBusy] = useState(false)
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))
  const epId = episode.episode_id || episode.id
  const submit = async () => {
    if (!form.title.trim()) { showToast('Title required'); return }
    setBusy(true)
    try {
      const body = { ...form, target_duration: form.target_minutes * 60, target_word_count: form.target_minutes * 90, key_points: form.key_points.split('\n').map(s => s.trim()).filter(Boolean) }
      const res = await api.updateEpisodeConfig(epId, body)
      onSaved(res.config || body)
    } catch (e) { showToast('Save failed: ' + e.message.slice(0, 80)) }
    finally { setBusy(false) }
  }
  return <Modal title={`Edit Config — ${epId}`} onClose={onClose} footer={<><button className="btn btn-steel" onClick={onClose}>CANCEL</button><button className="btn btn-solid" onClick={submit} disabled={busy}>{busy ? <Spinner size={11} /> : <Check size={11} />} SAVE CONFIG</button></>}>
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}><Field label="Title"><input className="ds-input" value={form.title} onChange={e => set('title', e.target.value)} /></Field><Field label="Intensity"><select className="ds-select" value={form.intensity} onChange={e => set('intensity', e.target.value)}>{['low', 'medium', 'high'].map(v => <option key={v}>{v}</option>)}</select></Field></div>
      <Field label="Main Topic"><input className="ds-input" value={form.topic} onChange={e => set('topic', e.target.value)} /></Field>
      <Field label="Description"><textarea className="ds-textarea" value={form.description} onChange={e => set('description', e.target.value)} /></Field>
      <Field label="Key Points (one per line)"><textarea className="ds-textarea" value={form.key_points} onChange={e => set('key_points', e.target.value)} placeholder={'Point 1\nPoint 2\nPoint 3'} /></Field>
      <Field label="Custom Instructions"><textarea className="ds-textarea" style={{ minHeight: 56 }} value={form.custom_instructions} onChange={e => set('custom_instructions', e.target.value)} placeholder="Special tone or format instructions…" /></Field>
      <DurationControl value={form.target_minutes} onChange={value => set('target_minutes', value)} />
    </div>
  </Modal>
}

function DurationControl({ value, onChange }) {
  const ticks = Array.from({ length: 41 }, (_, index) => index + 5)
  const fullSections = Math.floor(value / 5)
  const remainder = value % 5
  const sectionPlan = `${fullSections} × 5 MIN${remainder ? ` + ${remainder} MIN` : ''}`
  return <Field label={`SEGMENT LENGTH — ${value} MINUTES`}>
    <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <strong style={{ fontSize: '1.37rem', color: 'var(--bone)' }}>{value} MIN</strong>
        <span className="font-mono" style={{ fontSize: '0.72rem', color: 'var(--steel)' }}>5m</span>
        <span className="font-mono" style={{ fontSize: '0.72rem', color: 'var(--steel)' }}>45m</span>
      </div>
      <input type="range" min={5} max={45} step={1} value={value} list="segment-duration-ticks" onChange={e => onChange(Number(e.target.value))} />
      <datalist id="segment-duration-ticks">{ticks.map(minute => <option key={minute} value={minute} label={minute % 5 === 0 || minute === 5 || minute === 45 ? `${minute}` : ''} />)}</datalist>
      <div style={{ display: 'grid', gridTemplateColumns: `repeat(${ticks.length}, 1fr)`, alignItems: 'start', color: 'var(--steel)' }}>
        {ticks.map(minute => <span key={minute} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}><i style={{ display: 'block', width: 1, height: minute % 5 === 0 || minute === 5 || minute === 45 ? 9 : 5, background: 'currentColor' }} />{minute % 5 === 0 || minute === 5 || minute === 45 ? <small style={{ fontSize: '0.68rem' }}>{minute}</small> : null}</span>)}
      </div>
      <div className="font-mono" style={{ fontSize: '0.73rem', color: 'var(--gold)', letterSpacing: '.04em' }}>INTERNAL GENERATION PLAN: {sectionPlan}</div>
    </div>
  </Field>
}

function CreateEpisodeModal({ onClose, onCreated, showToast }) {
  const [form, setForm] = useState({ episode_id: '', title: '', topic: '', description: '', key_points: '', custom_instructions: '', target_minutes: 5 })
  const [busy, setBusy] = useState(false)
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))
  const targetWords = Math.round(form.target_minutes * 90)
  const submit = async () => {
    if (!form.title.trim()) { showToast('Title required'); return }
    setBusy(true)
    try {
      const body = { ...form, target_duration: form.target_minutes * 60, key_points: form.key_points.split('\n').map(s => s.trim()).filter(Boolean), target_word_count: targetWords }
      const res = await api.createEpisode(body)
      onCreated(res)
    } catch (e) { showToast('Create failed: ' + e.message.slice(0, 80)) }
    finally { setBusy(false) }
  }
  return <Modal title="Create Segment" onClose={onClose} footer={<><button className="btn btn-steel" onClick={onClose}>CANCEL</button><button className="btn btn-solid" onClick={submit} disabled={busy}>{busy ? <Spinner size={11} /> : <Plus size={11} />} CREATE</button></>}>
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}><Field label="Episode ID"><input className="ds-input" value={form.episode_id} onChange={e => set('episode_id', e.target.value)} placeholder="e.g. ep_042" /></Field><Field label="Title"><input className="ds-input" value={form.title} onChange={e => set('title', e.target.value)} placeholder="Episode title" /></Field></div>
      <Field label="Main Topic"><input className="ds-input" value={form.topic} onChange={e => set('topic', e.target.value)} placeholder="What is this episode about?" /></Field>
      <Field label="Description"><textarea className="ds-textarea" value={form.description} onChange={e => set('description', e.target.value)} placeholder="Longer description / context…" /></Field>
      <Field label="Key Points (one per line)"><textarea className="ds-textarea" value={form.key_points} onChange={e => set('key_points', e.target.value)} placeholder={'Point 1\nPoint 2\nPoint 3'} /></Field>
      <Field label="Custom Instructions"><textarea className="ds-textarea" style={{ minHeight: 56 }} value={form.custom_instructions} onChange={e => set('custom_instructions', e.target.value)} placeholder="Any special tone/format instructions…" /></Field>
      <DurationControl value={form.target_minutes} onChange={value => set('target_minutes', value)} />
    </div>
  </Modal>
}

function QuickAddLine({ epId, onDone, showToast, disabled }) {
  const [speaker, setSpeaker] = useState('PHIL')
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
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
  return <div style={{ padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: 8 }}>
    <Field label="Speaker"><select className="ds-select" value={speaker} onChange={e => setSpeaker(e.target.value)} disabled={disabled}>{SPEAKERS.map(s => <option key={s}>{s}</option>)}</select></Field>
    <Field label="Line"><textarea className="ds-textarea" style={{ minHeight: 64 }} value={text} onChange={e => setText(e.target.value)} placeholder="Dialogue text…" disabled={disabled} /></Field>
    <button className="btn btn-gold" onClick={submit} disabled={disabled || busy || !text.trim()}>{busy ? <Spinner size={11} /> : <Plus size={11} />} ADD LINE</button>
  </div>
}
