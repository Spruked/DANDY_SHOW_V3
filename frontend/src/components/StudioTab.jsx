import { useCallback, useEffect, useState } from 'react'
import { Activity, Camera, Circle, Monitor, Radio, RefreshCw, Square } from 'lucide-react'

const request = async (path, options = {}) => {
  const response = await fetch(`/api/obs${path}`, { headers: { 'Content-Type': 'application/json' }, ...options })
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}))
    throw new Error(payload.detail || `HTTP ${response.status}`)
  }
  return response.json()
}

export default function StudioTab() {
  const [obs, setObs] = useState({ connected: false, recording: false, streaming: false, active_scene: '', scenes: [] })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const obsRequest = useCallback((path, options) => request(path, options), [])

  const refresh = useCallback(async () => {
    setBusy(true)
    try {
      const [status, sceneData] = await Promise.all([obsRequest('/status'), obsRequest('/scenes')])
      setObs({ ...status, scenes: sceneData.scenes || [], active_scene: sceneData.active_scene || status.active_scene || '' })
      setError('')
    } catch (err) {
      setObs(current => ({ ...current, connected: false }))
      setError(err.message)
    } finally { setBusy(false) }
  }, [obsRequest])

  useEffect(() => { void refresh() }, [refresh])
  const invoke = async (path, options) => {
    setBusy(true)
    try { await obsRequest(path, options); await refresh() }
    catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }

  return <div className="tab-body" style={{ overflow: 'auto' }}><div className="pane-main">
    <div className="section-head"><span className="section-label">Studio / OBS</span>
      <button className="icon-btn" onClick={() => void refresh()} disabled={busy} title="Refresh OBS"><RefreshCw size={12} /></button>
    </div>
    <div className="sys-grid">
      <div className="sys-card" style={{ gridColumn: '1 / -1' }}><div className="sys-card-title">OBS Control</div>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
          <span className="font-mono" style={{ color: obs.connected ? 'var(--green)' : 'var(--red)' }}>{obs.connected ? 'OBS CONNECTED' : 'OBS OFFLINE'}</span>
          <button className="ds-btn" disabled={busy || !obs.connected} onClick={() => void invoke('/stream/toggle', { method: 'POST' })}><Radio size={12} /> {obs.streaming ? 'END STREAM' : 'GO LIVE'}</button>
          <button className="ds-btn" disabled={busy || !obs.connected} onClick={() => void invoke('/record/toggle', { method: 'POST' })}>{obs.recording ? <Square size={12} /> : <Circle size={12} />} {obs.recording ? 'STOP RECORD' : 'RECORD'}</button>
        </div>{error && <div className="font-mono" style={{ color: 'var(--red)', fontSize: '.55rem', marginTop: 10 }}>{error}</div>}
      </div>
      <div className="sys-card"><div className="sys-card-title"><Monitor size={13} /> Scene Switcher</div><div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: 6 }}>
        {obs.scenes.map(scene => <button key={scene} className="ds-btn" disabled={busy || !obs.connected} onClick={() => void invoke('/scene', { method: 'POST', body: JSON.stringify({ scene_name: scene }) })}>{scene === obs.active_scene ? 'ON AIR: ' : ''}{scene}</button>)}
      </div></div>
      <div className="sys-card"><div className="sys-card-title"><Activity size={13} /> Audio Routing</div><p className="font-mono" style={{ fontSize: '.58rem', color: 'var(--steel)', lineHeight: 1.6 }}>Dandy renders audio directly; use OBS-native sources for live routing.</p></div>
      <div className="sys-card"><div className="sys-card-title"><Camera size={13} /> Camera Control</div><p className="font-mono" style={{ fontSize: '.58rem', color: 'var(--steel)' }}>Camera controls remain OBS-scene based.</p></div>
    </div>
  </div></div>
}
