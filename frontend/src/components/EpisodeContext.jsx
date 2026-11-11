import { useEffect, useState } from 'react'
import { api, req } from '../lib/api'
import SegmentsView from './SegmentsView'

const DIRECTION_FIELDS = [
  ['episode_direction', 'Episode direction'], ['angle_and_tone', 'Angle and tone'],
  ['must_include', 'Must include'], ['must_avoid', 'Must avoid'], ['segment_notes', 'Segment notes'],
]
function directionValues(value = {}) {
  return { ...Object.fromEntries(DIRECTION_FIELDS.map(([key]) => [key, value?.[key] || ''])), per_source_notes: value?.per_source_notes || {} }
}

function statsFromPacket(packet) {
  return Object.fromEntries((packet?.sources || []).map(source => [source.source_id, {
    character_count: source.character_count ?? source.sections.reduce((total, record) => total + record.text.length, 0),
    estimated_tokens: source.estimated_tokens ?? Math.ceil(new TextEncoder().encode(source.sections.map(record => record.text).join('')).length / 3),
    record_count: source.sections.length,
    records: source.sections.slice(0, 20).map(record => ({ ...record, text_preview: record.text.slice(0, 200) })),
  }]))
}

function download(name, content, type) {
  const url = URL.createObjectURL(new Blob([content], { type }))
  const link = document.createElement('a')
  link.href = url
  link.download = name
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

const SECTION_TABS = [['direction', 'Direction'], ['sources', 'Sources'], ['brief', 'Brief'], ['bible', 'Show Bible'], ['facts', 'Source Facts'], ['format', 'Format'], ['ads', 'Ad Slots'], ['build', 'Build & Export'], ['segments', 'Segments'], ['short-copy', 'Short Copy']]

export default function EpisodeContext({ episodeId, onImport, onOpenAds, onDraftAccepted }) {
  const [section, setSection] = useState('direction')
  const [reference, setReference] = useState({})
  const [sources, setSources] = useState([])
  const [selected, setSelected] = useState([])
  const [brief, setBrief] = useState('')
  const [packet, setPacket] = useState(null)
  const [text, setText] = useState('')
  const [title, setTitle] = useState('')
  const [sourceUrl, setSourceUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const [writerDraft, setWriterDraft] = useState(null)
  const [generationJob, setGenerationJob] = useState(null)
  const [error, setError] = useState('')
  const [copyKind, setCopyKind] = useState('post')
  const [copyFacts, setCopyFacts] = useState('')
  const [copy, setCopy] = useState('')
  const [ocr, setOcr] = useState(null)
  const [direction, setDirection] = useState(directionValues())
  const [directionRevision, setDirectionRevision] = useState('')
  const [savedDirection, setSavedDirection] = useState(JSON.stringify(directionValues()))
  const [ready, setReady] = useState(false)
  const [notice, setNotice] = useState('')
  const [priorities, setPriorities] = useState([])
  const [modelName, setModelName] = useState('NVIDIA Nemotron')
  const [windowTokens, setWindowTokens] = useState(32768)
  const [reservedTokens, setReservedTokens] = useState(4096)
  const [inspection, setInspection] = useState({})
  const [inspectionWarnings, setInspectionWarnings] = useState([])
  const effectivePriorities = priorities.filter(id => selected.includes(id))
  const sourceTokens = selected.reduce((sum, id) => sum + (inspection[id]?.estimated_tokens || 0), 0)
  const unknownSources = selected.filter(id => inspection[id]?.estimated_tokens == null && !inspection[id]?.error).length
  const unreadableSources = selected.filter(id => inspection[id]?.error).length
  const liveEstimate = sourceTokens + Math.ceil(new TextEncoder().encode(JSON.stringify(direction) + brief).length / 3)
  const inputBudget = Number(windowTokens) - Number(reservedTokens)
  const invalidBudget = Number(windowTokens) < 1024 || Number(reservedTokens) < 256 || inputBudget <= 0
  const curationDirty = packet && (
    JSON.stringify([...selected].sort()) !== JSON.stringify(packet.sources.map(source => source.source_id).sort()) ||
    JSON.stringify([...effectivePriorities].sort()) !== JSON.stringify([...(packet.curation?.priority_source_ids || [])].sort()) ||
    brief !== packet.brief || modelName !== (packet.curation?.model_name || 'External LLM') ||
    Number(windowTokens) !== (packet.curation?.context_window_tokens || 32768) ||
    Number(reservedTokens) !== (packet.curation?.reserved_output_tokens || 4096))

  const directionDirty = JSON.stringify(direction) !== savedDirection
  const packDirectionStale = packet && (packet.owner_direction?.revision_id || '') !== directionRevision
  const path = `/episodes/${encodeURIComponent(episodeId)}`
  const generationRunning = ['generating', 'cancellation_requested'].includes(generationJob?.status)
  const generationBlocked = busy || generationRunning || !ready || !packet || directionDirty || packDirectionStale || curationDirty || invalidBudget

  useEffect(() => {
    let live = true
    const refresh = async () => {
      try {
        const [draft, job] = await Promise.all([api.writerDraft(episodeId), api.generationStatus(episodeId)])
        if (live) { setWriterDraft(draft); setGenerationJob(job) }
      } catch { /* A temporarily offline backend does not clear the saved form. */ }
    }
    setWriterDraft(null); setGenerationJob(null)
    refresh()
    const timer = setInterval(refresh, 3000)
    return () => { live = false; clearInterval(timer) }
  }, [episodeId])

  async function loadSources() {
    const data = await req(`${path}/assets`)
    const rows = data.assets.filter(a => a.asset_id?.startsWith('asset_') && a.role === 'source')
    const known = new Set(sources.map(source => source.asset_id))
    setSources(rows)
    setSelected(current => [...current.filter(id => rows.some(row => row.asset_id === id)), ...rows.filter(row => !known.has(row.asset_id)).map(row => row.asset_id)])
  }

  useEffect(() => {
    let live = true
    req('/authoring/ocr/status').then(result => { if (live) setOcr(result) }).catch(() => { if (live) setOcr({ available: false }) })
    setPriorities([]); setModelName('External LLM'); setWindowTokens(32768); setReservedTokens(4096); setInspection({}); setInspectionWarnings([])
    setReady(false); setNotice(''); setDirection(directionValues()); setDirectionRevision(''); setSavedDirection(JSON.stringify(directionValues()))
    setPacket(null); setBrief(''); setSources([]); setSelected([]); setError('')
    setText(''); setTitle(''); setSourceUrl(''); setCopy(''); setCopyFacts('')
    Promise.all([req(`${path}/assets`), req(`${path}/context`), req(`${path}/context/direction`), req(`${path}/context/reference`).catch(() => ({}))]).then(([data, saved, savedOwner, referenceData]) => {
      if (!live) return
      setReference(referenceData)
      const rows = data.assets.filter(a => a.asset_id?.startsWith('asset_') && a.role === 'source')
      setSources(rows); setSelected(saved ? rows.filter(a => saved.sources.some(source => source.source_id === a.asset_id)).map(a => a.asset_id) : rows.map(a => a.asset_id))
      const owner = savedOwner?.authority ? savedOwner : saved?.owner_direction
      setDirection(directionValues(owner)); setSavedDirection(JSON.stringify(directionValues(owner))); setDirectionRevision(owner?.revision_id || '')
      setPacket(saved); setBrief(saved?.brief ?? referenceData.episode_brief ?? ''); setReady(true)
      setPriorities(saved?.curation?.priority_source_ids || []); setModelName(saved?.curation?.model_name || 'External LLM')
      setWindowTokens(saved?.curation?.context_window_tokens || 32768); setReservedTokens(saved?.curation?.reserved_output_tokens || 4096); setInspection(statsFromPacket(saved))
    }).catch(e => { if (live) setError(e.message) })
    return () => { live = false }
  }, [path])

  async function act(work) {
    setBusy(true); setError('')
    try { await work() } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  const prefix = `context-${episodeId}`
  const characters = reference.show_bible || packet?.show_bible || []
  const contract = reference.format_contract || packet?.format_contract || {}
  const slots = reference.ad_slots || packet?.ad_slots || {}
  const panel = (key, content) => <div key={key} role="tabpanel" id={`${prefix}-panel-${key}`} aria-labelledby={`${prefix}-tab-${key}`} hidden={section !== key} className="context-section-panel">{content}</div>

  return <section aria-label="Episode context" className="episode-context-editor">
    <header className="context-editor-header">
      <h2>Context Generator &amp; Editor</h2>
      <div className="gap-row" style={{ flexWrap: 'wrap' }}>
        <span>{packet ? `Saved: ${packet.version_id}` : 'No context pack built yet'}</span>
        <button className="btn btn-steel btn-sm" onClick={onImport} disabled={busy}>IMPORT FINISHED SCRIPT</button>
      </div>
      {directionDirty && <span role="status">Unsaved owner direction — save Direction or build a new pack.</span>}
      {notice && <p role="status">{notice}</p>}
      {error && <p role="alert" style={{ color: 'var(--gold)', whiteSpace: 'pre-wrap' }}>{error}</p>}
      {generationRunning && <p role="status">Writer request {generationJob.status === 'cancellation_requested' ? 'cancellation requested' : 'running'}{generationJob.progress?.segment ? ` · segment ${generationJob.progress.segment}, pass ${generationJob.progress.pass} of ${generationJob.progress.passes} (${generationJob.progress.words_so_far} of ~${generationJob.progress.target_words} words)` : generationJob.progress?.section ? ` · section ${generationJob.progress.section} of ${generationJob.progress.sections} (${generationJob.progress.words_so_far} of ~${generationJob.progress.target_words} words)` : ''} · started {generationJob.started_at}. Your saved script remains available.
        <button className="btn btn-steel btn-sm" onClick={async () => { try { await api.cancelJob(episodeId); setNotice('Cancellation requested. The provider may finish its current request; its reply will not activate a script.') } catch (e) { setError(e.message) } }}>CANCEL WRITER</button>
      </p>}
    </header>
    <div role="tablist" aria-label="Context sections" className="context-section-tabs">
      {SECTION_TABS.map(([key, label], index) => <button key={key} role="tab" id={`${prefix}-tab-${key}`} aria-selected={section === key} aria-controls={`${prefix}-panel-${key}`} tabIndex={section === key ? 0 : -1} onClick={() => setSection(key)} onKeyDown={event => {
        const shifts = { ArrowRight: 1, ArrowLeft: -1, Home: -index, End: SECTION_TABS.length - 1 - index }
        if (!(event.key in shifts)) return
        event.preventDefault()
        const next = (index + shifts[event.key] + SECTION_TABS.length) % SECTION_TABS.length
        setSection(SECTION_TABS[next][0])
        event.currentTarget.parentElement.querySelectorAll('[role="tab"]')[next].focus()
      }}>{label}</button>)}
    </div>
    <div className="context-panel-scroll">
      {panel('direction', <>
    <fieldset disabled={busy || !ready} aria-label="Manual Direction" style={{ border: '1px solid var(--gold)', padding: 12, display: 'grid', gap: 10 }}>
      <legend>Manual Direction · owner instructions</legend>
      <p style={{ margin: 0 }}>Your direction takes editorial priority over the brief, show bible and source content. Source evidence stays separate; factual conflicts must be flagged for you.</p>
      <div className="context-direction-fields">{DIRECTION_FIELDS.map(([key, label]) => <label key={key}>{label}
        <textarea className="ds-input" style={{ display: 'block', width: '100%' }} rows={key === 'episode_direction' ? 4 : 3} maxLength={key === 'angle_and_tone' ? 10000 : 20000} value={direction[key]} onChange={e => setDirection(current => ({ ...current, [key]: e.target.value }))} />
      </label>)}</div>
      <button className="btn btn-gold" disabled={busy || !ready || (!directionDirty && Boolean(directionRevision) && !packDirectionStale)} onClick={() => act(async () => {
        const result = await req(`${path}/context/direction`, { method: 'PUT', body: JSON.stringify({ owner_direction: direction, expected_direction_revision: directionRevision }) })
        const owner = result.owner_direction
        setDirection(directionValues(owner)); setSavedDirection(JSON.stringify(directionValues(owner))); setDirectionRevision(owner.revision_id || '')
        if (result.package) setPacket(result.package)
        setNotice(result.pack_regenerated ? 'Direction saved. A new pack version was created using the previous pack’s source evidence.' : 'Owner direction saved.')
      })}>SAVE OWNER DIRECTION</button>
      <span role="status">{directionDirty ? 'Unsaved owner direction. Save it or build a pack before leaving this episode.' : directionRevision ? `Saved: ${directionRevision}` : 'Direction has not been saved yet.'}</span>
    </fieldset>
      </>)}
      {panel('sources', <>
    <p style={{ margin: 0 }}>Upload Markdown, READMEs, text, code, PDF, Word (.docx), or images. Uploaded code is read, never executed. Images use local Tesseract OCR. For Google Docs, download a DOCX or paste its text below. Scanned PDFs still need conversion to images or OCR before upload.</p>
    <p style={{ margin: 0 }} role="status">Image OCR: {ocr === null ? 'checking…' : ocr.available ? `${ocr.version} · local · English` : 'unavailable — install Tesseract with English language data'}. OCR transcribes text; it does not describe pictures.</p>
    <label>Source files <input type="file" multiple disabled={busy || !ready} accept="text/*,image/*,.txt,.md,.markdown,.rst,.pdf,.docx,.json,.csv,.py,.pyi,.js,.jsx,.ts,.tsx,.mjs,.cjs,.yaml,.yml,.toml,.ps1,.sql,.go,.rs,.java,.c,.cpp,.h,.cs,.xml,.ini,.sh" onChange={e => {
      const files = [...e.target.files]; e.target.value = ''
      act(async () => {
        const failures = []
        for (const file of files) {
          const form = new FormData(); form.append('file', file); form.append('role', 'source')
          const response = await fetch(`/api${path}/assets`, { method: 'POST', body: form })
          if (!response.ok) failures.push(`${file.name}: ${await response.text()}`)
        }
        await loadSources()
        if (failures.length) throw new Error(failures.join('\n'))
      })
    }} /></label>
    <details><summary>Paste a source document</summary>
      <div style={{ display: 'grid', gap: 8, marginTop: 8 }}>
        <input className="ds-input" aria-label="Source title" placeholder="Source title" value={title} onChange={e => setTitle(e.target.value)} />
        <input className="ds-input" aria-label="Source URL" placeholder="Original URL (optional, recorded as a reference)" value={sourceUrl} onChange={e => setSourceUrl(e.target.value)} />
        <textarea className="ds-input" aria-label="Source document text" rows={6} value={text} onChange={e => setText(e.target.value)} />
        <button className="btn btn-steel" disabled={busy || !title.trim() || !text.trim()} onClick={() => act(async () => {
          await req(`${path}/context/sources/text`, { method: 'POST', body: JSON.stringify({ title, text, source_url: sourceUrl }) })
          setText(''); setTitle(''); setSourceUrl(''); await loadSources()
        })}>ADD SOURCE</button>
      </div>
    </details>
    <fieldset disabled={busy || !ready} style={{ border: '1px solid var(--rim)', display: 'grid', gap: 6 }}><legend>Include sources</legend>
      {!sources.length && <span>No source documents uploaded yet.</span>}
      {sources.map(source => <div key={source.asset_id} style={{ overflowWrap: 'anywhere', display: 'grid', gap: 5, paddingBottom: 8 }}>
        <label><input type="checkbox" checked={selected.includes(source.asset_id)} onChange={e => setSelected(current => e.target.checked ? [...current, source.asset_id] : current.filter(id => id !== source.asset_id))} /> {source.label || source.original_name}</label>
        <label><input type="checkbox" checked={priorities.includes(source.asset_id)} disabled={!selected.includes(source.asset_id)} aria-label={`Priority source ${source.label || source.original_name}`} onChange={e => setPriorities(current => e.target.checked ? [...current, source.asset_id] : current.filter(id => id !== source.asset_id))} /> Priority · include first in the source evidence</label>
        {inspection[source.asset_id] && <div style={{ fontSize: '.85rem' }}>
          <span>{inspection[source.asset_id].error || `${inspection[source.asset_id].record_count} records · approximately ${inspection[source.asset_id].estimated_tokens.toLocaleString()} source tokens`}</span>
          {inspection[source.asset_id].records?.length > 0 && <details><summary>Locations and excerpts (first 20 records)</summary>
            {inspection[source.asset_id].records.map((record, index) => <div key={record.record_id || index} style={{ padding: 6, borderBottom: '1px solid var(--rim)' }}>
              <strong>{record.location}{record.heading ? ` · ${record.heading}` : ''}</strong>
              <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{record.text_preview}</pre>
            </div>)}
          </details>}
        </div>}
        <label>Owner note for {source.label || source.original_name}
          <textarea className="ds-input" rows={2} style={{ display: 'block', width: '100%' }} maxLength={10000} placeholder="Use only the pricing section; outdated; Jim reads this…" value={direction.per_source_notes[source.asset_id] || ''} onChange={e => setDirection(current => ({ ...current, per_source_notes: { ...current.per_source_notes, [source.asset_id]: e.target.value } }))} />
        </label>
      </div>)}
    </fieldset>
    <button className="btn btn-steel" disabled={busy || !ready || !selected.length} onClick={() => act(async () => {
      const result = await req(`${path}/context/inspect`, { method: 'POST', body: JSON.stringify({ source_ids: selected }) })
      const updates = Object.fromEntries(selected.map(id => [id, { error: 'Unreadable source — see analysis warnings.' }]))
      result.sources.forEach(source => { updates[source.source_id] = source })
      setInspection(current => ({ ...current, ...updates })); setInspectionWarnings(result.warnings)
    })}>ANALYZE SELECTED SOURCES</button>
    {inspectionWarnings.map((warning, index) => <p role="status" key={index} style={{ margin: 0 }}>{warning}</p>)}
      </>)}
      {panel('brief', <><h3>Episode Brief</h3>
    <label>Episode brief: angle, audience, questions, required points
      <textarea className="ds-input" style={{ width: '100%' }} rows={4} value={brief} onChange={e => setBrief(e.target.value)} />
    </label>
      </>)}
      {panel('bible', <>
        <h3>Show Bible</h3><p>Current character references. Building a pack snapshots these profiles; owner direction controls your episode’s tone.</p>
        {!characters.length && <p>No character profile loaded yet. Build a pack or reload to load the references.</p>}
        {characters.map(character => <article key={character.speaker}><h4>{character.speaker.toUpperCase()}</h4><p>{character.source_file} · {character.location}</p><pre className="context-reference-text">{JSON.stringify(character.persona || character.character || { identity: character.identity, personality: character.personality }, null, 2)}</pre></article>)}
      </>)}
      {panel('facts', <>
        <h3>Source Facts</h3><p>Read-only extraction previews. Use Sources to analyze files and Direction/source notes to guide the writer. Full evidence remains in the exported pack.</p>
        {!selected.some(id => inspection[id]?.records?.length) && <p>Analyze selected files in Sources to view their records here.</p>}
        {sources.filter(source => selected.includes(source.asset_id)).map(source => <article key={source.asset_id}>
          <h4>{source.label || source.original_name}</h4>
          {(inspection[source.asset_id]?.records || []).map((record, index) => <div key={record.record_id || index}><strong>{record.location}{record.heading ? ` · ${record.heading}` : ''}</strong><pre className="context-reference-text">{record.text_preview}</pre></div>)}
        </article>)}
      </>)}
      {panel('format', <><h3>Format Contract</h3><p>The returned script must match this contract before production review.</p><ul>{Object.entries(contract).map(([key, value]) => <li key={key}>{value}</li>)}</ul>{!Object.keys(contract).length && <p>Build a pack or reload to load the format contract.</p>}</>)}
      {panel('ads', <><h3>Ad Slots</h3><p>Current ad placements and settings. Edit ads in the Ads workspace, then build a new context pack.</p><pre className="context-reference-text">{slots.ads?.length || Object.keys(slots.settings || {}).length ? JSON.stringify(slots, null, 2) : 'No ad slots configured.'}</pre><button className="btn btn-steel" onClick={onOpenAds}>OPEN ADS</button></>)}
      {panel('build', <><h3>Build &amp; Export</h3>
    <fieldset disabled={busy || !ready} style={{ display: 'grid', gap: 8, border: '1px solid var(--rim)' }}><legend>External model and size planning</legend>
      <label>External model name<input className="ds-input" style={{ display: 'block', width: '100%' }} maxLength={200} value={modelName} onChange={e => setModelName(e.target.value)} /></label>
      <label>Context window (tokens)<input className="ds-input" type="number" min={1024} max={2000000} value={windowTokens} onChange={e => setWindowTokens(e.target.value)} /></label>
      <label>Reserve for script output (tokens)<input className="ds-input" type="number" min={256} max={1000000} value={reservedTokens} onChange={e => setReservedTokens(e.target.value)} /></label>
      <span role="status">Selected source text + direction: approximately {liveEstimate.toLocaleString()} tokens · {unknownSources} unanalysed · {unreadableSources} unreadable sources.</span>
      <progress aria-label="Context input budget estimate" max={Math.max(inputBudget, 1)} value={Math.min(liveEstimate, Math.max(inputBudget, 1))} style={{ width: '100%' }} />
      <span>Live estimate excludes show bible and remaining instructions until the pack is built. Analyze to read new sources; image analysis runs local OCR. No sources are silently trimmed to fit.</span>
      {invalidBudget && <span role="alert">Use a context window of at least 1024 tokens, reserve at least 256 for output, and keep the reserve smaller than the window.</span>}
      {packet?.sizing && <span role="status">Saved Markdown pack: approximately {packet.sizing.estimated_input_tokens.toLocaleString()} input tokens + {packet.sizing.planning_margin_tokens.toLocaleString()} margin, against {packet.sizing.input_budget_tokens.toLocaleString()} input budget. {packet.sizing.fits_estimate ? 'Within the estimated budget.' : 'OVER ESTIMATED BUDGET — reduce sources or choose a larger window.'} JSON trace manifest: approximately {(packet.sizing.json_estimated_input_tokens || 0).toLocaleString()} tokens. These are estimates, not the external model’s exact tokenizer.</span>}
    </fieldset>
    <button className="btn btn-gold" disabled={busy || !ready || !selected.length || invalidBudget} onClick={() => act(async () => {
      const result = await req(`${path}/context`, { method: 'POST', body: JSON.stringify({ brief, source_ids: selected, owner_direction: direction, expected_direction_revision: directionRevision, curation: { priority_source_ids: effectivePriorities, model_name: modelName, context_window_tokens: Number(windowTokens), reserved_output_tokens: Number(reservedTokens) } }) })
      setPacket(result); setInspection(current => ({ ...current, ...statsFromPacket(result) }))
      const owner = result.owner_direction
      setDirection(directionValues(owner)); setSavedDirection(JSON.stringify(directionValues(owner))); setDirectionRevision(owner?.revision_id || '')
      setNotice('New context pack saved with your owner direction.')
    })}>{busy ? 'WORKING…' : 'BUILD CONTEXT PACKAGE'}</button>
    <button className="btn btn-steel" disabled={generationBlocked} onClick={() => act(async () => {
      const result = await api.generateScript(episodeId, { context_version_id: packet.version_id, sample: true })
      setWriterDraft(result); setNotice(`Writer sample saved: ${result.word_count} words. The episode script is unchanged.`)
    })}>TEST WRITER · 8 TURNS</button>
    <button className="btn btn-solid" disabled={!packet} onClick={() => setSection('segments')}>WRITE EPISODE IN SEGMENTS →</button>
    {!packet && <p>Build a context package before testing or generating.</p>}
    {writerDraft && <section aria-label="Writer draft review">
      <h3>{writerDraft.sample ? 'Diagnostic sample' : 'Generated draft'} · {writerDraft.word_count} words</h3>
      <p>Context: {writerDraft.context_version_id} · {writerDraft.status}</p>
      {(writerDraft.review_warnings || []).map((warning, index) => <p role="alert" key={index}>{warning}</p>)}
      <pre className="context-reference-text" style={{ maxHeight: 420, overflow: 'auto', whiteSpace: 'pre-wrap' }}>{(writerDraft.script || []).map(line => `${line.speaker.toUpperCase()}: ${line.text}`).join('\n\n')}</pre>
      <button className="btn btn-steel" onClick={() => download(`${episodeId}-${writerDraft.draft_id}.json`, JSON.stringify(writerDraft, null, 2), 'application/json')}>DOWNLOAD DRAFT JSON</button>
      {!writerDraft.sample && writerDraft.status !== 'accepted' && <button className="btn btn-gold" disabled={busy || generationRunning} onClick={() => act(async () => {
        const result = await api.acceptWriterDraft(episodeId, writerDraft.draft_id)
        setWriterDraft(result); setNotice(`Accepted as ${result.accepted_version_id}. Review and approve it in Preview and Production Editor before audio production.`)
        onDraftAccepted?.()
      })}>ACCEPT DRAFT TO PREVIEW</button>}
    </section>}
    {curationDirty && <p role="status">Source choices, brief or model settings differ from the saved pack. Build a new pack before export.</p>}
    {packDirectionStale && <p role="status">The saved pack uses older direction. Save owner direction or build a new pack before export.</p>}
    {packet && <>
      <p style={{ margin: 0 }}>Saved {packet.version_id} · {packet.sources.length} sources. Downloads contain this saved version; rebuild after changing sources or the brief.</p>
      {packet.warnings.map((warning, i) => <p key={i} role="status" style={{ margin: 0 }}>{warning}</p>)}
      <div className="gap-row" style={{ flexWrap: 'wrap' }}>
        <button className="btn btn-steel" disabled={directionDirty || packDirectionStale || curationDirty || busy} onClick={() => download(`${episodeId}-context.md`, packet.markdown, 'text/markdown')}>DOWNLOAD CONTEXT MD</button>
        <button className="btn btn-steel" disabled={directionDirty || packDirectionStale || curationDirty || busy} onClick={() => download(`${episodeId}-context.json`, JSON.stringify(packet, null, 2), 'application/json')}>DOWNLOAD JSON</button>
      </div>
      <details><summary>Review saved context</summary><pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', maxHeight: 360, overflow: 'auto' }}>{packet.markdown}</pre></details>
    </>}
      </>)}
      {panel('segments', section === 'segments' ? <SegmentsView episodeId={episodeId} generationRunning={generationRunning} onAssembled={onDraftAccepted} /> : null)}
      {panel('short-copy', <>
    <div><h3>Local writer: ads and short posts</h3>
      <div style={{ display: 'grid', gap: 8, marginTop: 8 }}>
        <select className="ds-select" aria-label="Short copy kind" value={copyKind} onChange={e => setCopyKind(e.target.value)}><option value="post">Short post · up to 120 words</option><option value="ad">Ad · up to 180 words</option></select>
        <textarea className="ds-input" aria-label="Short copy facts" rows={4} placeholder="Supply the facts, product, offer and call to action to use" value={copyFacts} onChange={e => setCopyFacts(e.target.value)} />
        <button className="btn btn-steel" disabled={busy || !copyFacts.trim()} onClick={() => act(async () => {
          setCopy(''); const result = await req('/authoring/short-copy', { method: 'POST', body: JSON.stringify({ kind: copyKind, facts: copyFacts }) }); setCopy(result.text)
        })}>GENERATE SHORT COPY</button>
        {copy && <><textarea className="ds-input" aria-label="Generated short copy" rows={6} value={copy} onChange={e => setCopy(e.target.value)} /><button className="btn btn-steel" onClick={() => download(`${episodeId}-${copyKind}.txt`, copy, 'text/plain')}>DOWNLOAD COPY</button></>}
      </div>
    </div>
      </>)}
    </div>
  </section>
}
