// components/StudioTab.jsx — Phil & Jim Dandy Show Full Studio Control Dashboard
import { useState, useEffect, useCallback } from 'react'
import {
  Mic, Mic2, Volume2, VolumeX, Radio, Monitor, Camera,
  Headphones, Settings, Activity, Zap, ToggleLeft, ToggleRight,
  Sliders, Speaker, Eye, EyeOff, RefreshCw, ChevronDown, ChevronUp,
  Cpu, Globe, Wifi, AlertCircle, CheckCircle, XCircle, Music,
  Video, Layers, Play, Square, Circle, SkipForward, Download
} from 'lucide-react'

// ─── tiny helpers ─────────────────────────────────────────────────────────────
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v))
const pct   = v => `${clamp(v, 0, 100)}%`

const OBS_POLL_MS = 2000
const MIXER_POLL_MS = 900
const MIXER_MACRO_INDEX = {
  intro: 0,
  break: 1,
  music: 2,
  nomusic: 3,
  brb: 4,
  live: 5,
  record: 6,
  outro: 7,
}

const pctToDb = (value) => {
  const normalized = clamp(Number(value), 0, 100) / 100
  return Math.round((-60 + (normalized * 72)) * 10) / 10
}

const dbToPct = (value) => {
  const db = clamp(Number(value), -60, 12)
  return Math.round(((db + 60) / 72) * 100)
}

function Toggle({ on, onClick, color = 'var(--gold)' }) {
  return (
    <button
      onClick={onClick}
      style={{
        background: on ? color : 'var(--rim)',
        border: 'none', borderRadius: 12, width: 36, height: 20,
        cursor: 'pointer', position: 'relative', transition: 'background .2s',
        flexShrink: 0,
      }}
    >
      <span style={{
        position: 'absolute', top: 2, left: on ? 18 : 2,
        width: 16, height: 16, borderRadius: '50%',
        background: '#fff', transition: 'left .2s',
      }} />
    </button>
  )
}

function Fader({ label, value, onChange, color = 'var(--gold)', unit = 'dB', min = -60, max = 12 }) {
  const range = max - min
  const pos   = ((value - min) / range) * 100
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4, minWidth: 44 }}>
      <div style={{ fontSize: '.48rem', color: 'var(--steel)', fontFamily: 'var(--font-mono)', letterSpacing: '.08em' }}>
        {label}
      </div>
      {/* vertical slider track */}
      <div style={{ position: 'relative', width: 6, height: 100, background: 'var(--rim)', borderRadius: 3 }}>
        <div style={{
          position: 'absolute', bottom: 0, left: 0, right: 0,
          height: pct(pos), background: color, borderRadius: 3, transition: 'height .1s',
        }} />
        <input
          type="range" min={min} max={max} value={value}
          onChange={e => onChange(+e.target.value)}
          style={{
            position: 'absolute', inset: 0, opacity: 0, cursor: 'pointer',
            writingMode: 'vertical-lr', direction: 'rtl', width: '100%', height: '100%',
          }}
        />
      </div>
      <div style={{ fontSize: '.52rem', color, fontFamily: 'var(--font-mono)', fontWeight: 600 }}>
        {value > 0 ? '+' : ''}{value}
      </div>
    </div>
  )
}

function KnobRing({ value, max = 100, color = 'var(--gold)', size = 48 }) {
  const r     = (size - 6) / 2
  const circ  = 2 * Math.PI * r
  const angle = (value / max) * 0.75 * circ
  return (
    <svg width={size} height={size} style={{ transform: 'rotate(-135deg)' }}>
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="var(--rim)" strokeWidth={5} strokeDasharray={`${0.75*circ} ${circ}`} strokeLinecap="round" />
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={color} strokeWidth={5} strokeDasharray={`${angle} ${circ}`} strokeLinecap="round" />
    </svg>
  )
}

function Knob({ label, value, onChange, max = 100, color = 'var(--gold)' }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3 }}>
      <div style={{ position: 'relative', cursor: 'pointer' }}>
        <KnobRing value={value} max={max} color={color} />
        <input
          type="range" min={0} max={max} value={value}
          onChange={e => onChange(+e.target.value)}
          style={{ position: 'absolute', inset: 0, opacity: 0, cursor: 'pointer', width: '100%', height: '100%' }}
        />
        <div style={{
          position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: '.52rem', fontFamily: 'var(--font-mono)', color, fontWeight: 600,
        }}>
          {value}
        </div>
      </div>
      <div style={{ fontSize: '.46rem', color: 'var(--steel)', fontFamily: 'var(--font-mono)', textAlign: 'center', maxWidth: 52 }}>
        {label}
      </div>
    </div>
  )
}

function VUMeter({ level = 0, label = '' }) {
  const bars  = 20
  const lit   = Math.round((level / 100) * bars)
  const color = level > 85 ? 'var(--red)' : level > 65 ? 'var(--gold)' : 'var(--green)'
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 2, alignItems: 'center' }}>
      <div style={{ display: 'flex', flexDirection: 'column-reverse', gap: 1.5 }}>
        {Array.from({ length: bars }, (_, i) => (
          <div key={i} style={{
            width: 8, height: 3, borderRadius: 1,
            background: i < lit
              ? (i > bars * 0.85 ? 'var(--red)' : i > bars * 0.65 ? 'var(--gold)' : 'var(--green)')
              : 'var(--rim)',
            transition: 'background .05s',
          }} />
        ))}
      </div>
      <div style={{ fontSize: '.42rem', color: 'var(--steel)', fontFamily: 'var(--font-mono)', marginTop: 2 }}>{label}</div>
    </div>
  )
}

function SectionCard({ title, icon: Icon, children, accent = 'var(--gold)', defaultOpen = true, style = {} }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div style={{
      background: 'var(--panel)', border: `1px solid var(--rim)`,
      borderRadius: 'var(--radius-lg)', overflow: 'hidden',
      borderTop: `2px solid ${accent}`,
      ...style,
    }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          width: '100%', display: 'flex', alignItems: 'center', gap: 8,
          padding: '8px 12px', background: 'none', border: 'none',
          cursor: 'pointer', color: 'var(--bone)',
        }}
      >
        {Icon && <Icon size={12} style={{ color: accent }} />}
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '.6rem', letterSpacing: '.1em', flex: 1, textAlign: 'left' }}>
          {title}
        </span>
        {open ? <ChevronUp size={10} style={{ color: 'var(--steel)' }} /> : <ChevronDown size={10} style={{ color: 'var(--steel)' }} />}
      </button>
      {open && <div style={{ padding: '0 12px 12px' }}>{children}</div>}
    </div>
  )
}

function StatusPill({ ok, label }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 5,
      background: ok ? '#1a2e1a' : '#2e1a1a',
      border: `1px solid ${ok ? 'var(--green)' : 'var(--red)'}`,
      borderRadius: 20, padding: '3px 10px',
    }}>
      {ok
        ? <CheckCircle size={10} style={{ color: 'var(--green)' }} />
        : <XCircle    size={10} style={{ color: 'var(--red)' }} />
      }
      <span style={{ fontSize: '.52rem', fontFamily: 'var(--font-mono)', color: ok ? 'var(--green)' : 'var(--red)' }}>
        {label}
      </span>
    </div>
  )
}

function MacroBtn({ label, color = 'var(--gold)', onClick, active = false, disabled = false }) {
  return (
    <button
      disabled={disabled}
      onClick={onClick}
      style={{
        background: active ? color : 'var(--bg)',
        border: `1px solid ${color}`,
        borderRadius: 'var(--radius)', padding: '6px 10px',
        color: active ? '#000' : color,
        fontFamily: 'var(--font-mono)', fontSize: '.55rem',
        letterSpacing: '.06em', cursor: 'pointer', transition: 'all .15s',
        fontWeight: active ? 700 : 400,
        opacity: disabled ? 0.5 : 1,
      }}
    >
      {label}
    </button>
  )
}

// ─── MAIN COMPONENT ───────────────────────────────────────────────────────────
export default function StudioTab() {

  // ── Voicemeeter channel states ──
  const initCh = (label, color, gain = 0) => ({
    label, color, gain, mute: false, solo: false,
    gate: 30, comp: 40, eq: false,
    a1: true, a2: false, b1: true, b2: false,
    available: true,
    vu: 0,
  })

  const [channels, setChannels] = useState({
    mic1:  initCh('MIC 1 · PHIL', 'var(--phil)',   0),
    mic2:  initCh('MIC 2 · JIM',  'var(--jim)',    0),
    guest: initCh('GUEST MIC',    'var(--guest)', -3),
    music: initCh('MUSIC BED',    'var(--steel)', -18),
    sfx:   initCh('SFX',          'var(--ad)',    -6),
    vm:    initCh('VOICEMEETER',  'var(--gold)',   0),
  })

  const [master, setMaster] = useState({ gain: 0, mute: false, comp: 60, limiter: true, vu: 0 })

  // ── Monitor / headphone ──
  const [monitor, setMonitor] = useState({
    volume: 75, dim: false, mono: false, philHP: 80, jimHP: 80,
    talkback: false, comfortReverb: 20, clickTrack: false, clickLevel: 50,
  })

  // ── OBS states ──
  const [obs, setObs] = useState({
    connected: false, streaming: false, recording: false,
    activeScene: '',
    scenes: [],
    virtualCam: false,
    transition: 'Cut',
    transitions: ['Cut', 'Fade', 'Swipe', 'Stinger'],
  })

  // ── Camera states ──
  const [cameras, setCameras] = useState({
    main:  { label: 'MAIN', zoom: 50, focus: 70, exposure: 55, active: true  },
    phil:  { label: 'PHIL', zoom: 40, focus: 65, exposure: 55, active: false },
    jim:   { label: 'JIM',  zoom: 40, focus: 65, exposure: 55, active: false },
    screen:{ label: 'SCRN', zoom: 100, focus: 100, exposure: 50, active: false },
  })

  // ── Macro buttons ──
  const [activeMacros, setActiveMacros] = useState({})
  const macros = [
    { id: 'intro',   label: 'INTRO SEQUENCE',  color: 'var(--gold)'  },
    { id: 'break',   label: 'AD BREAK',         color: 'var(--ad)'    },
    { id: 'music',   label: 'MUSIC BED ON',     color: 'var(--blue)'  },
    { id: 'nomusic', label: 'MUSIC BED OFF',    color: 'var(--steel)' },
    { id: 'brb',     label: 'BRB SCREEN',       color: 'var(--red)'   },
    { id: 'live',    label: 'GO LIVE',          color: 'var(--green)' },
    { id: 'record',  label: 'START RECORD',     color: 'var(--red)'   },
    { id: 'outro',   label: 'OUTRO SEQUENCE',   color: 'var(--gold)'  },
  ]

  // ── Audacity / Recording ──
  const [audacity, setAudacity] = useState({
    inputGain: 75, noiseReduction: 60, compression: 50,
    eq: 55, deEss: 40, limiter: 80, recording: false,
  })

  // ── Streaming status ──
  const [stream, setStream] = useState({
    platform: 'OBS', bitrate: '--', fps: '--', resolution: '--',
    duration: 0, viewers: 0,
  })
  const [mixerConnected, setMixerConnected] = useState(false)
  const [mixerKind, setMixerKind] = useState('')
  const [mixerError, setMixerError] = useState('')
  const [obsBusy, setObsBusy] = useState(false)
  const [obsError, setObsError] = useState('')
  const [macroBusy, setMacroBusy] = useState(false)
  const [macroError, setMacroError] = useState('')
  const [studioView, setStudioView] = useState('audio')
  const [audioIo, setAudioIo] = useState({ ok: false, label: 'AUDIO I/O' })

  const mixerRequest = useCallback(async (path, options = {}) => {
    const res = await fetch(`/api/mixer${path}`, {
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
      ...options,
    })
    if (!res.ok) {
      let detail = `HTTP ${res.status}`
      try {
        const data = await res.json()
        detail = data.detail || detail
      } catch {
        detail = await res.text().catch(() => detail)
      }
      throw new Error(detail)
    }
    const ct = res.headers.get('content-type') || ''
    if (ct.includes('application/json')) return res.json()
    return {}
  }, [])

  const refreshMixerStatus = useCallback(async () => {
    try {
      const data = await mixerRequest('/status')
      const incomingChannels = data.channels || {}
      setChannels(prev => {
        const next = { ...prev }
        Object.keys(next).forEach((key) => {
          const source = incomingChannels[key]
          if (!source) return
          if (source.available === false) {
            next[key] = { ...next[key], available: false }
            return
          }
          next[key] = {
            ...next[key],
            label: source.label || next[key].label,
            available: true,
            gain: Number(source.gain ?? next[key].gain),
            mute: Boolean(source.mute ?? next[key].mute),
            solo: Boolean(source.solo ?? next[key].solo),
            eq: Boolean(source.eq ?? next[key].eq),
            gate: Number(source.gate ?? next[key].gate),
            comp: Number(source.comp ?? next[key].comp),
            a1: Boolean(source.a1 ?? next[key].a1),
            a2: Boolean(source.a2 ?? next[key].a2),
            b1: Boolean(source.b1 ?? next[key].b1),
            b2: Boolean(source.b2 ?? next[key].b2),
            vu: Number(source.vu ?? next[key].vu),
          }
        })
        return next
      })
      if (data.master) {
        setMaster(prev => ({
          ...prev,
          gain: Number(data.master.gain ?? prev.gain),
          mute: Boolean(data.master.mute ?? prev.mute),
          vu: Number(data.master.vu ?? prev.vu),
        }))
        setMonitor(prev => ({
          ...prev,
          volume: Number.isFinite(Number(data.master.gain)) ? dbToPct(Number(data.master.gain)) : prev.volume,
          mono: typeof data.master.mono === 'boolean' ? data.master.mono : prev.mono,
        }))
      }
      setMixerConnected(Boolean(data.connected))
      setMixerKind(String(data.kind || ''))
      setMixerError('')
    } catch (err) {
      setMixerConnected(false)
      setMixerError(err?.message || 'Voicemeeter unavailable')
    }
  }, [mixerRequest])

  useEffect(() => {
    let cancelled = false
    const init = async () => {
      await refreshMixerStatus()
      if (cancelled) return
    }
    init()
    const iv = setInterval(() => {
      if (!cancelled) refreshMixerStatus()
    }, MIXER_POLL_MS)
    return () => {
      cancelled = true
      clearInterval(iv)
    }
  }, [refreshMixerStatus])

  const obsRequest = useCallback(async (path, options = {}) => {
    const res = await fetch(`/api/obs${path}`, {
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
      ...options,
    })
    if (!res.ok) {
      let detail = `HTTP ${res.status}`
      try {
        const data = await res.json()
        detail = data.detail || detail
      } catch {
        detail = await res.text().catch(() => detail)
      }
      throw new Error(detail)
    }
    const ct = res.headers.get('content-type') || ''
    if (ct.includes('application/json')) return res.json()
    return {}
  }, [])

  const refreshObsStatus = useCallback(async () => {
    try {
      const data = await obsRequest('/status')
      setObs(prev => ({
        ...prev,
        connected: Boolean(data.connected),
        streaming: Boolean(data.streaming),
        recording: Boolean(data.recording),
        activeScene: data.scene_name || prev.activeScene,
      }))
      setStream(prev => ({
        ...prev,
        duration: Number(data.stream_duration_seconds || 0),
        bitrate: data.bitrate_kbps ?? data.output_bitrate_kbps ?? '--',
        fps: data.fps ?? data.output_fps ?? '--',
        resolution: data.resolution || data.output_resolution || '--',
      }))
      setObsError('')
    } catch (err) {
      setObs(prev => ({ ...prev, connected: false, streaming: false, recording: false }))
      setStream(prev => ({ ...prev, duration: 0, bitrate: '--', fps: '--', resolution: '--' }))
      setObsError(err?.message || 'OBS unavailable')
    }
  }, [obsRequest])

  const refreshObsScenes = useCallback(async () => {
    try {
      const data = await obsRequest('/scenes')
      setObs(prev => ({
        ...prev,
        connected: Boolean(data.connected),
        scenes: Array.isArray(data.scenes) ? data.scenes : prev.scenes,
        activeScene: data.active_scene || prev.activeScene,
      }))
      setObsError('')
    } catch (err) {
      setObs(prev => ({ ...prev, connected: false }))
      setObsError(err?.message || 'OBS unavailable')
    }
  }, [obsRequest])

  useEffect(() => {
    let cancelled = false
    const init = async () => {
      await Promise.all([refreshObsStatus(), refreshObsScenes()])
      if (cancelled) return
    }
    init()
    const iv = setInterval(() => {
      if (!cancelled) refreshObsStatus()
    }, OBS_POLL_MS)
    return () => {
      cancelled = true
      clearInterval(iv)
    }
  }, [refreshObsScenes, refreshObsStatus])

  const refreshAudioIoStatus = useCallback(async () => {
    try {
      const [healthRes, voicesRes] = await Promise.all([
        fetch('/api/health'),
        fetch('/api/voices'),
      ])
      if (!healthRes.ok) throw new Error(`health HTTP ${healthRes.status}`)
      if (!voicesRes.ok) throw new Error(`voices HTTP ${voicesRes.status}`)
      const health = await healthRes.json()
      const voices = await voicesRes.json()
      const voiceCount =
        (Array.isArray(voices.kokoro) ? voices.kokoro.length : 0) +
        (Array.isArray(voices.edge) ? voices.edge.length : 0)
      const healthy = health.status === 'healthy' && voiceCount > 0
      setAudioIo({
        ok: healthy,
        label: healthy ? `AUDIO I/O ${voiceCount} VOICES` : 'AUDIO I/O OFFLINE',
      })
    } catch {
      setAudioIo({ ok: false, label: 'AUDIO I/O OFFLINE' })
    }
  }, [])

  useEffect(() => {
    refreshAudioIoStatus()
    const iv = setInterval(refreshAudioIoStatus, 30000)
    return () => clearInterval(iv)
  }, [refreshAudioIoStatus])

  const setProgramScene = useCallback(async (sceneName) => {
    if (!sceneName) return
    setObsBusy(true)
    try {
      const data = await obsRequest('/scene', {
        method: 'POST',
        body: JSON.stringify({ scene_name: sceneName }),
      })
      setObs(prev => ({ ...prev, connected: true, activeScene: data.active_scene || sceneName }))
      setObsError('')
    } catch (err) {
      setObs(prev => ({ ...prev, connected: false }))
      setObsError(err?.message || 'Scene switch failed')
    } finally {
      setObsBusy(false)
    }
  }, [obsRequest])

  const toggleObsStream = useCallback(async () => {
    setObsBusy(true)
    try {
      const data = await obsRequest('/stream/toggle', { method: 'POST' })
      setObs(prev => ({ ...prev, connected: true, streaming: Boolean(data.streaming) }))
      setStream(prev => ({ ...prev, duration: Number(data.stream_duration_seconds || prev.duration) }))
      setObsError('')
    } catch (err) {
      setObs(prev => ({ ...prev, connected: false }))
      setObsError(err?.message || 'Stream toggle failed')
    } finally {
      setObsBusy(false)
    }
  }, [obsRequest])

  const toggleObsRecord = useCallback(async () => {
    setObsBusy(true)
    try {
      const data = await obsRequest('/record/toggle', { method: 'POST' })
      setObs(prev => ({ ...prev, connected: true, recording: Boolean(data.recording) }))
      setObsError('')
    } catch (err) {
      setObs(prev => ({ ...prev, connected: false }))
      setObsError(err?.message || 'Record toggle failed')
    } finally {
      setObsBusy(false)
    }
  }, [obsRequest])

  const fmtTime = s => `${String(Math.floor(s/3600)).padStart(2,'0')}:${String(Math.floor((s%3600)/60)).padStart(2,'0')}:${String(s%60).padStart(2,'0')}`

  const patchMixerChannel = useCallback(async (channelId, patch) => {
    try {
      const data = await mixerRequest('/channel', {
        method: 'POST',
        body: JSON.stringify({ channel_id: channelId, ...patch }),
      })
      if (data?.channel?.id) {
        const ch = data.channel
        setChannels(prev => ({
          ...prev,
          [ch.id]: {
            ...prev[ch.id],
            label: ch.label || prev[ch.id]?.label,
            available: ch.available !== false,
            gain: Number(ch.gain ?? prev[ch.id]?.gain ?? 0),
            mute: Boolean(ch.mute ?? prev[ch.id]?.mute ?? false),
            solo: Boolean(ch.solo ?? prev[ch.id]?.solo ?? false),
            eq: Boolean(ch.eq ?? prev[ch.id]?.eq ?? false),
            gate: Number(ch.gate ?? prev[ch.id]?.gate ?? 0),
            comp: Number(ch.comp ?? prev[ch.id]?.comp ?? 0),
            a1: Boolean(ch.a1 ?? prev[ch.id]?.a1 ?? false),
            a2: Boolean(ch.a2 ?? prev[ch.id]?.a2 ?? false),
            b1: Boolean(ch.b1 ?? prev[ch.id]?.b1 ?? false),
            b2: Boolean(ch.b2 ?? prev[ch.id]?.b2 ?? false),
            vu: Number(ch.vu ?? prev[ch.id]?.vu ?? 0),
          },
        }))
      }
      setMixerConnected(true)
      if (data?.kind) setMixerKind(String(data.kind))
      setMixerError('')
    } catch (err) {
      setMixerConnected(false)
      setMixerError(err?.message || 'Voicemeeter write failed')
    }
  }, [mixerRequest])

  const patchMixerMaster = useCallback(async (patch) => {
    try {
      const data = await mixerRequest('/master', {
        method: 'POST',
        body: JSON.stringify(patch),
      })
      if (data?.master) {
        setMaster(prev => ({
          ...prev,
          gain: Number(data.master.gain ?? prev.gain),
          mute: Boolean(data.master.mute ?? prev.mute),
          vu: Number(data.master.vu ?? prev.vu),
        }))
      }
      setMixerConnected(true)
      if (data?.kind) setMixerKind(String(data.kind))
      setMixerError('')
    } catch (err) {
      setMixerConnected(false)
      setMixerError(err?.message || 'Voicemeeter write failed')
    }
  }, [mixerRequest])

  const patchMixerBus = useCallback(async (busIndex, patch) => {
    try {
      const data = await mixerRequest(`/bus/${busIndex}`, {
        method: 'POST',
        body: JSON.stringify(patch),
      })
      if (Number(busIndex) === 0 && data?.bus) {
        const gain = Number(data.bus.gain)
        const mute = Boolean(data.bus.mute)
        const mono = Boolean(data.bus.mono)
        setMaster(prev => ({
          ...prev,
          gain: Number.isFinite(gain) ? gain : prev.gain,
          mute,
        }))
        setMonitor(prev => ({
          ...prev,
          volume: Number.isFinite(gain) ? dbToPct(gain) : prev.volume,
          mono,
        }))
      }
      setMixerConnected(true)
      if (data?.kind) setMixerKind(String(data.kind))
      setMixerError('')
      return data
    } catch (err) {
      setMixerError(err?.message || 'Voicemeeter bus write failed')
      return null
    }
  }, [mixerRequest])

  const triggerMixerMacro = useCallback(async (id) => {
    const buttonIndex = MIXER_MACRO_INDEX[id]
    if (!Number.isInteger(buttonIndex)) return null
    try {
      const data = await mixerRequest(`/macro/${buttonIndex}`, {
        method: 'POST',
        body: JSON.stringify({}),
      })
      setMixerConnected(true)
      if (data?.kind) setMixerKind(String(data.kind))
      setMixerError('')
      return data
    } catch (err) {
      setMixerError(err?.message || `Voicemeeter macro ${buttonIndex} failed`)
      return null
    }
  }, [mixerRequest])

  const updateChannel = useCallback((k, patch, sync = true) => {
    setChannels(p => ({ ...p, [k]: { ...p[k], ...patch } }))
    if (sync) void patchMixerChannel(k, patch)
  }, [patchMixerChannel])

  const updateMaster = useCallback((patch, sync = true) => {
    setMaster(p => ({ ...p, ...patch }))
    if (sync) void patchMixerMaster(patch)
  }, [patchMixerMaster])

  const updateMonitorVolume = useCallback((value) => {
    const next = clamp(Number(value), 0, 100)
    setMonitor(prev => ({ ...prev, volume: next }))
    if (mixerConnected) {
      void patchMixerBus(0, { gain: pctToDb(next) })
    }
  }, [mixerConnected, patchMixerBus])

  const updateMonitorMono = useCallback((value) => {
    const next = Boolean(value)
    setMonitor(prev => ({ ...prev, mono: next }))
    if (mixerConnected) {
      void patchMixerBus(0, { mono: next })
    }
  }, [mixerConnected, patchMixerBus])

  const updateCamera  = (k, patch) => setCameras(p => ({ ...p, [k]: { ...p[k], ...patch } }))
  const chKeys = Object.keys(channels)
  const studioViews = [
    { id: 'audio', label: 'AUDIO MIX', icon: Sliders },
    { id: 'obs', label: 'OBS LIVE', icon: Monitor },
    { id: 'cams', label: 'CAMERAS', icon: Camera },
    { id: 'automate', label: 'MACROS / TOOLS', icon: Zap },
  ]

  const pickSceneByNames = useCallback((candidates) => {
    if (!Array.isArray(obs.scenes) || obs.scenes.length === 0) return null
    const normalize = (value) => String(value || '').toLowerCase().replace(/[^a-z0-9]/g, '')
    const wants = candidates.map(normalize)
    return obs.scenes.find((scene) => {
      const s = normalize(scene)
      return wants.some((item) => s.includes(item))
    }) || null
  }, [obs.scenes])

  const triggerMacro = useCallback(async (id) => {
    setMacroBusy(true)
    setMacroError('')
    setActiveMacros((prev) => ({ ...prev, [id]: true }))
    try {
      await triggerMixerMacro(id)
      if (id === 'music') updateChannel('music', { mute: false })
      if (id === 'nomusic') updateChannel('music', { mute: true })
      if (id === 'live' && !obs.streaming) await toggleObsStream()
      if (id === 'record' && !obs.recording) await toggleObsRecord()
      if (id === 'intro') {
        updateChannel('music', { mute: false })
        const scene = pickSceneByNames(['intro', 'open', 'main'])
        if (scene) await setProgramScene(scene)
      }
      if (id === 'break') {
        const scene = pickSceneByNames(['break', 'ad', 'sponsor'])
        if (scene) await setProgramScene(scene)
      }
      if (id === 'brb') {
        const scene = pickSceneByNames(['brb', 'intermission', 'back'])
        if (scene) await setProgramScene(scene)
      }
      if (id === 'outro') {
        updateChannel('music', { mute: false })
        const scene = pickSceneByNames(['outro', 'credits', 'end'])
        if (scene) await setProgramScene(scene)
      }
    } catch (err) {
      setMacroError(err?.message || 'Macro action failed')
    } finally {
      setTimeout(() => {
        setActiveMacros((prev) => ({ ...prev, [id]: false }))
      }, 900)
      setMacroBusy(false)
    }
  }, [obs.recording, obs.streaming, pickSceneByNames, setProgramScene, toggleObsRecord, toggleObsStream, triggerMixerMacro, updateChannel])

  return (
    <div className="tab-body" style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      {/* ── TOP STATUS BAR ── */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 10, padding: '6px 16px',
        background: 'var(--surface)', borderBottom: '1px solid var(--rim)', flexShrink: 0, flexWrap: 'wrap',
      }}>
        <span style={{ fontFamily: 'var(--font-display)', fontSize: '1rem', color: 'var(--gold)', letterSpacing: '.12em', marginRight: 8 }}>
          DANDY SHOW V3
        </span>
        <StatusPill ok={mixerConnected} label={mixerConnected ? `VOICEMEETER ${mixerKind.toUpperCase()}` : 'VOICEMEETER'} />
        <StatusPill ok={obs.connected} label="OBS WS" />
        <StatusPill ok={audioIo.ok} label={audioIo.label} />
        <StatusPill ok={obs.streaming}  label={obs.streaming ? `LIVE ${fmtTime(stream.duration)}` : 'OFF AIR'} />
        <StatusPill ok={obs.recording}  label={obs.recording  ? 'REC' : 'IDLE'} />
        <button
          onClick={() => void refreshMixerStatus()}
          style={{
            background: 'var(--bg)', border: '1px solid var(--rim)', borderRadius: 6,
            color: 'var(--steel)', fontFamily: 'var(--font-mono)', fontSize: '.5rem', padding: '4px 8px', cursor: 'pointer',
          }}
        >
          REFRESH MIXER
        </button>
        <button
          onClick={() => void Promise.all([refreshObsStatus(), refreshObsScenes()])}
          style={{
            background: 'var(--bg)', border: '1px solid var(--rim)', borderRadius: 6,
            color: 'var(--steel)', fontFamily: 'var(--font-mono)', fontSize: '.5rem', padding: '4px 8px', cursor: 'pointer',
          }}
        >
          REFRESH OBS
        </button>
        {mixerError && (
          <span style={{ fontSize: '.48rem', fontFamily: 'var(--font-mono)', color: 'var(--red)' }}>
            {mixerError}
          </span>
        )}
        {obsError && (
          <span style={{ fontSize: '.48rem', fontFamily: 'var(--font-mono)', color: 'var(--red)' }}>
            {obsError}
          </span>
        )}
        {macroError && (
          <span style={{ fontSize: '.48rem', fontFamily: 'var(--font-mono)', color: 'var(--red)' }}>
            {macroError}
          </span>
        )}
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          <MacroBtn label={obs.streaming ? 'END STREAM' : 'GO LIVE'} color="var(--red)"
            active={obs.streaming}
            disabled={obsBusy}
            onClick={toggleObsStream}
          />
          <MacroBtn label={obs.recording ? 'STOP REC' : 'RECORD'}  color="var(--red)"
            active={obs.recording}
            disabled={obsBusy}
            onClick={toggleObsRecord}
          />
        </div>
      </div>

      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        padding: '8px 12px',
        borderBottom: '1px solid var(--rim)',
        background: 'var(--bg)',
        flexWrap: 'wrap',
        flexShrink: 0,
      }}>
        {studioViews.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setStudioView(id)}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              borderRadius: 999,
              border: `1px solid ${studioView === id ? 'var(--gold)' : 'var(--rim)'}`,
              background: studioView === id ? 'var(--gold-dim)' : 'var(--panel)',
              color: studioView === id ? 'var(--gold)' : 'var(--steel)',
              fontFamily: 'var(--font-mono)',
              fontSize: '.54rem',
              letterSpacing: '.08em',
              padding: '5px 10px',
              cursor: 'pointer',
            }}
          >
            <Icon size={11} />
            {label}
          </button>
        ))}
      </div>

      {/* ── MAIN LAYOUT ── */}
      <div style={{ flex: 1, overflow: 'auto', padding: 12, display: 'grid', gap: 10,
        gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
        alignContent: 'start',
      }}>

        {studioView === 'audio' && (
          <>
        {/* ════════════════════════════════════════════════════════════
            COL 1 — AUDIO / VOICEMEETER
        ════════════════════════════════════════════════════════════ */}

        {/* Channel mixer */}
        <SectionCard title="VOICEMEETER — CHANNEL MIXER" icon={Sliders} accent="var(--gold)" defaultOpen={true}>
          <div style={{ fontSize: '.44rem', color: 'var(--steel)', fontFamily: 'var(--font-mono)', marginBottom: 6 }}>
            {mixerConnected
              ? 'LIVE: channel controls wired to Voicemeeter Remote API.'
              : 'OFFLINE: waiting for Voicemeeter Remote API.'}
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start', overflowX: 'auto', paddingBottom: 4 }}>
            {chKeys.map(k => {
              const ch = channels[k]
              const disabled = !mixerConnected || ch.available === false
              return (
                <div key={k} style={{
                  display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6,
                  minWidth: 68, padding: '8px 6px',
                  background: 'var(--bg)', borderRadius: 'var(--radius)',
                  border: `1px solid ${ch.mute ? 'var(--red)' : ch.solo ? ch.color : 'var(--rim)'}`,
                  opacity: disabled ? 0.5 : 1,
                }}>
                  <div style={{ fontSize: '.44rem', fontFamily: 'var(--font-mono)', color: ch.color, textAlign: 'center', lineHeight: 1.3 }}>
                    {ch.label}
                  </div>
                  <VUMeter level={ch.vu} />
                  <Fader label="GAIN" value={ch.gain} min={-60} max={12} color={ch.color}
                    onChange={v => !disabled && updateChannel(k, { gain: v })} />
                  {/* Gate / Comp knobs */}
                  <div style={{ display: 'flex', gap: 4 }}>
                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 1 }}>
                      <div style={{ position: 'relative' }}>
                        <KnobRing value={ch.gate} max={100} color="var(--blue)" size={32} />
                        <input type="range" min={0} max={100} value={ch.gate}
                          onChange={e => !disabled && updateChannel(k, { gate: +e.target.value })}
                          disabled={disabled}
                          style={{ position: 'absolute', inset: 0, opacity: 0, cursor: 'pointer', width: '100%', height: '100%' }} />
                      </div>
                      <div style={{ fontSize: '.38rem', color: 'var(--steel)', fontFamily: 'var(--font-mono)' }}>GATE</div>
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 1 }}>
                      <div style={{ position: 'relative' }}>
                        <KnobRing value={ch.comp} max={100} color="var(--guest)" size={32} />
                        <input type="range" min={0} max={100} value={ch.comp}
                          onChange={e => !disabled && updateChannel(k, { comp: +e.target.value })}
                          disabled={disabled}
                          style={{ position: 'absolute', inset: 0, opacity: 0, cursor: 'pointer', width: '100%', height: '100%' }} />
                      </div>
                      <div style={{ fontSize: '.38rem', color: 'var(--steel)', fontFamily: 'var(--font-mono)' }}>COMP</div>
                    </div>
                  </div>
                  {/* EQ toggle */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                    <Toggle on={ch.eq} onClick={() => !disabled && updateChannel(k, { eq: !ch.eq })} color="var(--blue)" />
                    <span style={{ fontSize: '.4rem', color: 'var(--steel)', fontFamily: 'var(--font-mono)' }}>EQ</span>
                  </div>
                  {/* Mute / Solo */}
                  <div style={{ display: 'flex', gap: 3 }}>
                    <button disabled={disabled} onClick={() => !disabled && updateChannel(k, { mute: !ch.mute })} style={{
                      background: ch.mute ? 'var(--red)' : 'var(--bg)',
                      border: '1px solid var(--red)', borderRadius: 4,
                      color: ch.mute ? '#fff' : 'var(--red)',
                      fontFamily: 'var(--font-mono)', fontSize: '.42rem', padding: '2px 5px', cursor: 'pointer',
                    }}>M</button>
                    <button disabled={disabled} onClick={() => !disabled && updateChannel(k, { solo: !ch.solo })} style={{
                      background: ch.solo ? 'var(--gold)' : 'var(--bg)',
                      border: '1px solid var(--gold)', borderRadius: 4,
                      color: ch.solo ? '#000' : 'var(--gold)',
                      fontFamily: 'var(--font-mono)', fontSize: '.42rem', padding: '2px 5px', cursor: 'pointer',
                    }}>S</button>
                  </div>
                  {/* Bus routing */}
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 2, width: '100%' }}>
                    {['A1','A2','B1','B2'].map(bus => (
                      <button key={bus} disabled={disabled} onClick={() => !disabled && updateChannel(k, { [bus.toLowerCase()]: !ch[bus.toLowerCase()] })}
                        style={{
                          background: ch[bus.toLowerCase()] ? ch.color : 'var(--bg)',
                          border: `1px solid ${ch.color}`, borderRadius: 3,
                          color: ch[bus.toLowerCase()] ? '#000' : ch.color,
                          fontFamily: 'var(--font-mono)', fontSize: '.38rem', padding: '1px 2px', cursor: 'pointer',
                        }}>{bus}</button>
                    ))}
                  </div>
                </div>
              )
            })}

            {/* Master section */}
            <div style={{
              display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6,
              minWidth: 68, padding: '8px 6px',
              background: 'var(--bg)', borderRadius: 'var(--radius)',
              border: `2px solid var(--gold)`,
              opacity: mixerConnected ? 1 : 0.5,
            }}>
              <div style={{ fontSize: '.44rem', fontFamily: 'var(--font-mono)', color: 'var(--gold)', textAlign: 'center' }}>MASTER</div>
              <VUMeter level={master.mute ? 0 : (master.vu || 0)} />
              <Fader label="OUT" value={master.gain} min={-60} max={12} color="var(--gold)"
                onChange={v => mixerConnected && updateMaster({ gain: v })} />
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 1 }}>
                <div style={{ position: 'relative' }}>
                  <KnobRing value={master.comp} max={100} color="var(--guest)" size={32} />
                  <input type="range" min={0} max={100} value={master.comp}
                    onChange={e => setMaster(m => ({ ...m, comp: +e.target.value }))}
                    style={{ position: 'absolute', inset: 0, opacity: 0, cursor: 'pointer', width: '100%', height: '100%' }} />
                </div>
                <div style={{ fontSize: '.38rem', color: 'var(--steel)', fontFamily: 'var(--font-mono)' }}>COMP</div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                <Toggle on={master.limiter} onClick={() => setMaster(m => ({ ...m, limiter: !m.limiter }))} color="var(--red)" />
                <span style={{ fontSize: '.38rem', color: 'var(--steel)', fontFamily: 'var(--font-mono)' }}>LIM</span>
              </div>
              <button disabled={!mixerConnected} onClick={() => mixerConnected && updateMaster({ mute: !master.mute })} style={{
                background: master.mute ? 'var(--red)' : 'var(--bg)',
                border: '1px solid var(--red)', borderRadius: 4,
                color: master.mute ? '#fff' : 'var(--red)',
                fontFamily: 'var(--font-mono)', fontSize: '.42rem', padding: '3px 8px', cursor: 'pointer', width: '100%',
              }}>MUTE ALL</button>
            </div>
          </div>
        </SectionCard>

        {/* Monitoring */}
        <SectionCard title="MONITORING & HEADPHONES" icon={Headphones} accent="var(--blue)" defaultOpen={true}
          style={{ gridColumn: 1 }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            {/* Monitor controls */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <div style={{ fontSize: '.5rem', color: 'var(--steel)', fontFamily: 'var(--font-mono)' }}>MONITOR OUTPUT</div>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <Knob label="VOLUME" value={monitor.volume} onChange={updateMonitorVolume} color="var(--blue)" />
                <Knob label="REVERB" value={monitor.comfortReverb} onChange={v => setMonitor(m => ({ ...m, comfortReverb: v }))} color="var(--guest)" />
              </div>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                {[
                  { key: 'dim',        label: 'DIM',        color: 'var(--gold)' },
                  { key: 'mono',       label: 'MONO',       color: 'var(--blue)' },
                  { key: 'talkback',   label: 'TALKBACK',   color: 'var(--red)'  },
                  { key: 'clickTrack', label: 'CLICK',      color: 'var(--green)'},
                ].map(({ key, label, color }) => (
                  <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                    <Toggle
                      on={monitor[key]}
                      onClick={() => {
                        if (key === 'mono') {
                          updateMonitorMono(!monitor.mono)
                        } else {
                          setMonitor(m => ({ ...m, [key]: !m[key] }))
                        }
                      }}
                      color={color}
                    />
                    <span style={{ fontSize: '.48rem', color: 'var(--steel)', fontFamily: 'var(--font-mono)' }}>{label}</span>
                  </div>
                ))}
              </div>
              {monitor.clickTrack && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <span style={{ fontSize: '.46rem', color: 'var(--steel)', fontFamily: 'var(--font-mono)' }}>CLICK LVL</span>
                  <input type="range" min={0} max={100} value={monitor.clickLevel}
                    onChange={e => setMonitor(m => ({ ...m, clickLevel: +e.target.value }))}
                    style={{ flex: 1, accentColor: 'var(--green)' }} />
                </div>
              )}
            </div>
            {/* Headphone mixes */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <div style={{ fontSize: '.5rem', color: 'var(--steel)', fontFamily: 'var(--font-mono)' }}>HEADPHONE MIXES</div>
              {[
                { key: 'philHP', label: 'PHIL HP', color: 'var(--phil)' },
                { key: 'jimHP',  label: 'JIM HP',  color: 'var(--jim)'  },
              ].map(({ key, label, color }) => (
                <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Headphones size={10} style={{ color }} />
                  <span style={{ fontSize: '.46rem', fontFamily: 'var(--font-mono)', color, width: 48, flexShrink: 0 }}>{label}</span>
                  <input type="range" min={0} max={100} value={monitor[key]}
                    onChange={e => setMonitor(m => ({ ...m, [key]: +e.target.value }))}
                    style={{ flex: 1, accentColor: color }} />
                  <span style={{ fontSize: '.46rem', fontFamily: 'var(--font-mono)', color, width: 24, textAlign: 'right' }}>
                    {monitor[key]}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </SectionCard>

        {/* Audacity / Recording chain */}
        <SectionCard title="AUDACITY — RECORDING CHAIN" icon={Mic2} accent="var(--guest)" defaultOpen={true}>
          <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start', flexWrap: 'wrap' }}>
            <div style={{ display: 'flex', gap: 8 }}>
              {[
                { key: 'inputGain',     label: 'INPUT\nGAIN',  color: 'var(--phil)' },
                { key: 'noiseReduction',label: 'NOISE\nREDUC', color: 'var(--blue)' },
                { key: 'compression',   label: 'COMP',         color: 'var(--guest)'},
                { key: 'eq',            label: 'EQ',           color: 'var(--gold)' },
                { key: 'deEss',         label: 'DE-ESS',       color: 'var(--jim)'  },
                { key: 'limiter',       label: 'LIMIT',        color: 'var(--red)'  },
              ].map(({ key, label, color }) => (
                <Knob key={key} label={label} value={audacity[key]} max={100} color={color}
                  onChange={v => setAudacity(a => ({ ...a, [key]: v }))} />
              ))}
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, justifyContent: 'center' }}>
              <button onClick={() => setAudacity(a => ({ ...a, recording: !a.recording }))} style={{
                display: 'flex', alignItems: 'center', gap: 6,
                background: audacity.recording ? 'var(--red)' : 'var(--bg)',
                border: '1px solid var(--red)', borderRadius: 'var(--radius)',
                color: audacity.recording ? '#fff' : 'var(--red)',
                fontFamily: 'var(--font-mono)', fontSize: '.55rem', padding: '8px 14px', cursor: 'pointer',
              }}>
                {audacity.recording ? <Square size={10} /> : <Circle size={10} />}
                {audacity.recording ? 'STOP' : 'RECORD'}
              </button>
              <div style={{ fontSize: '.44rem', color: 'var(--steel)', fontFamily: 'var(--font-mono)', lineHeight: 1.6 }}>
                <div>Pre-processing chain</div>
                <div style={{ color: 'var(--bone)' }}>ReaFIR → ReaComp → ReaEQ</div>
                <div style={{ color: 'var(--bone)' }}>Spitfish → LoudMax</div>
              </div>
            </div>
          </div>
        </SectionCard>
          </>
        )}

        {studioView === 'obs' && (
          <>
        {/* ════════════════════════════════════════════════════════════
            COL 2 — OBS / VIDEO
        ════════════════════════════════════════════════════════════ */}

        {/* OBS Scene switcher */}
        <SectionCard title="OBS — SCENE SWITCHER" icon={Monitor} accent="var(--blue)" defaultOpen={true}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 5, marginBottom: 8 }}>
            {obs.scenes.map(scene => (
              <button key={scene}
                onClick={() => setProgramScene(scene)}
                disabled={obsBusy || !obs.connected}
                style={{
                  background: obs.activeScene === scene ? 'var(--blue)' : 'var(--bg)',
                  border: `1px solid ${obs.activeScene === scene ? 'var(--blue)' : 'var(--rim)'}`,
                  borderRadius: 'var(--radius)', padding: '6px 8px',
                  color: obs.activeScene === scene ? '#fff' : 'var(--steel)',
                  fontFamily: 'var(--font-mono)', fontSize: '.52rem',
                  cursor: 'pointer', transition: 'all .15s', textAlign: 'left',
                  opacity: (obsBusy || !obs.connected) ? 0.5 : 1,
                }}>
                {obs.activeScene === scene && '▶ '}{scene}
              </button>
            ))}
          </div>
          {obs.scenes.length === 0 && (
            <div style={{ fontSize: '.48rem', color: 'var(--steel)', fontFamily: 'var(--font-mono)', marginBottom: 8 }}>
              No OBS scenes available.
            </div>
          )}
          {/* Transition */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
            <span style={{ fontSize: '.48rem', color: 'var(--steel)', fontFamily: 'var(--font-mono)' }}>TRANSITION</span>
            <div style={{ display: 'flex', gap: 4 }}>
              {obs.transitions.map(t => (
                <button key={t} onClick={() => setObs(o => ({ ...o, transition: t }))} style={{
                  background: obs.transition === t ? 'var(--gold)' : 'var(--bg)',
                  border: `1px solid ${obs.transition === t ? 'var(--gold)' : 'var(--rim)'}`,
                  borderRadius: 4, padding: '2px 7px',
                  color: obs.transition === t ? '#000' : 'var(--steel)',
                  fontFamily: 'var(--font-mono)', fontSize: '.44rem', cursor: 'pointer',
                }}>{t}</button>
              ))}
            </div>
          </div>
          {/* OBS controls */}
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {[
              { key: 'virtualCam', label: 'VIRTUAL CAM (SIM)', color: 'var(--green)' },
            ].map(({ key, label, color }) => (
              <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <Toggle on={obs[key]} onClick={() => setObs(o => ({ ...o, [key]: !o[key] }))} color={color} />
                <span style={{ fontSize: '.48rem', color: 'var(--steel)', fontFamily: 'var(--font-mono)' }}>{label}</span>
              </div>
            ))}
          </div>
        </SectionCard>

        {/* OBS Audio levels */}
        <SectionCard title="OBS — AUDIO SOURCES" icon={Volume2} accent="var(--blue)" defaultOpen={true}>
          <div style={{ fontSize: '.44rem', color: 'var(--steel)', fontFamily: 'var(--font-mono)', marginBottom: 6 }}>
            {mixerConnected ? 'LIVE: levels mirrored from Voicemeeter.' : 'OFFLINE: waiting on Voicemeeter levels.'}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {[
              { label: 'MIC PHIL',    level: channels.mic1.mute  ? 0 : channels.mic1.vu,  color: 'var(--phil)' },
              { label: 'MIC JIM',     level: channels.mic2.mute  ? 0 : channels.mic2.vu,  color: 'var(--jim)'  },
              { label: 'MUSIC BED',   level: channels.music.mute ? 0 : channels.music.vu, color: 'var(--steel)'},
              { label: 'SFX',         level: channels.sfx.mute   ? 0 : channels.sfx.vu,   color: 'var(--ad)'   },
              { label: 'MASTER OUT',  level: master.mute         ? 0 : (master.vu || 0), color: 'var(--gold)' },
            ].map(({ label, level, color }) => (
              <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{ fontSize: '.46rem', fontFamily: 'var(--font-mono)', color: 'var(--steel)', width: 64, flexShrink: 0 }}>{label}</span>
                <div style={{ flex: 1, height: 6, background: 'var(--rim)', borderRadius: 3, overflow: 'hidden' }}>
                  <div style={{
                    height: '100%', width: pct(level), background: color,
                    borderRadius: 3, transition: 'width .1s',
                  }} />
                </div>
                <span style={{ fontSize: '.46rem', fontFamily: 'var(--font-mono)', color, width: 24, textAlign: 'right' }}>
                  {Math.round(level)}
                </span>
              </div>
            ))}
          </div>
        </SectionCard>

        {/* Stream info */}
        <SectionCard title="STREAM STATUS" icon={Radio} accent="var(--red)" defaultOpen={true}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
            {[
              { label: 'PLATFORM',    value: stream.platform,          color: 'var(--gold)' },
              { label: 'STATUS',      value: obs.streaming ? 'LIVE 🔴' : 'OFF AIR', color: obs.streaming ? 'var(--red)' : 'var(--steel)' },
              { label: 'OBS WS',      value: obs.connected ? 'CONNECTED' : 'OFFLINE', color: obs.connected ? 'var(--green)' : 'var(--red)' },
              { label: 'DURATION',    value: fmtTime(stream.duration), color: 'var(--bone)' },
              { label: 'BITRATE',     value: stream.bitrate === '--' ? '--' : `${stream.bitrate} kbps`, color: 'var(--blue)' },
              { label: 'FPS',         value: stream.fps,               color: 'var(--green)' },
              { label: 'RESOLUTION',  value: stream.resolution,        color: 'var(--bone)' },
            ].map(({ label, value, color }) => (
              <div key={label} style={{ background: 'var(--bg)', borderRadius: 'var(--radius)', padding: '6px 8px' }}>
                <div style={{ fontSize: '.42rem', color: 'var(--steel)', fontFamily: 'var(--font-mono)', marginBottom: 2 }}>{label}</div>
                <div style={{ fontSize: '.65rem', color, fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{value}</div>
              </div>
            ))}
          </div>
        </SectionCard>
          </>
        )}

        {studioView === 'cams' && (
          <>
        {/* ════════════════════════════════════════════════════════════
            COL 3 — CAMERAS + MACROS
        ════════════════════════════════════════════════════════════ */}

        {/* PTZ Camera controls */}
        <SectionCard title="PTZ CAMERAS" icon={Camera} accent="var(--guest)" defaultOpen={true}>
          <div style={{ fontSize: '.44rem', color: 'var(--steel)', fontFamily: 'var(--font-mono)', marginBottom: 6 }}>
            SIMULATED: waiting on backend PTZ route.
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {Object.entries(cameras).map(([k, cam]) => (
              <div key={k} style={{
                padding: '8px', borderRadius: 'var(--radius)',
                border: `1px solid ${cam.active ? 'var(--guest)' : 'var(--rim)'}`,
                background: cam.active ? 'rgba(192,132,252,0.05)' : 'var(--bg)',
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: '.55rem', color: cam.active ? 'var(--guest)' : 'var(--steel)' }}>
                    {cam.label} {cam.active && '● LIVE'}
                  </span>
                  <Toggle on={cam.active} onClick={() => {
                    setCameras(p => {
                      const n = { ...p }
                      Object.keys(n).forEach(ck => n[ck] = { ...n[ck], active: false })
                      n[k] = { ...n[k], active: true }
                      return n
                    })
                    const sceneName = cam.label === 'MAIN' ? 'MAIN CAM' : `${cam.label} CAM`
                    if (obs.connected && obs.scenes.includes(sceneName)) {
                      void setProgramScene(sceneName)
                    } else {
                      setObs(o => ({ ...o, activeScene: sceneName }))
                    }
                  }} color="var(--guest)" />
                </div>
                {[
                  { key: 'zoom',     label: 'ZOOM',     color: 'var(--blue)'  },
                  { key: 'focus',    label: 'FOCUS',    color: 'var(--green)' },
                  { key: 'exposure', label: 'EXPOSURE', color: 'var(--gold)'  },
                ].map(({ key, label, color }) => (
                  <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: 3 }}>
                    <span style={{ fontSize: '.42rem', color: 'var(--steel)', fontFamily: 'var(--font-mono)', width: 44, flexShrink: 0 }}>{label}</span>
                    <input type="range" min={0} max={100} value={cam[key]}
                      onChange={e => updateCamera(k, { [key]: +e.target.value })}
                      style={{ flex: 1, accentColor: color, height: 3 }} />
                    <span style={{ fontSize: '.42rem', color, fontFamily: 'var(--font-mono)', width: 20, textAlign: 'right' }}>
                      {cam[key]}
                    </span>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </SectionCard>
          </>
        )}

        {studioView === 'automate' && (
          <>
        {/* Macro buttons */}
        <SectionCard title="MACRO BUTTONS" icon={Zap} accent="var(--gold)" defaultOpen={true}>
          <div style={{ fontSize: '.44rem', color: 'var(--steel)', fontFamily: 'var(--font-mono)', marginBottom: 6 }}>
            LIVE: macro actions use OBS and mixer endpoints when available.
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 5 }}>
            {macros.map(m => (
              <MacroBtn key={m.id} label={m.label} color={m.color}
                active={!!activeMacros[m.id]}
                disabled={macroBusy}
                onClick={() => void triggerMacro(m.id)} />
            ))}
          </div>
        </SectionCard>

        {/* Quick commands */}
        <SectionCard title="QUICK HEALTH COMMANDS" icon={Activity} accent="var(--green)" defaultOpen={false}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {[
              { label: 'Backend health',      cmd: `curl.exe ${window.location.origin}/api/health` },
              { label: 'Voice list',          cmd: `curl.exe ${window.location.origin}/api/voices` },
              { label: 'OBS WebSocket check', cmd: 'curl http://localhost:4455' },
              { label: 'Mixer API status',    cmd: `curl.exe ${window.location.origin}/api/mixer/status` },
              { label: 'Audio device list',   cmd: 'python -m sounddevice' },
              { label: 'ffprobe audio',       cmd: 'ffprobe episodes/demo_podcast_gen/audio.mp3' },
              { label: 'Produce offline',     cmd: 'python staging/produce_demo.py' },
              { label: 'Stream Deck check',   cmd: 'curl http://localhost:23654' },
            ].map(({ label, cmd }) => (
              <div key={label} style={{
                background: 'var(--bg)', border: '1px solid var(--rim)',
                borderRadius: 'var(--radius)', padding: '6px 10px',
                cursor: 'pointer',
              }}
                onClick={() => navigator.clipboard?.writeText(cmd)}
                title="Click to copy"
              >
                <div style={{ fontSize: '.44rem', color: 'var(--steel)', fontFamily: 'var(--font-mono)', marginBottom: 2 }}>{label}</div>
                <div style={{ fontSize: '.52rem', color: 'var(--gold)', fontFamily: 'var(--font-mono)', wordBreak: 'break-all' }}>{cmd}</div>
              </div>
            ))}
          </div>
        </SectionCard>
          </>
        )}

      </div>
    </div>
  )
}
