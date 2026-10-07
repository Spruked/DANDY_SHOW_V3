import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, ArrowDown, ArrowUp, FileText, Plus, RefreshCw, Save, ShieldCheck, Trash2 } from 'lucide-react'
import { api } from '../lib/api'

const panel = { background: 'var(--panel)', border: '1px solid var(--rim)', borderRadius: 8, padding: 12, minWidth: 0 }
const label = { color: 'var(--steel)', font: '600 0.75rem var(--font-mono)', letterSpacing: '.08em', textTransform: 'uppercase' }
const input = { width: '100%', background: 'var(--bg)', color: 'var(--bone)', border: '1px solid var(--rim)', borderRadius: 4, padding: '6px 7px', font: '0.94rem var(--font-body)' }

export default function ProductionEditorTab({ episodeId, onEpisodeChange }) {
  const [episodes, setEpisodes] = useState([])
  const [selectedId, setSelectedId] = useState(episodeId || '')
  const [versions, setVersions] = useState([])
  const [versionId, setVersionId] = useState('')
  const [canonical, setCanonical] = useState(null)
  const [previewReview, setPreviewReview] = useState(null)
  const [draft, setDraft] = useState(null)
  const [state, setState] = useState(null)
  const [cueAssets, setCueAssets] = useState([])
  const [dirty, setDirty] = useState(false)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')

  const refresh = async (id = selectedId) => {
    if (!id) return
    const [canonicalList, editor, selectedPreview] = await Promise.all([api.canonicalScripts(id), api.productionEditor(id), api.selectedPreview(id)])
    setVersions(canonicalList.versions || [])
    const targetVersion = editor.draft?.canonical_version_id || selectedPreview?.canonical_version_id || canonicalList.active_version_id
    setVersionId(targetVersion || '')
    setState(editor)
    setDraft(editor.draft || null)
    setDirty(false)
    if (targetVersion) {
      const [source, review] = await Promise.all([api.canonicalScript(id, targetVersion), api.previewReview(id, targetVersion)])
      setCanonical(source)
      setPreviewReview(editor.draft?.preview_review || review)
    } else { setCanonical(null); setPreviewReview(null) }
  }

  useEffect(() => {
    let alive = true
    api.listEpisodes().then(data => {
      if (!alive) return
      const items = Array.isArray(data) ? data : (data.episodes || [])
      setEpisodes(items)
      const id = episodeId || items[0]?.episode_id || items[0]?.id || ''
      setSelectedId(id)
      if (id) {
        onEpisodeChange?.(id)
        refresh(id).then(async () => {
          const [episodeAssets, library] = await Promise.all([api.listAssets(id), api.listAssetLibrary('', '')])
          const combined = [...(Array.isArray(episodeAssets) ? episodeAssets : (episodeAssets.assets || [])), ...(library.assets || [])]
          if (alive) setCueAssets(combined.filter(asset => (asset.asset_type || '').toLowerCase() === 'audio' && (asset.asset_id || asset.id)))
        }).catch(error => setMessage(error.message))
      }
    }).catch(error => setMessage(error.message))
    return () => { alive = false }
  }, [])

  useEffect(() => {
    if (!episodeId || episodeId === selectedId) return
    setSelectedId(episodeId)
    refresh(episodeId).catch(error => setMessage(error.message))
  }, [episodeId])

  const chooseEpisode = async (id) => {
    setSelectedId(id); onEpisodeChange?.(id); setCanonical(null); setDraft(null); setState(null); setMessage('')
    try {
      await refresh(id)
      const [episodeAssets, library] = await Promise.all([api.listAssets(id), api.listAssetLibrary('', '')])
      const combined = [...(Array.isArray(episodeAssets) ? episodeAssets : (episodeAssets.assets || [])), ...(library.assets || [])]
      setCueAssets(combined.filter(asset => (asset.asset_type || '').toLowerCase() === 'audio' && (asset.asset_id || asset.id)))
    } catch (error) { setMessage(error.message) }
  }
  const chooseCanonical = async (id) => {
    setVersionId(id)
    try {
      const [source, review] = await Promise.all([api.canonicalScript(selectedId, id), api.previewReview(selectedId, id)])
      setCanonical(source); setPreviewReview(review)
    } catch (error) { setMessage(error.message) }
  }
  const openDraft = async () => {
    if (!selectedId || !versionId) return
    setBusy(true); setMessage('')
    try {
      const next = await api.createProductionDraft(selectedId, versionId)
      setState(next); setDraft(next.draft); setDirty(false); setCanonical(await api.canonicalScript(selectedId, versionId))
      setPreviewReview(next.draft?.preview_review || await api.previewReview(selectedId, versionId))
      setMessage(`Draft opened from Preview ${next.draft?.preview_review_id || ''}`)
    } catch (error) { setMessage(error.message) } finally { setBusy(false) }
  }
  const saveDraft = async () => {
    if (!draft || !selectedId) return
    setBusy(true); setMessage('')
    try {
      const next = await api.saveProductionDraft(selectedId, {
        draft_id: draft.draft_id, canonical_version_id: draft.canonical_version_id,
        script: draft.script, media_cues: draft.media_cues || [], morb_proposals: draft.morb_proposals || [],
      })
      setState(next); setDraft(next.draft); setDirty(false); setMessage('Production draft saved')
    } catch (error) { setMessage(error.message) } finally { setBusy(false) }
  }
  const approve = async () => {
    if (!draft || dirty || busy || draft.morb_proposals?.some(item => !item.reviewed)) return
    setBusy(true); setMessage('')
    try { const next = await api.approveProductionDraft(selectedId, draft.draft_id); setState(next); setDraft(next.draft); setMessage(`Approved ${next.current_approved_version_id}`) }
    catch (error) { setMessage(error.message) } finally { setBusy(false) }
  }
  const updateLine = (lineId, field, value) => {
    setDraft(current => ({ ...current, script: current.script.map(line => line.production_line_id === lineId ? { ...line, [field]: value } : line) }))
    setDirty(true)
  }
  const moveLine = (index, delta) => {
    const target = index + delta
    if (target < 0 || target >= draft.script.length) return
    const script = [...draft.script]; [script[index], script[target]] = [script[target], script[index]]
    setDraft(current => ({ ...current, script })); setDirty(true)
  }
  const addLine = () => {
    if (!draft) return
    const line = { production_line_id: `pl_${crypto.randomUUID()}`, source_canonical_line_id: null,
      speaker: 'phil', text: '', spoken_text: '', original_text: '', emotion: 'neutral',
      delivery_notes: '', pause_after: 0.4, production_cues: [], generated_by: 'production_editor' }
    setDraft(current => ({ ...current, script: [...current.script, line] })); setDirty(true)
  }
  const deleteLine = (lineId) => {
    setDraft(current => ({ ...current,
      script: current.script.filter(line => line.production_line_id !== lineId),
      morb_proposals: current.morb_proposals.map(item => item.production_line_id === lineId
        ? { ...item, reviewed: true, operator_decision: 'reject' } : item),
    })); setDirty(true)
  }
  const reviewProposal = (proposalId, decision) => {
    setDraft(current => ({ ...current, morb_proposals: current.morb_proposals.map(item => item.proposal_id === proposalId
      ? { ...item, reviewed: true, operator_decision: decision } : item) }))
    setDirty(true)
  }
  const addLineCue = (lineId, assetId) => {
    if (!assetId) return
    const asset = cueAssets.find(item => (item.asset_id || item.id) === assetId)
    setDraft(current => ({ ...current, script: current.script.map(line => line.production_line_id === lineId ? {
      ...line, production_cues: [...(line.production_cues || []), { cue_id: `cue_${crypto.randomUUID()}`, asset_id: assetId,
        cue_type: String(asset?.role || 'sfx').toLowerCase(), notes: String(asset?.role || '').toLowerCase() === 'sfx' ? 'overlay' : '' }],
    } : line) }))
    setDirty(true)
  }
  const removeLineCue = (lineId, cueId) => {
    setDraft(current => ({ ...current, script: current.script.map(line => line.production_line_id === lineId ? {
      ...line, production_cues: (line.production_cues || []).filter(cue => cue.cue_id !== cueId),
    } : line) }))
    setDirty(true)
  }

  const canonicalLines = canonical?.script || []
  const draftLines = draft?.script || []
  const approved = state?.approval_state === 'approved'
  const episode = episodes.find(item => (item.episode_id || item.id) === selectedId) || {}
  const words = useMemo(() => draftLines.reduce((sum, line) => sum + String(line.text || '').trim().split(/\s+/).filter(Boolean).length, 0), [draftLines])

  return <div className="production-editor-page" style={{ display: 'grid', gridTemplateColumns: '190px minmax(0,1fr) 250px', height: '100%', minHeight: 0 }}>
    <aside style={{ borderRight: '1px solid var(--rim)', overflow: 'auto', padding: 10 }}>
      <div style={{ ...label, padding: '5px 4px 10px' }}>Episodes</div>
      {episodes.map(item => {
        const id = item.episode_id || item.id
        return <button key={id} onClick={() => chooseEpisode(id)} style={{ display: 'block', width: '100%', textAlign: 'left', marginBottom: 6, padding: 9, color: id === selectedId ? 'var(--gold)' : 'var(--bone)', background: id === selectedId ? 'var(--gold-dim)' : 'var(--surface)', border: `1px solid ${id === selectedId ? 'var(--gold)' : 'var(--rim)'}`, borderRadius: 5, cursor: 'pointer' }}>
          <span style={{ ...label, display: 'block' }}>{String(id).slice(0, 18)}</span><span style={{ fontSize: '0.94rem' }}>{item.title || item.name || id}</span>
        </button>
      })}
    </aside>

    <main style={{ display: 'flex', flexDirection: 'column', minWidth: 0, minHeight: 0 }}>
      <header style={{ padding: '10px 14px', borderBottom: '1px solid var(--rim)', display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <div style={{ flex: 1, minWidth: 180 }}><div style={{ font: '1.56rem var(--font-display)', letterSpacing: '.06em' }}>{episode.title || 'PRODUCTION EDITOR'}</div><div style={label}>Canonical source → editable production copy → explicit approval</div></div>
        <select className="ds-select" value={versionId} onChange={event => chooseCanonical(event.target.value)} aria-label="Canonical version" style={{ maxWidth: 180 }}>
          {versions.map(item => <option key={item.version_id} value={item.version_id}>{item.version_id} · {item.word_count} words</option>)}
        </select>
        <button className="btn btn-steel" onClick={() => refresh()} disabled={!selectedId || busy}><RefreshCw size={11} /> REFRESH</button>
      </header>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,minmax(0,1fr))', gap: 8, padding: '9px 12px', borderBottom: '1px solid var(--rim)' }}>
        {[["CANONICAL SCRIPT", canonical?.version_id || '—', canonical ? 'READY · IMMUTABLE' : 'NOT LOADED'], ['PRODUCTION DRAFT', draft?.draft_id || '—', dirty ? 'UNSAVED EDITS' : draft ? 'EDITING COPY' : 'NOT OPEN'], ['APPROVED PRODUCTION', state?.current_approved_version_id || '—', approved ? `APPROVED · ${state.approved?.approved_at || ''}` : state?.approval_state === 'stale' ? 'APPROVAL STALE' : 'REQUIRES APPROVAL']].map(([title, value, sub]) => <div key={title} style={panel}><div style={label}>{title}</div><div style={{ margin: '5px 0', fontWeight: 700 }}>{value}</div><div style={{ ...label, color: title.startsWith('APPROVED') && approved ? 'var(--green)' : 'var(--steel)' }}>{sub}</div></div>)}
      </div>

      <div style={{ display: 'flex', gap: 6, alignItems: 'center', padding: '8px 12px', borderBottom: '1px solid var(--rim)', flexWrap: 'wrap' }}>
        <span style={{ ...label, color: 'var(--green)' }}>1 GENERATE · CANONICAL READY</span><span style={{ color: 'var(--steel)' }}>→</span><span style={{ ...label, color: previewReview?.saved ? 'var(--green)' : 'var(--steel)' }}>2 PREVIEW {previewReview?.saved ? 'SAVED' : 'REQUIRED'}</span><span style={{ color: 'var(--steel)' }}>→</span><span style={{ ...label, color: draft ? 'var(--gold)' : 'var(--steel)' }}>3 EDITOR {draft ? 'DRAFT' : 'LOCKED'}</span><span style={{ color: 'var(--steel)' }}>→</span><span style={{ ...label, color: approved ? 'var(--green)' : 'var(--steel)' }}>4 PRODUCE {approved ? 'APPROVED' : 'GATED'}</span>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 6 }}>
        <button className="btn btn-steel" onClick={openDraft} disabled={!versionId || !previewReview?.saved || busy}><FileText size={10} /> OPEN FROM PREVIEW</button>
          <button className="btn btn-steel" onClick={saveDraft} disabled={!draft || !dirty || busy}><Save size={10} /> SAVE DRAFT</button>
          <button className="btn btn-solid" onClick={approve} disabled={!draft || dirty || busy || approved || draft.morb_proposals?.some(item => !item.reviewed)}><ShieldCheck size={10} /> APPROVE PRODUCTION VERSION</button>
        </div>
      </div>

      {message && <div role="status" style={{ padding: '6px 12px', color: message.toLowerCase().includes('failed') || message.toLowerCase().includes('error') ? 'var(--red)' : 'var(--gold)', fontSize: '0.88rem' }}>{message}</div>}
      <div style={{ flex: 1, overflow: 'auto', padding: 10 }}>
        {previewReview?.saved && <section style={{ ...panel, marginBottom: 10 }}>
          <div style={{ ...label, display: 'flex', justifyContent: 'space-between', gap: 8 }}><span>PREVIEW HANDOFF · {previewReview.review_id} · {previewReview.preview_hash?.slice(0, 12)}</span><span>Canonical {previewReview.canonical_version_id}</span></div>
          {previewReview.overall_notes && <div style={{ marginTop: 7, fontSize: '0.88rem' }}><b>Overall:</b> {previewReview.overall_notes}</div>}
          {Object.entries(previewReview.section_notes || {}).filter(([, note]) => note).map(([key, note]) => <div key={key} style={{ marginTop: 5, fontSize: '0.86rem' }}><b>{key}:</b> {note}</div>)}
          {Object.entries(previewReview.line_reviews || {}).filter(([, item]) => item.mark !== 'none' || item.note).map(([lineId, item]) => <div key={lineId} style={{ marginTop: 4, color: item.mark === 'needs_attention' || item.mark === 'possible_cut' ? 'var(--gold)' : 'var(--steel)', fontSize: '0.83rem' }}>{lineId} · {item.mark}{item.note ? ` — ${item.note}` : ''}</div>)}
        </section>}
        {!draft && <div style={{ ...panel, marginBottom: 10, color: 'var(--steel)' }}>{previewReview?.saved ? 'Open this saved Preview handoff as a production draft. The canonical snapshot remains read-only.' : 'Save and send a canonical version from the Preview stage before opening it here.'}</div>}
        <div className="production-editor-columns" style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) minmax(0,1.25fr)', gap: 9, minHeight: '60%' }}>
          <section style={{ ...panel, overflow: 'auto' }}>
            <div style={{ ...label, marginBottom: 8 }}>CANONICAL SCRIPT ({canonical?.version_id || '—'}) · READ ONLY</div>
            {canonicalLines.map((line, index) => <div key={line.canonical_line_id || index} style={{ padding: '7px 5px', borderBottom: '1px solid var(--rim)', fontSize: '0.88rem', lineHeight: 1.45 }}><b style={{ color: (line.speaker || '').toLowerCase() === 'jim' ? 'var(--blue)' : 'var(--gold)' }}>#{index + 1} {(line.speaker || 'PHIL').toUpperCase()}</b><div>{line.text}</div></div>)}
          </section>
          <section style={{ ...panel, overflow: 'auto' }}>
            <div style={{ ...label, display: 'flex', justifyContent: 'space-between', marginBottom: 8, alignItems: 'center' }}><span>PRODUCTION COPY · DRAFT</span><span>{draftLines.length} lines · {words} words</span><button className="btn btn-steel btn-sm" onClick={addLine} disabled={!draft}><Plus size={9} /> ADD LINE</button></div>
            {draftLines.map((line, index) => <div key={line.production_line_id} style={{ padding: '7px 4px', marginBottom: 5, background: 'var(--surface)', border: '1px solid var(--rim)', borderRadius: 4 }}>
              <div style={{ display: 'grid', gridTemplateColumns: '28px 88px minmax(0,1fr) 70px 24px 24px 24px', gap: 5, alignItems: 'center' }}>
                <span style={label}>#{index + 1}</span>
                <select style={input} value={(line.speaker || 'phil').toLowerCase()} onChange={event => updateLine(line.production_line_id, 'speaker', event.target.value)}>{['phil','jim','bryan','host','guest'].map(name => <option key={name} value={name}>{name.toUpperCase()}</option>)}</select>
                <textarea style={{ ...input, minHeight: 42, resize: 'vertical' }} value={line.text || ''} disabled={!draft} onChange={event => updateLine(line.production_line_id, 'text', event.target.value)} aria-label={`Dialogue line ${index + 1}`} />
                <input style={input} type="number" min="0" max="3" step="0.05" value={line.pause_after ?? 0.4} onChange={event => updateLine(line.production_line_id, 'pause_after', Number(event.target.value))} aria-label="Pause seconds" />
                <button className="icon-btn" title="Move up" onClick={() => moveLine(index, -1)}><ArrowUp size={10} /></button><button className="icon-btn" title="Move down" onClick={() => moveLine(index, 1)}><ArrowDown size={10} /></button>
                <button className="icon-btn del" title="Delete production line" onClick={() => deleteLine(line.production_line_id)}><Trash2 size={10} /></button>
                <div style={{ gridColumn: '2 / -1', display: 'grid', gridTemplateColumns: 'minmax(0,1fr) minmax(100px,.8fr)', gap: 5 }}>
                  <label style={label}>PRONUNCIATION / SPOKEN FORM<input style={{ ...input, marginTop: 3 }} value={line.spoken_text || line.text || ''} onChange={event => updateLine(line.production_line_id, 'spoken_text', event.target.value)} /></label>
                  <div><label style={label}>NOTES / CUES<input style={{ ...input, marginTop: 3 }} value={line.delivery_notes || ''} onChange={event => updateLine(line.production_line_id, 'delivery_notes', event.target.value)} /></label>
                    <select style={{ ...input, marginTop: 4 }} defaultValue="" onChange={event => { addLineCue(line.production_line_id, event.target.value); event.target.value = '' }} aria-label="Add an audio production cue">
                      <option value="">Add audio cue…</option>{cueAssets.map(asset => <option key={asset.asset_id || asset.id} value={asset.asset_id || asset.id}>{asset.label || asset.filename || asset.original_name || asset.asset_id}</option>)}
                    </select>
                    {(line.production_cues || []).map(cue => <button key={cue.cue_id || cue.asset_id} className="btn btn-steel btn-sm" style={{ margin: '4px 4px 0 0' }} onClick={() => removeLineCue(line.production_line_id, cue.cue_id)} title="Remove cue from this production line">{cue.asset_id} ×</button>)}
                  </div>
                </div>
              </div>
            </div>)}
          </section>
        </div>

        {draft && <section style={{ ...panel, marginTop: 9 }}>
          <div style={label}>MORB RECOMMENDATIONS · {draft.morb_proposals?.length || 0} · OPERATOR REVIEW REQUIRED</div>
          {(draft.morb_proposals || []).map(item => <div key={item.proposal_id} style={{ display: 'flex', gap: 8, alignItems: 'center', borderBottom: '1px solid var(--rim)', padding: '6px 0', fontSize: '0.87rem' }}>
            <AlertTriangle size={12} color={item.reviewed ? 'var(--green)' : 'var(--gold)'} /><span style={{ flex: 1 }}>{item.production_line_id} · {item.morb} · {item.action} · {item.reason} · {item.reviewed ? `OPERATOR ${item.operator_decision}` : 'PENDING'}</span>
            {!item.reviewed && <><button className="btn btn-steel btn-sm" onClick={() => reviewProposal(item.proposal_id, 'accept')}>ACCEPT</button><button className="btn btn-steel btn-sm" onClick={() => reviewProposal(item.proposal_id, 'reject')}>REJECT</button></>}
          </div>)}
          <div style={{ ...label, marginTop: 9 }}>CHANGE LEDGER · {draft.change_ledger?.length || 0} changes</div>
          {(draft.change_ledger || []).slice(-8).map((item, index) => <span key={index} style={{ display: 'inline-block', margin: '6px 8px 0 0', color: 'var(--steel)', fontSize: '0.81rem' }}>{item.action} {item.production_line_id || ''} {item.field || ''}</span>)}
        </section>}
      </div>
      <footer style={{ borderTop: '1px solid var(--rim)', padding: '8px 12px', display: 'flex', gap: 18, flexWrap: 'wrap', ...label }}>
        <span>CANONICAL {canonical?.version_id || '—'} · {canonical?.canonical_hash?.slice(0, 12) || '—'}</span><span>COPY HASH {draft?.production_copy_hash?.slice(0, 12) || '—'}</span><span>APPROVAL {approved ? `${state.current_approved_version_id} · ${state.approved?.approved_at}` : (state?.approval_state || 'none')}</span><span>CHANGE LEDGER {draft?.change_ledger?.length || 0}</span>
      </footer>
    </main>

    <aside style={{ borderLeft: '1px solid var(--rim)', padding: 10, overflow: 'auto' }}>
      <div style={{ ...label, marginBottom: 8 }}>AUDIO PREVIEW</div>
      {selectedId && <><audio controls style={{ width: '100%' }} src={`${api.audioUrl(selectedId)}?v=${state?.approved?.approved_at || 'editor'}`} /><div style={{ ...panel, marginTop: 10 }}><div style={label}>EPISODE INFO</div><div style={{ fontSize: '0.88rem', lineHeight: 1.8, marginTop: 6 }}>Title: {episode.title || '—'}<br />Canonical: {canonical?.version_id || '—'}<br />Draft: {draft?.draft_id || '—'}<br />Lines: {draftLines.length}<br />Runtime estimate: {Math.floor(words / 90)}:{String(Math.round((words % 90) / 1.5)).padStart(2, '0')}</div></div></>}
      <div style={{ ...panel, marginTop: 10 }}><div style={label}>PRODUCTION STATE</div>{['Canonical Ready', 'Editor Draft', 'Approved', 'Producing', 'QC', 'Final'].map((step, index) => <div key={step} style={{ padding: '6px 0', color: index === 0 && canonical || index === 1 && draft || index === 2 && approved ? 'var(--green)' : 'var(--steel)', fontSize: '0.88rem' }}>{index < 3 ? '●' : '○'} &nbsp;{step}</div>)}</div>
    </aside>
  </div>
}
