import { useState, useEffect, useRef } from 'react'
import { RefreshCw, Play, Save } from 'lucide-react'
import { api, req } from '../lib/api'
import { Badge, Spinner, Toast, Field } from './ui'
import { useToast } from '../hooks/useToast'
import AudioAssetPicker from './AudioAssetPicker'

const CHECK_NAMES = {
  writer: 'Writer / Loaded Model', kokoro: 'Kokoro WSL Runtime', qwen_bridge: 'Qwen TTS Bridge',
  qwen_custom_voice: 'Qwen CustomVoice Service', qwen_operator_ui: 'Qwen Operator UI',
  gpu: 'GPU / VRAM', resources: 'CPU / RAM / Backend Process', media_tools: 'Media Tools',
  storage: 'Storage / Required Assets', production: 'Production / Generation Records',
  obs: 'OBS / Streaming / Recording', mixer: 'Voicemeeter',
}
const bytes = value => typeof value === 'number' ? ((value / 1024 ** 3).toFixed(2) + ' GiB') : 'unverified'
const clock = value => value ? new Date(value).toLocaleTimeString() : 'not checked'
function probeWebSocket() {
  return new Promise(resolve => {
    const started = performance.now()
    const url = (location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws/system-monitor-' + crypto.randomUUID()
    const socket = new WebSocket(url), token = crypto.randomUUID()
    let done = false
    const finish = (status, error) => {
      if (done) return
      done = true; clearTimeout(timer); socket.close()
      resolve({ status, url, error, checked_at: new Date().toISOString(), latency_ms: Math.round(performance.now() - started), source: 'browser handshake + matching echo; not production progress' })
    }
    const timer = setTimeout(() => finish('unavailable', 'No matching echo within 4 seconds'), 4000)
    socket.onopen = () => socket.send(token)
    socket.onmessage = event => {
      try { const data = JSON.parse(event.data); if (data.type === 'echo' && data.text === token) finish('ready') } catch { /* Ignore unrelated messages. */ }
    }
    socket.onerror = () => finish('unavailable', 'WebSocket connection failed')
    socket.onclose = () => { if (!done) finish('unavailable', 'Connection closed before echo') }
  })
}
function Summary({ name, check }) {
  const data = check.data || {}
  if (name === 'writer') return <><div>{data.model || 'No loaded model verified'}</div><div>{data.llamacpp_url}</div><div>Inference: {check.inference || 'unverified'}</div></>
  if (name === 'gpu') return data.devices?.map(d => <div key={d.index}>{d.name}<br />VRAM {d.memory_used_mib} / {d.memory_total_mib} MiB · GPU {d.utilization_percent}% · {d.temperature_c} °C</div>)
  if (name === 'resources') return <><div>CPU {data.cpu_percent ?? 'unverified'}% · RAM {data.ram_used_percent ?? 'unverified'}%</div><div>Available RAM: {bytes(data.ram_available_bytes)}</div><div>Backend PID {data.backend_pid} · RSS {bytes(data.backend_rss_bytes)}</div></>
  if (name === 'storage') return <><div>Free disk: {bytes(data.disk_free_bytes)}</div><div>Intro/outro music: {data.music_exists ? 'present' : 'MISSING'}</div><div>Brand images: {data.brand_assets?.filter(a => a.available).length ?? 0} / {data.brand_assets?.length ?? 0} present</div></>
  if (name === 'obs') return <><div>Scene: {data.scene_name || 'unverified'}</div><div>Streaming: {String(data.streaming)} · Recording: {String(data.recording)}</div><div>{check.cameras}</div></>
  if (name === 'kokoro') return <><div>Device: {data.device || 'unverified'}</div><div>CUDA available: {String(data.cuda_available ?? 'unverified')}</div><div>Synthesis: {check.synthesis || 'unverified'}</div></>
  if (name === 'media_tools') return Object.entries(data).map(([tool, value]) => <div key={tool}>{tool}: {value.status}<div>{value.path}</div></div>)
  if (name === 'production') return <><div>{data.episodes?.length ?? 0} production records · {data.jobs?.length ?? 0} recent jobs</div><div>Live progress: {data.progress_telemetry}</div></>
  return <div>{check.url || 'See measured details below'}</div>
}
export default function SystemTab() {
  const { toast, showToast } = useToast()
  const [diagnostics, setDiagnostics] = useState(null), [network, setNetwork] = useState(null)
  const [checking, setChecking] = useState(false), [error, setError] = useState('')
  const [selectedTts, setSelectedTts] = useState(''), [savingTts, setSavingTts] = useState(false)
  const [ioCfg, setIoCfg] = useState(null), [ioLoading, setIoLoading] = useState(false), [ioSaving, setIoSaving] = useState(false)
  const [ioPreviewing, setIoPreviewing] = useState(null), [ioPreviewUrl, setIoPreviewUrl] = useState(null)
  const [tick, setTick] = useState(Date.now())
  const inFlight = useRef(false), mounted = useRef(true), controller = useRef(null), previewRef = useRef(null)
  const loadIoConfig = async () => {
    setIoLoading(true)
    try { const cfg = await api.getIntroOutroConfig(); if (mounted.current) setIoCfg(cfg) }
    catch (e) { if (mounted.current) showToast('Intro/outro load failed: ' + e.message) }
    finally { if (mounted.current) setIoLoading(false) }
  }
  const checkHealth = async () => {
    if (inFlight.current) return
    inFlight.current = true; setChecking(true)
    const activeController = new AbortController()
    controller.current = activeController
    const timeout = setTimeout(() => activeController.abort(), 20000)
    try {
      const [data, ws] = await Promise.all([req('/system/diagnostics', { signal: activeController.signal }), probeWebSocket()])
      if (mounted.current) { setDiagnostics(data); setNetwork(ws); setSelectedTts(data.selected_tts); setError('') }
    } catch (e) { if (mounted.current) setError(e.name === 'AbortError' ? 'Diagnostic timeout; previous readings are stale.' : e.message) }
    finally { clearTimeout(timeout); inFlight.current = false; if (mounted.current) setChecking(false) }
  }
  useEffect(() => {
    mounted.current = true; checkHealth(); loadIoConfig()
    req('/tts-engine').then(data => { if (mounted.current) setSelectedTts(data.selected_engine) }).catch(() => {})
    const interval = setInterval(() => { setTick(Date.now()); if (!document.hidden) checkHealth() }, 15000)
    return () => { mounted.current = false; clearInterval(interval); controller.current?.abort(); if (previewRef.current) URL.revokeObjectURL(previewRef.current) }
  }, [])
  const setProductionTts = async engine => {
    setSavingTts(true)
    try { await req('/tts-engine', { method: 'POST', body: JSON.stringify({ engine }) }); setSelectedTts(engine); showToast('Production TTS: ' + engine); await checkHealth() }
    catch (e) { showToast('TTS selection failed: ' + e.message) }
    finally { setSavingTts(false) }
  }
  const setIo = (path, value) => setIoCfg(prev => {
    const next = structuredClone(prev), keys = path.split('.')
    let object = next
    keys.slice(0, -1).forEach(key => { object = object[key] })
    object[keys.at(-1)] = value
    return next
  })
  const saveIoConfig = async () => {
    setIoSaving(true)
    try { await api.saveIntroOutroConfig(ioCfg); showToast('Intro/outro configuration saved') }
    catch (e) { showToast('Save failed: ' + e.message) }
    finally { setIoSaving(false) }
  }
  const previewSection = async section => {
    setIoPreviewing(section)
    if (previewRef.current) URL.revokeObjectURL(previewRef.current)
    setIoPreviewUrl(null)
    try { const url = await api.previewIntroOutro(section); previewRef.current = url; setIoPreviewUrl(url) }
    catch (e) { showToast('Preview failed: ' + e.message) }
    finally { setIoPreviewing(null) }
  }
  const stale = !!error || (diagnostics && tick - new Date(diagnostics.checked_at).getTime() > 45000)
  const voiceKeys = Object.keys(diagnostics?.voice_registry || {})
  return <div className="tab-body"><div className="pane-main" style={{ overflow: 'auto' }}>
    <div className="section-head"><span className="section-label">System Status · Live Checks</span><button className="btn btn-steel btn-sm" onClick={checkHealth} disabled={checking}><RefreshCw size={12} />{checking ? 'CHECKING' : 'REFRESH'}</button></div>
    <div style={{ padding: '8px 16px', fontSize: '.75rem' }} role="status">
      <Badge type={stale || diagnostics?.status !== 'ready' ? 'steel' : 'green'}>{stale ? 'STALE / CHECK FAILED' : diagnostics?.status || 'not checked'}</Badge>
      {' '}Last response: {clock(diagnostics?.checked_at)} · refresh every 15 seconds while visible · WSL cache 60 seconds
      {error && <div style={{ color: 'var(--red)' }}>{error}</div>}
      <div>Reachable = service answered. Ready = named dependency check passed. Neither proves completed synthesis, inference, or camera frames.</div>
    </div>
    <div className="sys-grid">
      <div className="sys-card"><div className="sys-card-title">Frontend / API Proxy / WebSocket</div>
        <div>Frontend: {location.origin} (this loaded page)</div><div>API proxy: {diagnostics ? 'response verified' : 'unverified'}{stale ? ' — stale' : ''}</div>
        <div>WebSocket: {network?.status || 'unverified'} · {network?.latency_ms ?? '—'} ms</div>
        <div style={{ overflowWrap: 'anywhere' }}>{network?.url}</div><div>{network?.error || network?.source}</div>
      </div>
      <div className="sys-card"><div className="sys-card-title">Production TTS / No Provider Fallback</div>
        <Field label="Selected production engine"><select className="ds-select" value={selectedTts} disabled={!selectedTts || savingTts} onChange={e => setProductionTts(e.target.value)}><option value="" disabled>Not checked</option><option value="kokoro">Kokoro · WSL runtime</option><option value="qwen">Qwen · local bridge</option></select></Field>
        <div>Selected: {selectedTts || 'unverified'} · Fallback: NONE</div>
        <details><summary>Configured voice identities ({voiceKeys.length})</summary>{voiceKeys.map(key => <div key={key}>{key}: {diagnostics.voice_registry[key].primary_voice} · Qwen: {diagnostics.qwen_voice_registry[key] || 'not configured'}</div>)}</details>
      </div>
      {Object.entries(diagnostics?.checks || {}).map(([name, check]) => <div className="sys-card" key={name} style={{ minWidth: 0 }}>
        <div className="sys-card-title">{CHECK_NAMES[name] || name} <Badge type={stale ? 'steel' : check.status === 'ready' ? 'green' : check.status === 'reachable' ? 'gold' : 'steel'}>{stale ? 'stale (' + check.status + ')' : check.status}</Badge></div>
        <div style={{ fontSize: '.75rem', lineHeight: 1.7, overflowWrap: 'anywhere' }}><Summary name={name} check={check} />{check.error && <div style={{ color: 'var(--red)' }}>{check.error}</div>}</div>
        <div className="font-mono" style={{ fontSize: '.58rem', color: 'var(--steel)', marginTop: 8 }}>{check.source} · {clock(check.checked_at)} · {check.latency_ms} ms{check.cached ? ' · cached' : ''}</div>
        <details><summary style={{ fontSize: '.68rem' }}>Measured details</summary><pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', fontSize: '.65rem', maxHeight: 220, overflow: 'auto' }}>{JSON.stringify(check, null, 2)}</pre></details>
      </div>)}
      <div className="sys-card" style={{ gridColumn: '1 / -1' }}>
        <div className="sys-card-title">Intro / Outro</div>
        <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}><button className="btn btn-steel btn-sm" onClick={loadIoConfig} disabled={ioLoading}>RELOAD</button><button className="btn btn-solid btn-sm" onClick={saveIoConfig} disabled={ioSaving || !ioCfg}>{ioSaving ? <Spinner /> : <Save size={12} />} SAVE CONFIG</button></div>
        {ioLoading && <Spinner />}
        {ioCfg && <>
          <Field label="Apply intro and outro"><select className="ds-select" value={ioCfg.enabled ? 'yes' : 'no'} onChange={e => setIo('enabled', e.target.value === 'yes')}><option value="yes">Enabled</option><option value="no">Disabled</option></select></Field>
          <AudioAssetPicker label="Theme music / jingle / SFX" value={ioCfg.music_file || ''} onChange={value => setIo('music_file', value)} />
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 20 }}>
            {['intro', 'outro'].map(section => <div key={section}>
              <div className="section-head"><span>{section.toUpperCase()}</span><button className="btn btn-steel btn-sm" onClick={() => previewSection(section)} disabled={!!ioPreviewing}>{ioPreviewing === section ? <Spinner /> : <Play size={12} />} PREVIEW SAVED SETTINGS</button></div>
              <Field label={section === 'outro' ? 'Spoken outro ({topic} and [pause] supported)' : 'Spoken intro'}><textarea className="ds-textarea" value={ioCfg[section]?.announcer_text || ''} onChange={e => setIo(section + '.announcer_text', e.target.value)} /></Field>
              <Field label="Announcer voice (Kokoro voice ID)"><input className="ds-input" value={ioCfg[section]?.announcer_voice || ''} onChange={e => setIo(section + '.announcer_voice', e.target.value)} /></Field>
              <Field label="Music duration (seconds)"><input className="ds-input" type="number" min="0" max="120" value={(ioCfg[section]?.clip_duration_ms || 0) / 1000} onChange={e => setIo(section + '.clip_duration_ms', Number(e.target.value) * 1000)} /></Field>
              <details><summary>Advanced timing and mix (milliseconds / dB)</summary>{Object.entries(ioCfg[section] || {}).filter(([key, value]) => typeof value === 'number' && key !== 'clip_duration_ms').map(([key, value]) => <Field key={key} label={key.replaceAll('_', ' ')}><input className="ds-input" type="number" value={value} onChange={e => setIo(section + '.' + key, Number(e.target.value))} /></Field>)}</details>
            </div>)}
          </div>
          <div style={{ fontSize: '.72rem', marginTop: 12 }}>Intro/outro runs once around the assembled episode, not around each 15-minute section. Preview uses saved settings; save before previewing edits.</div>
        </>}
        {ioPreviewUrl && <audio controls src={ioPreviewUrl} style={{ width: '100%', marginTop: 12 }} />}
      </div>
    </div><Toast {...toast} />
  </div></div>
}
