import { useEffect, useMemo, useState } from 'react'
import { Play, Search, X } from 'lucide-react'
import { api } from '../lib/api'
import { Spinner } from './ui'

const AUDIO_ROLES = new Set(['music', 'jingle', 'sfx', 'ad', 'voice'])
const ROLE_LABELS = {
  music: 'Music',
  jingle: 'Jingles / Stingers',
  sfx: 'Sound Effects',
  ad: 'Ad Audio',
  voice: 'Voice Clips',
}

function formatBytes(value) {
  const n = Number(value || 0)
  if (!n) return ''
  if (n >= 1024 ** 2) return `${(n / 1024 ** 2).toFixed(1)} MB`
  if (n >= 1024) return `${Math.round(n / 1024)} KB`
  return `${n} B`
}

export default function AudioAssetPicker({ value = '', onChange, label = 'Audio asset' }) {
  const [assets, setAssets] = useState([])
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [previewId, setPreviewId] = useState('')

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const result = await api.listAssetLibrary()
      const rows = (result?.assets || []).filter(item => item.asset_type === 'audio' && AUDIO_ROLES.has(item.role))
      setAssets(rows)
    } catch (e) {
      setError(e.message || 'Could not load audio assets')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return assets
    return assets.filter(item => [item.label, item.filename, item.relative_path, item.role]
      .some(value => String(value || '').toLowerCase().includes(q)))
  }, [assets, query])

  const grouped = useMemo(() => {
    const map = new Map()
    for (const item of filtered) {
      if (!map.has(item.role)) map.set(item.role, [])
      map.get(item.role).push(item)
    }
    return map
  }, [filtered])

  const selected = assets.find(item => item.relative_path === value)

  return (
    <div className="field">
      <div className="field-label">{label}</div>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
        <div style={{ position: 'relative', flex: 1 }}>
          <Search size={13} style={{ position: 'absolute', left: 9, top: 9, color: 'var(--steel)' }} />
          <input
            className="ds-input"
            value={query}
            onChange={event => setQuery(event.target.value)}
            placeholder="Search music, jingles, SFX, ad audio, voice clips…"
            style={{ paddingLeft: 30 }}
          />
        </div>
        <button className="btn btn-steel btn-sm" type="button" onClick={load} disabled={loading}>
          {loading ? <Spinner /> : 'REFRESH'}
        </button>
      </div>

      {value && <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8, fontSize: '.72rem' }}>
        <span style={{ color: 'var(--gold)' }}>Selected:</span>
        <span style={{ overflowWrap: 'anywhere' }}>{selected?.label || value}</span>
        <button className="icon-btn" type="button" title="Clear selection" onClick={() => onChange('')}><X size={12} /></button>
      </div>}

      {error && <div style={{ color: 'var(--red)', fontSize: '.72rem', marginBottom: 8 }}>{error}</div>}
      {!loading && !error && filtered.length === 0 && <div style={{ fontSize: '.72rem', color: 'var(--steel)', padding: '8px 0' }}>No matching audio assets found.</div>}

      {filtered.length > 0 && <div style={{ maxHeight: 280, overflow: 'auto', border: '1px solid var(--line)', borderRadius: 4 }}>
        {[...grouped.entries()].map(([role, items]) => <div key={role}>
          <div style={{ position: 'sticky', top: 0, zIndex: 1, padding: '6px 10px', background: 'var(--panel-2)', color: 'var(--gold)', fontSize: '.68rem', fontWeight: 700, letterSpacing: '.08em' }}>
            {ROLE_LABELS[role] || role.toUpperCase()} · {items.length}
          </div>
          {items.map(item => {
            const active = item.relative_path === value
            return <div key={item.asset_id} style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) auto auto', gap: 8, alignItems: 'center', padding: '8px 10px', borderTop: '1px solid var(--line)', background: active ? 'rgba(199,153,54,.08)' : 'transparent' }}>
              <button type="button" onClick={() => onChange(item.relative_path)} style={{ minWidth: 0, border: 0, background: 'transparent', color: 'inherit', textAlign: 'left', cursor: 'pointer', padding: 0 }}>
                <div style={{ fontSize: '.76rem', color: active ? 'var(--gold)' : 'var(--text)' }}>{item.label || item.filename}</div>
                <div className="font-mono" style={{ fontSize: '.6rem', color: 'var(--steel)', overflowWrap: 'anywhere' }}>{item.relative_path}</div>
              </button>
              <span style={{ fontSize: '.62rem', color: 'var(--steel)', whiteSpace: 'nowrap' }}>{formatBytes(item.size_bytes)}</span>
              <button className="icon-btn" type="button" title="Preview audio" onClick={() => setPreviewId(previewId === item.asset_id ? '' : item.asset_id)}><Play size={12} /></button>
              {previewId === item.asset_id && <div style={{ gridColumn: '1 / -1' }}><audio controls autoPlay src={api.libraryAssetUrl(item.asset_id)} style={{ width: '100%' }} /></div>}
            </div>
          })}
        </div>)}
      </div>}
    </div>
  )
}
