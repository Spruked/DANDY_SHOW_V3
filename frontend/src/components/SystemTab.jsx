// components/SystemTab.jsx
import { useState, useEffect } from 'react'
import { RefreshCw, CheckCircle, XCircle, Mic, Cpu, Globe, Music, Play, Save } from 'lucide-react'
import { api } from '../lib/api'
import { Badge, Spinner, Toast, Field } from './ui'
import { useToast } from '../hooks/useToast'

const KNOWN_VOICES = [
  { id: 'am_michael', character: 'Phil',               engine: 'Kokoro', role: 'Host' },
  { id: 'am_liam',    character: 'Jim',                engine: 'Kokoro', role: 'Host' },
  { id: 'am_eric',    character: 'Host / Announcer',   engine: 'Kokoro', role: 'Host / Announcer' },
  { id: 'bf_emma',    character: 'Guest / Announcer',  engine: 'Kokoro', role: 'Guest / Announcer' },
]

const PROXIES = [
  { name: 'Backend API',     url: '/api', note: 'FastAPI through the active Vite proxy' },
  { name: 'Vite Dev Server', url: 'http://localhost:5173', note: 'Frontend and /api proxy' },
  { name: 'WebSocket',       url: 'ws://localhost:5173/ws', note: 'Production progress stream' },
]

const displayValue = (value) => (
  value && typeof value === 'object' ? JSON.stringify(value) : String(value)
)

export default function SystemTab() {
  const { toast, showToast } = useToast()
  const [health, setHealth] = useState(null)
  const [voices, setVoices] = useState([])
  const [checking, setChecking] = useState(false)
  const [savingTts, setSavingTts] = useState(false)

  const [ioCfg, setIoCfg] = useState(null)
  const [ioLoading, setIoLoading] = useState(false)
  const [ioSaving, setIoSaving] = useState(false)
  const [ioPreviewing, setIoPreviewing] = useState(null)
  const [ioPreviewUrl, setIoPreviewUrl] = useState(null)

  useEffect(() => { checkHealth(); loadIoConfig() }, [])

  const loadIoConfig = async () => {
    setIoLoading(true)
    try {
      const cfg = await api.getIntroOutroConfig()
      setIoCfg(cfg)
    } catch { showToast('Could not load intro/outro config') }
    setIoLoading(false)
  }

  const saveIoConfig = async () => {
    if (!ioCfg) return
    setIoSaving(true)
    try {
      await api.saveIntroOutroConfig(ioCfg)
      showToast('Intro/outro config saved ✓')
    } catch (e) { showToast('Save failed: ' + e.message.slice(0, 60)) }
    setIoSaving(false)
  }

  const previewSection = async (section) => {
    setIoPreviewing(section)
    if (ioPreviewUrl) URL.revokeObjectURL(ioPreviewUrl)
    setIoPreviewUrl(null)
    try {
      const url = await api.previewIntroOutro(section, 'the show')
      setIoPreviewUrl(url)
    } catch (e) { showToast(`Preview failed: ${e.message.slice(0, 100)}`) }
    setIoPreviewing(null)
  }

  const setIo = (path, value) => {
    setIoCfg(prev => {
      const next = JSON.parse(JSON.stringify(prev))
      const keys = path.split('.')
      let obj = next
      for (let i = 0; i < keys.length - 1; i++) obj = obj[keys[i]]
      obj[keys[keys.length - 1]] = value
      return next
    })
  }

  const checkHealth = async () => {
    setChecking(true)
    try {
      const h = await api.health()
      setHealth({ ok: true, ...h })
    } catch (e) {
      setHealth({ ok: false, error: e.message })
    }
    try {
      const v = await api.voices()
      setVoices(Array.isArray(v) ? v : (v.kokoro || v.voices || []))
    } catch { setVoices([]) }
    setChecking(false)
  }

  const setProductionTts = async (engine) => {
    setSavingTts(true)
    try {
      const response = await fetch('/api/tts-engine', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ engine }),
      })
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}))
        throw new Error(payload.detail || `HTTP ${response.status}`)
      }
      showToast(`Production TTS set to ${engine.toUpperCase()} ✓`)
      await checkHealth()
    } catch (e) {
      showToast('TTS selection failed: ' + e.message.slice(0, 90))
    }
    setSavingTts(false)
  }

  const backendOk = health?.ok
  const selectedTts = String(health?.tts_runtime?.primary_engine || 'kokoro').toLowerCase()
  const qwen = health?.qwen_tts_bridge || {}

  return (
    <div className="tab-body">
      <div className="pane-main" style={{ overflow: 'auto' }}>
        <div className="section-head">
          <span className="section-label">System Status</span>
          <button className="icon-btn" onClick={checkHealth} title="Refresh" disabled={checking}>
            <RefreshCw size={10} style={{ animation: checking ? 'spin .7s linear infinite' : 'none' }} />
          </button>
        </div>

        <div className="sys-grid">
          <div className="sys-card">
            <div className="sys-card-title">Backend Health</div>
            {checking && <Spinner size={18} />}
            {!checking && health && (
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                  {backendOk
                    ? <CheckCircle size={18} style={{ color: 'var(--green)' }} />
                    : <XCircle size={18} style={{ color: 'var(--red)' }} />}
                  <span className="font-mono" style={{ fontSize: '.6rem', color: backendOk ? 'var(--green)' : 'var(--red)' }}>
                    {backendOk ? 'ONLINE - /api' : 'OFFLINE'}
                  </span>
                </div>
                {health.ok && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                    {Object.entries(health).filter(([k]) => k !== 'ok').map(([k, v]) => (
                      <div key={k} style={{ display: 'flex', justifyContent: 'space-between', gap: 10 }}>
                        <span className="font-mono" style={{ fontSize: '.52rem', color: 'var(--steel)' }}>{k}</span>
                        <span className="font-mono" style={{ fontSize: '.52rem', color: 'var(--bone)', textAlign: 'right' }}>{displayValue(v)}</span>
                      </div>
                    ))}
                  </div>
                )}
                {!health.ok && (
                  <div className="font-mono" style={{ fontSize: '.55rem', color: 'var(--red)', marginTop: 6 }}>{health.error}</div>
                )}
              </div>
            )}
          </div>

          <div className="sys-card">
            <div className="sys-card-title">Network / Proxies</div>
            {PROXIES.map((p, i) => (
              <div key={i} style={{ marginBottom: 10 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
                  <Globe size={11} style={{ color: 'var(--gold)', flexShrink: 0 }} />
                  <span style={{ fontSize: '.75rem', fontWeight: 600, color: 'var(--bone)' }}>{p.name}</span>
                </div>
                <div className="font-mono" style={{ fontSize: '.52rem', color: 'var(--blue)', marginBottom: 2 }}>{p.url}</div>
                <div className="font-mono" style={{ fontSize: '.48rem', color: 'var(--steel)' }}>{p.note}</div>
              </div>
            ))}
          </div>

          <div className="sys-card" style={{ gridColumn: '1 / -1' }}>
            <div className="sys-card-title">Production TTS</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, alignItems: 'end' }}>
              <Field label="Selected Engine">
                <select className="ds-select" value={selectedTts} disabled={savingTts} onChange={e => setProductionTts(e.target.value)}>
                  <option value="kokoro">Kokoro — Default</option>
                  <option value="qwen">Qwen — Explicit Selection</option>
                </select>
              </Field>
              <div className="font-mono" style={{ fontSize: '.55rem', color: 'var(--bone)', lineHeight: 1.7 }}>
                <div>Fallback engine: <strong>NONE</strong></div>
                <div>Edge TTS: NOT USED</div>
                <div>Browser voice: NOT USED</div>
              </div>
            </div>
            <div style={{ marginTop: 12, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <Badge type="gold">Kokoro primary</Badge>
              <Badge type={qwen.status === 'ok' ? 'green' : 'steel'}>Qwen bridge: {qwen.status || 'unknown'}</Badge>
            </div>
          </div>

          <div className="sys-card" style={{ gridColumn: '1 / -1' }}>
            <div className="sys-card-title">Kokoro Voice Registry</div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 8 }}>
              {KNOWN_VOICES.map((v, i) => {
                const liveVoice = voices.find(lv => lv.id === v.id || lv.voice_id === v.id)
                return (
                  <div key={i} className="voice-row" style={{ flexDirection: 'column', alignItems: 'flex-start', padding: '8px 10px', border: '1px solid var(--rim)', borderRadius: 'var(--radius)', background: 'var(--bg)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, width: '100%' }}>
                      <Mic size={13} style={{ color: 'var(--gold)', flexShrink: 0 }} />
                      <span style={{ fontWeight: 600, fontSize: '.78rem', color: 'var(--bone)', flex: 1 }}>{v.character}</span>
                      <Badge type="gold">{v.engine}</Badge>
                    </div>
                    <div className="font-mono" style={{ fontSize: '.5rem', color: 'var(--steel)', marginTop: 4 }}>{v.id} · {v.role}</div>
                    {liveVoice && <div className="font-mono" style={{ fontSize: '.46rem', color: 'var(--green)', marginTop: 3 }}>✓ registered</div>}
                  </div>
                )
              })}
            </div>
          </div>

          <div className="sys-card">
            <div className="sys-card-title">Hardware</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
              <Cpu size={14} style={{ color: 'var(--gold)' }} />
              <span style={{ fontSize: '.78rem', color: 'var(--bone)' }}>RTX 3050 6GB GDDR6</span>
            </div>
            <div className="font-mono" style={{ fontSize: '.52rem', color: 'var(--steel)', lineHeight: 1.8 }}>
              <div>Primary TTS: {health?.tts_runtime?.primary_engine || '--'}</div>
              <div>Device: {health?.tts_runtime?.device || '--'}</div>
              <div>Fallback: NONE</div>
              <div>Voices defined: {health?.tts_runtime?.voices_defined || '--'}</div>
              <div>ffmpeg: staging/ffmpeg/ffmpeg-master-latest-win64-gpl/bin</div>
            </div>
          </div>

          <div className="sys-card">
            <div className="sys-card-title">Production Notes</div>
            <div className="font-mono" style={{ fontSize: '.52rem', color: 'var(--steel)', lineHeight: 2 }}>
              <div style={{ color: 'var(--bone)' }}>Offline runner: <span style={{ color: 'var(--gold)' }}>python staging/produce_demo.py</span></div>
              <div>Watch: <span style={{ color: 'var(--blue)' }}>logs/produce_demo.log</span></div>
              <div>Audio: <span style={{ color: 'var(--blue)' }}>episodes/&lt;episode_id&gt;/audio.mp3</span></div>
              <div>Selected TTS failure stops production. No alternate voice provider is substituted.</div>
            </div>
          </div>

          <div className="sys-card" style={{ gridColumn: '1 / -1' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
              <div className="sys-card-title" style={{ marginBottom: 0 }}>
                <Music size={12} style={{ display: 'inline', marginRight: 6, color: 'var(--gold)' }} />
                Intro / Outro Settings
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <button className="btn btn-steel btn-sm" onClick={loadIoConfig} disabled={ioLoading}><RefreshCw size={10} /> RELOAD</button>
                <button className="btn btn-solid btn-sm" onClick={saveIoConfig} disabled={ioSaving || !ioCfg}>{ioSaving ? <Spinner size={10} /> : <Save size={10} />} SAVE CONFIG</button>
              </div>
            </div>

            {ioLoading && <Spinner size={18} />}
            {!ioLoading && ioCfg && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                  <Field label="Enabled">
                    <select className="ds-select" value={ioCfg.enabled ? 'yes' : 'no'} onChange={e => setIo('enabled', e.target.value === 'yes')}>
                      <option value="yes">Yes — apply on every produce</option>
                      <option value="no">No — skip intro/outro</option>
                    </select>
                  </Field>
                  <Field label="Music File"><input className="ds-input" value={ioCfg.music_file || ''} onChange={e => setIo('music_file', e.target.value)} /></Field>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
                      <div className="section-label">Intro</div>
                      <button className="btn btn-steel btn-sm" onClick={() => previewSection('intro')} disabled={ioPreviewing === 'intro'}>{ioPreviewing === 'intro' ? <Spinner size={9} /> : <Play size={9} />} PREVIEW</button>
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                      <Field label="Announcer Text"><textarea className="ds-textarea" style={{ minHeight: 52 }} value={ioCfg.intro?.announcer_text || ''} onChange={e => setIo('intro.announcer_text', e.target.value)} /></Field>
                      <Field label="Announcer Voice (Kokoro)"><input className="ds-input" value={ioCfg.intro?.announcer_voice || ''} onChange={e => setIo('intro.announcer_voice', e.target.value)} /></Field>
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                        <Field label="Clip Start (ms)"><input className="ds-input" type="number" value={ioCfg.intro?.clip_start_ms ?? 0} onChange={e => setIo('intro.clip_start_ms', +e.target.value)} /></Field>
                        <Field label="Clip Duration (ms)"><input className="ds-input" type="number" value={ioCfg.intro?.clip_duration_ms ?? 14000} onChange={e => setIo('intro.clip_duration_ms', +e.target.value)} /></Field>
                        <Field label="Music Fade In (ms)"><input className="ds-input" type="number" value={ioCfg.intro?.music_fade_in_ms ?? 1200} onChange={e => setIo('intro.music_fade_in_ms', +e.target.value)} /></Field>
                        <Field label="Music Fade Out (ms)"><input className="ds-input" type="number" value={ioCfg.intro?.music_fade_out_ms ?? 2000} onChange={e => setIo('intro.music_fade_out_ms', +e.target.value)} /></Field>
                        <Field label="Duck Start (ms)"><input className="ds-input" type="number" value={ioCfg.intro?.duck_start_ms ?? 4000} onChange={e => setIo('intro.duck_start_ms', +e.target.value)} /></Field>
                        <Field label="Duck Level (dB)"><input className="ds-input" type="number" value={ioCfg.intro?.duck_db ?? -18} onChange={e => setIo('intro.duck_db', +e.target.value)} /></Field>
                        <Field label="Silence After (ms)"><input className="ds-input" type="number" value={ioCfg.intro?.silence_after_ms ?? 800} onChange={e => setIo('intro.silence_after_ms', +e.target.value)} /></Field>
                        <Field label="Pause Duration (ms)"><input className="ds-input" type="number" value={ioCfg.intro?.pause_duration_ms ?? 700} onChange={e => setIo('intro.pause_duration_ms', +e.target.value)} /></Field>
                      </div>
                    </div>
                  </div>

                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
                      <div className="section-label">Outro</div>
                      <button className="btn btn-steel btn-sm" onClick={() => previewSection('outro')} disabled={ioPreviewing === 'outro'}>{ioPreviewing === 'outro' ? <Spinner size={9} /> : <Play size={9} />} PREVIEW</button>
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                      <Field label="Announcer Text ({topic} + [pause] supported)"><textarea className="ds-textarea" style={{ minHeight: 52 }} value={ioCfg.outro?.announcer_text || ''} onChange={e => setIo('outro.announcer_text', e.target.value)} /></Field>
                      <Field label="Announcer Voice (Kokoro)"><input className="ds-input" value={ioCfg.outro?.announcer_voice || ''} onChange={e => setIo('outro.announcer_voice', e.target.value)} /></Field>
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                        <Field label="Clip Start (ms)"><input className="ds-input" type="number" value={ioCfg.outro?.clip_start_ms ?? 0} onChange={e => setIo('outro.clip_start_ms', +e.target.value)} /></Field>
                        <Field label="Clip Duration (ms)"><input className="ds-input" type="number" value={ioCfg.outro?.clip_duration_ms ?? 12000} onChange={e => setIo('outro.clip_duration_ms', +e.target.value)} /></Field>
                        <Field label="Music Fade In (ms)"><input className="ds-input" type="number" value={ioCfg.outro?.music_fade_in_ms ?? 2000} onChange={e => setIo('outro.music_fade_in_ms', +e.target.value)} /></Field>
                        <Field label="Music Fade Out (ms)"><input className="ds-input" type="number" value={ioCfg.outro?.music_fade_out_ms ?? 3000} onChange={e => setIo('outro.music_fade_out_ms', +e.target.value)} /></Field>
                        <Field label="Silence Before (ms)"><input className="ds-input" type="number" value={ioCfg.outro?.silence_before_ms ?? 600} onChange={e => setIo('outro.silence_before_ms', +e.target.value)} /></Field>
                        <Field label="Pause Duration (ms)"><input className="ds-input" type="number" value={ioCfg.outro?.pause_duration_ms ?? 700} onChange={e => setIo('outro.pause_duration_ms', +e.target.value)} /></Field>
                      </div>
                    </div>
                  </div>
                </div>

                {ioPreviewUrl && (
                  <div style={{ marginTop: 4 }}>
                    <div className="section-label" style={{ marginBottom: 6 }}>Preview</div>
                    <audio controls autoPlay src={ioPreviewUrl} style={{ width: '100%' }} />
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
      <Toast {...toast} />
    </div>
  )
}
