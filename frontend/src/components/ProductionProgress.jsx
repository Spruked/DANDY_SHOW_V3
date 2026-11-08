import { useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'

const ACTIVE = new Set(['queued', 'producing', 'cancellation_requested'])
const FINISHED = new Set(['produced', 'failed', 'cancelled', 'interrupted'])

export default function ProductionProgress({ onOpenEpisode }) {
  const [runs, setRuns] = useState([])
  const tracked = useRef(new Map())

  useEffect(() => {
    let mounted = true, polling = false
    const poll = async () => {
      if (polling) return
      polling = true
      try {
        const data = await api.listEpisodes()
        if (!mounted) return
        const episodes = Array.isArray(data) ? data : (data.episodes || [])
        for (const episode of episodes) {
          if (ACTIVE.has(episode.status)) {
            const id = episode.episode_id || episode.id
            tracked.current.set(id, { ...tracked.current.get(id), episode_id: id, status: episode.status, title: episode.title || id })
          }
        }
        const updates = await Promise.all([...tracked.current.values()].map(async run => {
          try {
            const status = await api.produceStatus(run.episode_id)
            return { ...run, ...status, error: status.error || null, stale: false }
          } catch {
            return { ...run, stale: true }
          }
        }))
        if (!mounted) return
        const visible = updates.filter(run => tracked.current.has(run.episode_id) && (ACTIVE.has(run.status) || FINISHED.has(run.status) || run.stale))
        tracked.current = new Map(visible.map(run => [run.episode_id, run]))
        setRuns(visible)
      } catch {
        if (mounted) setRuns(previous => previous.map(run => ({ ...run, stale: true })))
      } finally { polling = false }
    }
    poll()
    const timer = setInterval(poll, 2500)
    window.addEventListener('focus', poll)
    return () => { mounted = false; clearInterval(timer); window.removeEventListener('focus', poll) }
  }, [])

  return runs.length ? <section className="production-progress-tray" aria-label="Studio production jobs">
    {runs.map(run => {
      const progress = Math.max(0, Math.min(1, Number(run.progress) || 0))
      const knownProgress = Number.isFinite(Number(run.progress))
      const title = run.title || run.episode_id
      return <div key={run.episode_id} className="production-progress-run">
        <div className="production-progress-heading">
          <strong>{title}</strong>
          <span>{run.status === 'produced' ? 'Completed' : run.stage || run.status} · {knownProgress ? `${Math.round(progress * 100)}% overall` : 'awaiting saved progress'}</span>
          {run.line_number && <span>Line {run.line_number}/{run.total_lines}</span>}
          {run.chunk_count > 1 && <span>Chunk {run.chunk_number}/{run.chunk_count}</span>}
          {run.engine && <span>{run.engine.toUpperCase()}</span>}
          <button className="btn btn-steel btn-sm" onClick={() => onOpenEpisode(run.episode_id)}>VIEW EPISODE</button>
          {FINISHED.has(run.status) && <button className="btn btn-steel btn-sm" onClick={() => {
            tracked.current.delete(run.episode_id)
            setRuns(previous => previous.filter(item => item.episode_id !== run.episode_id))
          }}>DISMISS</button>}
        </div>
        <progress max="1" value={knownProgress ? progress : undefined} aria-label={`Production progress for ${title}`} />
        {run.stale && <div role="status">Connection unavailable — showing the last saved progress.</div>}
        {run.error && <div role="status">{run.error}</div>}
      </div>
    })}
  </section> : null
}
