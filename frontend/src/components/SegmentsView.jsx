import { useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'

const STATUS = { planned: 'PLANNED', generating: 'GENERATING', draft_ready: 'DRAFT READY', approved: 'APPROVED', stale: 'STALE' }
const SLOT = { pre_roll_1: 'PRE 1', pre_roll_2: 'PRE 2', mid_roll_1: 'MID 1', mid_roll_2: 'MID 2', mid_roll_3: 'MID 3', mid_roll_4: 'MID 4', post_roll_1: 'POST' }
const ROLES = [['episode_requirement', 'Episode requirement'], ['editorial_requirement', 'Editorial requirement'], ['episode_metadata', 'Episode metadata']]

function clock(seconds) {
  if (seconds == null) return '—'
  const minutes = Math.floor(seconds / 60)
  return `${minutes}:${(seconds - minutes * 60).toFixed(1).padStart(4, '0')}`
}

function editable(plan) {
  return plan ? JSON.parse(JSON.stringify({ segments: plan.segments, episode_requirements: plan.episode_requirements })) : null
}

export default function SegmentsView({ episodeId, generationRunning, onAssembled }) {
  const [data, setData] = useState(null)
  const [edit, setEdit] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [preview, setPreview] = useState(null)
  const dirty = useRef(false)

  async function refresh() {
    const next = await api.segments(episodeId)
    setData(next)
    if (!dirty.current) setEdit(editable(next.plan))
    return next
  }

  useEffect(() => {
    let live = true
    dirty.current = false
    setData(null); setEdit(null); setPreview(null)
    const tick = () => api.segments(episodeId).then(next => {
      if (!live) return
      setData(next)
      if (!dirty.current) setEdit(editable(next.plan))
    }).catch(() => { /* backend briefly offline: keep the current view */ })
    tick()
    const timer = setInterval(tick, 3000)
    return () => { live = false; clearInterval(timer) }
  }, [episodeId])

  async function act(work) {
    setBusy(true); setError(''); setNotice('')
    try { await work() } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  if (!data) return <p>Loading segments…</p>
  const plan = data.plan
  const locked = Boolean(plan?.locked)
  const revision = plan?.plan_revision || null
  const settings = data.settings || {}
  const points = plan?.points || []
  const runtime = data.runtime
  const blocked = busy || generationRunning
  const change = updater => { dirty.current = true; setEdit(current => updater(JSON.parse(JSON.stringify(current)))) }
  const segmentOf = id => edit?.segments.find(s => s.point_ids.includes(id))?.index

  async function savePlan() {
    const saved = await api.saveSegmentPlan(episodeId, edit, revision)
    dirty.current = false
    await refresh()
    return saved
  }

  const written = data.segments.reduce((sum, s) => sum + ((s.latest_draft?.word_count) || 0), 0)
  const strip = [['THEME'], ...data.ad_layout.flatMap((group, index) => [
    ...group.slots.map(slot => [SLOT[slot.slot_id], slot]),
    ...(index < 3 ? [[`SEGMENT ${index + 1}`]] : []),
  ]), ['THEME']]

  return <div className="segments-view" aria-label="Segments">
    <section className="segment-episode" aria-label="Episode overview">
      <h3>Episode · three segments</h3>
      {runtime ? <p role="status">
        Runtime <strong>{clock(runtime.runtime_seconds)}</strong> · Talk {clock(runtime.talk_seconds)} ({runtime.segments.map(s => `${s.talk_minutes}:00`).join(' + ')})
        · Ads {clock(runtime.advertising_seconds)} ({data.ad_layout.flatMap(g => g.slots).filter(s => s.status === 'assigned').length} of 7 assigned, others held at 30 s)
        · Theme {clock(runtime.theme_seconds)} · Words {written.toLocaleString()} drafted / {runtime.target_words.toLocaleString()} target
      </p> : <p>No segment plan yet.</p>}
      <div className="segment-strip" aria-label="Running order">
        {strip.map(([label, slot], index) => <span key={index} className={slot ? `slot slot-${slot.status}` : label.startsWith('SEG') ? 'seg' : 'theme'}
          title={slot ? (slot.status === 'assigned' ? `${slot.assigned_ad_id} · ${slot.duration_seconds}s` : 'Reserved, unassigned') : undefined}>{label}</span>)}
      </div>
      <p style={{ fontSize: '.85rem' }}>Ads play only before, between and after segments, never inside one. {plan ? `Plan ${revision} · ${locked ? 'LOCKED' : 'editable'} · from ${plan.context_version_id}${plan.proposed_by === 'nemotron' ? ' · proposed by Nemotron' : ''}` : ''}</p>
      {data.plan_stale && <p role="alert">The saved context changed after this plan was made. Start a new plan from the current context before writing.</p>}
      <div className="gap-row" style={{ flexWrap: 'wrap' }}>
        <button className="btn btn-steel" disabled={blocked || locked} onClick={() => act(async () => {
          if (plan && !window.confirm('Start a new empty plan? The current plan stays in revision history.')) return
          await api.newSegmentPlan(episodeId, revision); dirty.current = false; await refresh(); setNotice('New plan started from the current context.')
        })}>NEW EMPTY PLAN</button>
        <button className="btn btn-steel" disabled={blocked || locked} onClick={() => act(async () => {
          if (!window.confirm('Send one short request to Nemotron to propose a three-segment plan? It replaces the editable plan; earlier revisions stay in history.')) return
          await api.proposeSegmentPlan(episodeId, revision); dirty.current = false; await refresh(); setNotice('Proposal saved as an editable plan. Review every field before locking.')
        })}>PROPOSE PLAN (NEMOTRON)</button>
        <button className="btn btn-steel" disabled={blocked || locked || !plan || !dirty.current} onClick={() => act(async () => { await savePlan(); setNotice('Plan saved.') })}>SAVE PLAN</button>
        {!locked ? <button className="btn btn-gold" disabled={blocked || !plan} onClick={() => act(async () => {
          const current = dirty.current ? await savePlan() : plan
          await api.lockSegmentPlan(episodeId, current.plan_revision); await refresh(); setNotice('Plan locked. Segment 1 can be written.')
        })}>LOCK PLAN</button>
          : <button className="btn btn-steel" disabled={blocked} onClick={() => act(async () => {
            await api.unlockSegmentPlan(episodeId, revision); await refresh(); setNotice('Plan unlocked for editing. Approved segments become stale if their part of the plan changes.')
          })}>UNLOCK PLAN</button>}
        <button className="btn btn-solid" disabled={blocked || !data.can_assemble} onClick={() => act(async () => { setPreview(await api.assemblyPreview(episodeId)) })}>ASSEMBLY PREVIEW</button>
      </div>
      {plan && !locked && data.plan_issues.length > 0 && <details open><summary>Before locking ({data.plan_issues.length})</summary><ul>{data.plan_issues.map((issue, i) => <li key={i}>{issue}</li>)}</ul></details>}
      {plan && data.plan_notes?.length > 0 && <ul aria-label="Plan notes">{data.plan_notes.map((note, i) => <li key={i} style={{ fontSize: '.85rem' }}>{note}</li>)}</ul>}
      {edit?.episode_requirements.length > 0 && <fieldset disabled={blocked || locked} style={{ border: '1px solid var(--rim)', display: 'grid', gap: 6 }}>
        <legend>Episode-wide requirements (from Must include; apply to every segment)</legend>
        {edit.episode_requirements.map((item, i) => <div key={item.id} style={{ display: 'grid', gap: 4 }}>
          <span style={{ overflowWrap: 'anywhere' }}>{item.text}</span>
          <div className="gap-row" style={{ flexWrap: 'wrap' }}>
            <select className="ds-select" aria-label={`Role of requirement ${i + 1}`} value={item.role} onChange={e => change(d => { d.episode_requirements[i].role = e.target.value; return d })}>{ROLES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
            <select className="ds-select" aria-label={`Primary segment for requirement ${i + 1}`} value={item.primary_segment ?? ''} onChange={e => change(d => { d.episode_requirements[i].primary_segment = e.target.value ? Number(e.target.value) : null; return d })}>
              <option value="">No primary segment</option>{[1, 2, 3].map(n => <option key={n} value={n}>Primarily segment {n}</option>)}
            </select>
          </div>
        </div>)}
      </fieldset>}
      {notice && <p role="status">{notice}</p>}
      {error && <p role="alert" style={{ color: 'var(--gold)', whiteSpace: 'pre-wrap' }}>{error}</p>}
    </section>

    {edit && <div className="segment-cards">
      {data.segments.map((segment, i) => {
        const draft = segment.latest_draft
        const fields = edit.segments[i]
        const approvedCurrent = segment.approved && draft && segment.approved.draft_id === draft.draft_id
        return <article key={segment.index} className="segment-card" aria-label={`Segment ${segment.index}`}>
          <h4>SEGMENT {segment.index}{segment.index === 1 ? ' · OPENS' : segment.index === 3 ? ' · CLOSES' : ''} <span className={`segment-status status-${segment.status}`}>{STATUS[segment.status]}</span></h4>
          <fieldset disabled={blocked || locked} style={{ border: 0, padding: 0, display: 'grid', gap: 6 }}>
            <label>Title<input className="ds-input" style={{ width: '100%' }} value={fields.title} onChange={e => change(d => { d.segments[i].title = e.target.value; return d })} /></label>
            <label>Topic focus<textarea className="ds-input" rows={2} style={{ width: '100%' }} value={fields.focus} onChange={e => change(d => { d.segments[i].focus = e.target.value; return d })} /></label>
            <div>Beats ({fields.beats.length}, use 4–8)
              {fields.beats.map((beat, b) => <div key={b} className="gap-row">
                <input className="ds-input" style={{ flex: 1 }} aria-label={`Segment ${segment.index} beat ${b + 1}`} value={beat} onChange={e => change(d => { d.segments[i].beats[b] = e.target.value; return d })} />
                <button className="btn btn-steel btn-sm" aria-label={`Remove beat ${b + 1}`} onClick={() => change(d => { d.segments[i].beats.splice(b, 1); return d })}>✕</button>
              </div>)}
              {fields.beats.length < 8 && <button className="btn btn-steel btn-sm" onClick={() => change(d => { d.segments[i].beats.push(''); return d })}>+ BEAT</button>}
            </div>
            <div>Must-include points
              {points.map(point => <label key={point.id} style={{ display: 'block', overflowWrap: 'anywhere' }}>
                <input type="checkbox" checked={fields.point_ids.includes(point.id)} onChange={e => change(d => {
                  d.segments.forEach(s => { s.point_ids = s.point_ids.filter(id => id !== point.id) })
                  if (e.target.checked) d.segments[i].point_ids.push(point.id)
                  return d
                })} /> {point.text}{segmentOf(point.id) && segmentOf(point.id) !== segment.index ? ` (segment ${segmentOf(point.id)})` : ''}
              </label>)}
            </div>
            <label>Talk length <select className="ds-select" value={fields.talk_minutes} onChange={e => change(d => { d.segments[i].talk_minutes = Number(e.target.value); return d })}>
              {Array.from({ length: (settings.max_talk_minutes || 12) - (settings.min_talk_minutes || 10) + 1 }, (_, k) => (settings.min_talk_minutes || 10) + k).map(m => <option key={m} value={m}>{m} min</option>)}
            </select> · target {segment.plan.target_words.toLocaleString()} words</label>
          </fieldset>
          {segment.stale_reasons.map((reason, k) => <p key={k} role="alert" style={{ fontSize: '.85rem' }}>{reason}</p>)}
          {segment.status === 'generating' && segment.progress && <p role="status">Writing pass {segment.progress.pass || '…'} of {segment.progress.passes || '…'} · {segment.progress.words_so_far ?? 0} of ~{segment.progress.target_words ?? segment.plan.target_words} words</p>}
          {!segment.can_generate && <p style={{ fontSize: '.85rem' }}>{segment.generate_blocked_reason}</p>}
          <div className="gap-row" style={{ flexWrap: 'wrap' }}>
            <button className="btn btn-solid" disabled={blocked || !segment.can_generate || dirty.current} onClick={() => act(async () => {
              const result = await api.generateSegment(episodeId, segment.index); await refresh()
              setNotice(`Segment ${segment.index} draft saved: ${result.word_count.toLocaleString()} words. Other segments are unchanged.`)
            })}>{draft ? 'REGENERATE' : 'GENERATE'}</button>
            <button className="btn btn-gold" disabled={blocked || !draft || approvedCurrent} onClick={() => act(async () => {
              await api.approveSegmentDraft(episodeId, segment.index, draft.draft_id); await refresh(); setNotice(`Segment ${segment.index} approved.`)
            })}>{approvedCurrent ? 'APPROVED' : 'APPROVE'}</button>
          </div>
          {draft && <section aria-label={`Segment ${segment.index} draft`}>
            <p style={{ fontSize: '.85rem' }}>Draft {segment.draft_count} · {draft.word_count.toLocaleString()} / {draft.target_words.toLocaleString()} words · {draft.script.length} turns · {draft.passes.length} passes{segment.approved && !approvedCurrent ? ` · approved: ${segment.approved.draft_id.slice(0, 16)}…` : ''}</p>
            {draft.review_warnings.length > 0 && <details><summary>Review notes ({draft.review_warnings.length}, informational)</summary>
              <ul>{draft.review_warnings.map(w => <li key={w.id} style={{ fontSize: '.85rem' }}>Line {w.line}{w.end_line && w.end_line !== w.line ? `–${w.end_line}` : ''}: {w.detail}</li>)}</ul>
            </details>}
            <pre className="context-reference-text segment-draft">{draft.script.map((line, n) => `${n + 1}. ${line.speaker.toUpperCase()}: ${line.text}`).join('\n')}</pre>
          </section>}
        </article>
      })}
    </div>}

    {preview && <section className="segment-episode" aria-label="Assembly preview">
      <h3>Assembly preview · nothing saved yet</h3>
      <p>{preview.segments.map(s => `Segment ${s.segment_index}: ${s.word_count.toLocaleString()} words, ${s.turns} turns`).join(' · ')}</p>
      <p role="status">Estimated runtime {clock(preview.runtime.runtime_seconds)} = talk {clock(preview.runtime.talk_seconds)} + ads {clock(preview.runtime.advertising_seconds)} + theme {clock(preview.runtime.theme_seconds)}. Final length is measured from audio after production.</p>
      {preview.review_warnings.length > 0 && <p>{preview.review_warnings.length} informational review notes across segments.</p>}
      <details><summary>Full assembled script ({preview.script.length} lines)</summary>
        <pre className="context-reference-text segment-draft">{preview.script.map(line => `${line.line_number}. [S${line.episode_segment}] ${line.speaker.toUpperCase()}: ${line.text}`).join('\n')}</pre>
      </details>
      <div className="gap-row">
        <button className="btn btn-gold" disabled={blocked} onClick={() => act(async () => {
          if (!window.confirm('Assemble the episode? This saves the previewed script as the active canonical script. The current script stays in version history.')) return
          const result = await api.assembleEpisode(episodeId, preview.preview_sha256)
          setPreview(null); await refresh()
          setNotice(`Assembled as ${result.canonical_version_id}. Review it in Preview and Production Editor before audio production.`)
          onAssembled?.()
        })}>ASSEMBLE EPISODE</button>
        <button className="btn btn-steel" onClick={() => setPreview(null)}>CLOSE PREVIEW</button>
      </div>
    </section>}
  </div>
}
