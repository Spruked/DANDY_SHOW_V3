// SocialTab.jsx — sub-tab router for Exports / Slideshow / Ad Cards
import { useState, useEffect } from 'react'
import ExportsMode from './ExportsMode'
import SlideshowBuilder from './SlideshowBuilder'
import AdCardsBuilder from './AdCardsBuilder'
import { api } from '../lib/api'

const MODES = [
  { id: 'exports',   label: 'EXPORTS'   },
  { id: 'slideshow', label: 'SLIDESHOW' },
  { id: 'adcards',   label: 'AD CARDS'  },
]

// Maps brand asset slots to the shape builders expect: {id, filename, name}
const ASSET_SLOTS = [
  { id: 'thumbnail_base',   filename: 'thumbnail_base.png',   name: 'Thumbnail Base'   },
  { id: 'waveform_base',    filename: 'waveform_base.png',    name: 'Waveform Base'    },
  { id: 'alternate_cover',  filename: 'alternate_cover.png',  name: 'Alternate Cover'  },
  { id: 'character_logo',   filename: 'character_logo.png',   name: 'Character Logo'   },
  { id: 'segment_tech_talk',filename: 'segment_tech_talk.png',name: 'Tech Talk Card'   },
  { id: 'logo',             filename: 'logo.png',             name: 'Logo Mark'        },
]

export default function SocialTab({ episodeId, onEpisodeChange }) {
  const [mode, setMode] = useState('exports')
  const [episodes, setEpisodes] = useState([])
  const [activeEp, setActiveEp] = useState(null)
  const [assetSlots, setAssetSlots] = useState([])

  useEffect(() => {
    api.listEpisodes()
      .then(data => {
        const list = Array.isArray(data) ? data : (data.episodes || [])
        setEpisodes(list)
        if (list.length) setActiveEp(list.find(ep => (ep.episode_id || ep.id) === episodeId) || list[0])
      })
      .catch(() => {})
    fetch('/api/social/assets').then(r => { if (!r.ok) throw new Error('Asset check failed'); return r.json() }).then(data => setAssetSlots(data.assets || [])).catch(() => {})
  }, [])

  const epId = activeEp?.episode_id || activeEp?.id
  const episode = activeEp ? { ...activeEp, id: epId } : null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>

      {/* Sub-tab mode bar */}
      <div style={{
        display: 'flex', gap: 2, padding: '6px 14px',
        borderBottom: '1px solid var(--rim)', flexShrink: 0,
      }}>
        {MODES.map(m => (
          <button
            key={m.id}
            onClick={() => setMode(m.id)}
            style={{
              padding: '3px 14px', fontSize: '.65rem', fontFamily: 'var(--font-display)',
              letterSpacing: '.08em', cursor: 'pointer', border: '1px solid',
              borderRadius: 'var(--radius)',
              borderColor: mode === m.id ? 'var(--gold)' : 'var(--rim)',
              background: mode === m.id ? 'var(--gold)' : 'transparent',
              color: mode === m.id ? '#0e1116' : 'var(--steel)',
            }}
          >
            {m.label}
          </button>
        ))}
      </div>

      {/* Episode selector — shown in builder modes */}
      {mode !== 'exports' && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8,
          padding: '5px 14px', borderBottom: '1px solid var(--rim)', flexShrink: 0,
        }}>
          <span style={{ fontSize: '.62rem', color: 'var(--steel)', whiteSpace: 'nowrap' }}>EPISODE</span>
          <select
            className="ds-select"
            style={{ flex: 1, maxWidth: 340 }}
            value={epId || ''}
            onChange={e => { onEpisodeChange?.(e.target.value); setActiveEp(episodes.find(ep => (ep.episode_id || ep.id) === e.target.value) || null) }}
          >
            {!episodes.length && <option value="">No episodes</option>}
            {episodes.map(ep => {
              const id = ep.episode_id || ep.id
              return <option key={id} value={id}>{ep.title || id}</option>
            })}
          </select>
        </div>
      )}

      {/* Mode body */}
      <div style={{ flex: 1, overflow: 'hidden' }}>
        {mode === 'exports'   && <ExportsMode episodeId={episodeId || epId} onEpisodeChange={id => { onEpisodeChange?.(id); setActiveEp(episodes.find(ep => (ep.episode_id || ep.id) === id) || null) }} />}
        {mode === 'slideshow' && <SlideshowBuilder key={epId || "none"} episode={episode} assetSlots={assetSlots} />}
        {mode === 'adcards'   && <AdCardsBuilder key={epId || "global"} episode={episode} assetSlots={assetSlots} />}
      </div>

    </div>
  )
}
