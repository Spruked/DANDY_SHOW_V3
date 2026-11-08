import { useState } from 'react'
import {
  Mic, Mic2, Volume2, VolumeX, Radio, Monitor, Camera,
  Headphones, Settings, Activity, Zap, ToggleLeft, ToggleRight,
  Sliders, Speaker, Eye, EyeOff, RefreshCw, ChevronDown, ChevronUp,
  Cpu, Globe, Wifi, AlertCircle, CheckCircle, XCircle, Music,
  Video, Layers, Play, Square, Circle, SkipForward, Download
} from 'lucide-react'

const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v))
const pct = v => `${clamp(v, 0, 100)}%`
export function Toggle({ on, onClick, color = 'var(--gold)' }) {
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

export function Fader({ label, value, onChange, color = 'var(--gold)', unit = 'dB', min = -60, max = 12 }) {
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

export function KnobRing({ value, max = 100, color = 'var(--gold)', size = 48 }) {
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

export function Knob({ label, value, onChange, max = 100, color = 'var(--gold)' }) {
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

export function VUMeter({ level = 0, label = '' }) {
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

export function SectionCard({ title, icon: Icon, children, accent = 'var(--gold)', defaultOpen = true, style = {} }) {
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

export function StatusPill({ ok, label }) {
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

export function MacroBtn({ label, color = 'var(--gold)', onClick, active = false, disabled = false }) {
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
