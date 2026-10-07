import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, ArrowRight, RefreshCw, Save, Sparkles } from 'lucide-react'
import { api } from '../lib/api'

const marks = [
  ['none', 'No mark'], ['needs_attention', 'Needs attention'], ['possible_cut', 'Possible cut'],
  ['strong', 'Strong'], ['weak', 'Weak'],
]
const panel = { background: 'var(--panel)', border: '1px solid var(--rim)', borderRadius: 8, padding: 12, minWidth: 0 }
const label = { color: 'var(--steel)', font: '600 0.75rem var(--font-mono)', letterSpacing: '.08em', textTransform: 'uppercase' }

function sectionKey(line, index) {
  return `section_${String(line.segment_index ?? line.section_index ?? 1).replace(/[^A-Za-z0-9_-]/g, '_')}`
}

export default function PreviewTab({ episodeId, onEpisodeChange, onNavigate }) {
  const [episodes, setEpisodes] = useState([])
  const [selectedId, setSelectedId] = useState(episodeId || '')
  const [versions, setVersions] = useState([])
  const [versionId, setVersionId] = useState('')
  const [canonical, setCanonical] = useState(null)
  const [review, setReview] = useState(null)
  const [dirty, setDirty] = useState(false)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')

  const loadPreview = async (id, requestedVersion = '') => {
    if (!id) return
    const versionList = await api.canonicalScripts(id)
    const selected = requestedVersion || versionList.active_version_id
    setVersions(versionList.versions || [])
    if (!selected) {
      setVersionId(''); setCanonical(null); setReview(null); setDirty(false)
      return
    }
    const [source, notes] = await Promise.all([
      api.canonicalScript(id, selected), api.previewReview(id, selected),
    ])
    setVersionId(selected)
    setCanonical(source)
    setReview(notes)
    setDirty(false)
  }

  useEffect(() => {
    let alive = true
    api.listEpisodes().then(async data => {
      if (!alive) return
      const items = Array.isArray(data) ? data : (data.episodes || [])
      setEpisodes(items)
      const id = episodeId || items[0]?.episode_id || items[0]?.id || ''
      setSelectedId(id)
      if (id) {
        onEpisodeChange?.(id)
        try {
          const selected = await api.selectedPreview(id)
          await loadPreview(id, selected?.canonical_version_id || '')
        } catch (error) { if (alive) setMessage(error.message) }
      }
    }).catch(error => setMessage(error.message))
    return () => { alive = false }
  }, [])

  useEffect(() => {
    if (!episodeId || episodeId === selectedId) return
    setSelectedId(episodeId)
    api.selectedPreview(episodeId).then(selected => loadPreview(episodeId, selected?.canonical_version_id || ''))
      .catch(error => setMessage(error.message))
  }, [episodeId])

  const chooseEpisode = async id => {
    setSelectedId(id); onEpisodeChange?.(id); setCanonical(null); setReview(null); setMessage('')
    try {
      const selected = await api.selectedPreview(id)
      await loadPreview(id, selected?.canonical_version_id || '')
    } catch (error) { setMessage(error.message) }
  }
  const chooseVersion = async id => {
    setVersionId(id); setCanonical(null); setReview(null); setMessage('')
    try { await loadPreview(selectedId, id) } catch (error) { setMessage(error.message) }
  }
  const updateLineReview = (lineId, field, value) => {
    setReview(current => ({ ...current, line_reviews: { ...current.line_reviews,
      [lineId]: { ...(current.line_reviews?.[lineId] || { mark: 'none', note: '' }), [field]: value },
    } }))
    setDirty(true)
  }
  const save = async () => {
    if (!review || !selectedId || !canonical) return
    setBusy(true); setMessage('')
    try {
      const saved = await api.savePreview(selectedId, {
        canonical_version_id: versionId, canonical_source_hash: canonical.canonical_hash,
        overall_notes: review.overall_notes || '', line_reviews: review.line_reviews || {},
        section_notes: review.section_notes || {},
      })
      setReview(saved); setDirty(false); setMessage(`Preview saved as ${saved.review_id}`)
    } catch (error) { setMessage(error.message) } finally { setBusy(false) }
  }
  const sendToEditor = async () => {
    if (!review || !canonical) return
    setBusy(true); setMessage('')
    try {
      let saved = review
      if (dirty || !review.saved) {
        saved = await api.savePreview(selectedId, {
          canonical_version_id: versionId, canonical_source_hash: canonical.canonical_hash,
          overall_notes: review.overall_notes || '', line_reviews: review.line_reviews || {},
          section_notes: review.section_notes || {},
        })
        setReview(saved); setDirty(false)
      }
      await api.createProductionDraft(selectedId, versionId)
      onNavigate?.('production-editor')
    } catch (error) { setMessage(error.message) } finally { setBusy(false) }
  }
  const regenerate = async () => {
    if (!selectedId || busy) return
    setBusy(true); setMessage('Script generation started…')
    try {
      await api.generateScript(selectedId)
      const list = await api.canonicalScripts(selectedId)
      await loadPreview(selectedId, list.active_version_id)
      setMessage(`New canonical snapshot ${list.active_version_id} is ready for Preview`)
    } catch (error) { setMessage(`Regenerate failed: ${error.message}`) } finally { setBusy(false) }
  }

  const lines = canonical?.script || []
  const groups = useMemo(() => {
    const result = []
    lines.forEach((line, index) => {
      const key = sectionKey(line, index)
      let group = result.find(item => item.key === key)
      if (!group) { group = { key, title: line.segment_title || `Section ${result.length + 1}`, lines: [] }; result.push(group) }
      group.lines.push({ line, index })
    })
    return result
  }, [lines])
  const episode = episodes.find(item => (item.episode_id || item.id) === selectedId) || {}
  const flags = Object.values(review?.line_reviews || {}).filter(item => item.mark && item.mark !== 'none').length

  return <div className="preview-page" style={{ display: 'grid', gridTemplateColumns: '190px minmax(0,1fr) 250px', height: '100%', minHeight: 0 }}>
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
        <div style={{ flex: 1, minWidth: 170 }}><div style={{ font: '1.56rem var(--font-display)', letterSpacing: '.06em' }}>{episode.title || 'SCRIPT PREVIEW'}</div><div style={label}>Review a frozen canonical snapshot · {review?.saved ? review.review_id : 'Preview not saved'}</div></div>
        <select className="ds-select" value={versionId} onChange={event => chooseVersion(event.target.value)} aria-label="Canonical version">
          {versions.map(item => <option key={item.version_id} value={item.version_id}>{item.version_id} · {item.word_count} words</option>)}
        </select>
        <button className="btn btn-steel" onClick={() => loadPreview(selectedId, versionId)} disabled={!selectedId || busy}><RefreshCw size={10} /> RELOAD</button>
      </header>
      <div style={{ display: 'flex', gap: 7, alignItems: 'center', flexWrap: 'wrap', padding: '8px 12px', borderBottom: '1px solid var(--rim)' }}>
        <span style={{ ...label, color: 'var(--green)' }}>1 GENERATE · CANONICAL READY</span><span>→</span><span style={{ ...label, color: 'var(--gold)' }}>2 PREVIEW · {dirty ? 'UNSAVED' : review?.saved ? 'SAVED REVIEW' : 'REVIEW'}</span><span>→</span><span style={label}>3 PRODUCTION EDITOR</span><span>→</span><span style={label}>4 PRODUCE</span>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 6 }}>
          <button className="btn btn-steel" onClick={regenerate} disabled={!selectedId || busy}><Sparkles size={10} /> REGENERATE</button>
          <button className="btn btn-steel" onClick={save} disabled={!review || !dirty || busy}><Save size={10} /> SAVE PREVIEW</button>
          <button className="btn btn-solid" onClick={sendToEditor} disabled={!review || busy}><ArrowRight size={10} /> SEND TO PRODUCTION EDITOR</button>
        </div>
      </div>
      {message && <div role="status" style={{ padding: '6px 12px', color: message.toLowerCase().includes('failed') ? 'var(--red)' : 'var(--gold)', fontSize: '0.88rem' }}>{message}</div>}
      <div style={{ flex: 1, overflow: 'auto', padding: 12 }}>
        {!lines.length && <div style={{ ...panel, color: 'var(--steel)' }}>No canonical script exists for this episode yet. Generate a script, then review its saved snapshot here.</div>}
        {groups.map(group => <section key={group.key} style={{ ...panel, marginBottom: 10 }}>
          <header style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}><span style={label}>{group.title} · {group.lines.length} lines</span><input value={review?.section_notes?.[group.key] || ''} onChange={event => { setReview(current => ({ ...current, section_notes: { ...(current.section_notes || {}), [group.key]: event.target.value } })); setDirty(true) }} placeholder="Section note: pacing, structure, transition…" style={{ flex: 1, background: 'var(--bg)', color: 'var(--bone)', border: '1px solid var(--rim)', borderRadius: 4, padding: '6px 8px', fontSize: '0.88rem' }} /></header>
          {group.lines.map(({ line, index }) => {
            const item = review?.line_reviews?.[line.canonical_line_id] || { mark: 'none', note: '' }
            return <div key={line.canonical_line_id || index} style={{ display: 'grid', gridTemplateColumns: '34px 64px minmax(0,1fr) 155px 190px', gap: 7, alignItems: 'start', padding: '7px 4px', borderTop: '1px solid var(--rim)' }}>
              <span style={label}>#{index + 1}</span><b style={{ fontSize: '0.81rem', color: String(line.speaker).toLowerCase() === 'jim' ? 'var(--blue)' : 'var(--gold)' }}>{(line.speaker || 'PHIL').toUpperCase()}</b>
              <div style={{ fontSize: '0.94rem', lineHeight: 1.5, whiteSpace: 'pre-wrap' }}>{line.text}</div>
              <select className="ds-select" value={item.mark || 'none'} onChange={event => { setReview(current => ({ ...current, line_reviews: { ...current.line_reviews, [line.canonical_line_id]: { ...item, mark: event.target.value } } })); setDirty(true) }} aria-label={`Preview mark line ${index + 1}`}>
                {marks.map(([value, title]) => <option key={value} value={value}>{title}</option>)}
              </select>
              <textarea className="ds-textarea" rows={2} value={item.note || ''} onChange={event => updateLineReview(line.canonical_line_id, 'note', event.target.value)} placeholder="Line comment" aria-label={`Review note line ${index + 1}`} />
            </div>
          })}
        </section>)}
        {lines.length > 0 && <section style={panel}>
          <div style={{ ...label, marginBottom: 6 }}>OVERALL SCRIPT NOTES · TONE / PACING / STRUCTURE</div>
          <textarea className="ds-textarea" rows={4} value={review?.overall_notes || ''} onChange={event => { setReview(current => ({ ...current, overall_notes: event.target.value })); setDirty(true) }} placeholder="What should the Production Editor know about this script as a whole?" />
        </section>}
      </div>
      <footer style={{ borderTop: '1px solid var(--rim)', padding: '8px 12px', display: 'flex', gap: 18, flexWrap: 'wrap', ...label }}>
        <span>CANONICAL {versionId || '—'} · {canonical?.canonical_hash?.slice(0, 12) || '—'}</span><span>PREVIEW {review?.review_id || 'UNSAVED'}</span><span>FLAGS {flags}</span><span>NOTES {Object.values(review?.line_reviews || {}).filter(item => item.note).length + (review?.overall_notes ? 1 : 0)}</span>
      </footer>
    </main>
    <aside style={{ borderLeft: '1px solid var(--rim)', padding: 10, overflow: 'auto' }}>
      <div style={{ ...label, marginBottom: 8 }}>SCRIPT INFO</div>
      <div style={panel}><div style={{ fontSize: '0.88rem', lineHeight: 1.9 }}>Canonical: {versionId || '—'}<br />Lines: {lines.length}<br />Words: {canonical?.word_count || 0}<br />Marked lines: {flags}<br />Review: {review?.saved ? 'Saved' : 'Unsaved'}</div></div>
      <div style={{ ...panel, marginTop: 10 }}><div style={label}>REVIEW MARKS</div>{marks.slice(1).map(([mark, title]) => <div key={mark} style={{ padding: '6px 0', fontSize: '0.88rem' }}>{title}: {Object.values(review?.line_reviews || {}).filter(item => item.mark === mark).length}</div>)}</div>
      <div style={{ ...panel, marginTop: 10, color: 'var(--steel)', fontSize: '0.85rem', lineHeight: 1.5 }}><AlertTriangle size={12} color="var(--gold)" /> Preview notes and flags are saved against the canonical hash and carried into the Production Editor draft. They do not alter canonical dialogue.</div>
    </aside>
  </div>
}
