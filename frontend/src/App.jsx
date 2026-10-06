// App.jsx — Dandy Studio root
import { useState, useEffect } from 'react'
import { Mic2, Radio, Image, Settings, Sliders, Trash2 } from 'lucide-react'
import EpisodeTab from './components/EpisodeTab'
import AdTab      from './components/AdTab'
import SocialTab  from './components/SocialTab'
import SystemTab  from './components/SystemTab'
import StudioConsole from './components/StudioConsole'
import { api, req } from './lib/api'

const TABS = [
  { id: 'episodes', label: 'EPISODES',  icon: Radio,    component: EpisodeTab },
  { id: 'ads',      label: 'ADS',       icon: Mic2,     component: AdTab      },
  { id: 'social',   label: 'SOCIAL',    icon: Image,    component: SocialTab  },
  { id: 'studio',   label: 'STUDIO',    icon: Sliders,  component: StudioConsole },
  { id: 'system',   label: 'SYSTEM',    icon: Settings, component: SystemTab  },
]

export default function App() {
  const [activeTab, setActiveTab]     = useState('studio')
  const [backendOk, setBackendOk]     = useState(null)   // null = checking
  const [episodeId, setEpisodeId] = useState(null)
  const [deletingEpisode, setDeletingEpisode] = useState(false)

  useEffect(() => {
    let active = true
    const check = () => api.health().then(() => { if (active) setBackendOk(true) }).catch(() => { if (active) setBackendOk(false) })
    check()
    const interval = setInterval(check, 30000)
    return () => { active = false; clearInterval(interval) }
  }, [])

  const deleteSelectedEpisode = async () => {
    if (!episodeId || deletingEpisode) return
    if (!window.confirm(`Delete episode ${episodeId}?\n\nThis removes the episode folder, draft, and matching job records. This cannot be undone.`)) return
    setDeletingEpisode(true)
    try {
      await req(`/episodes/${encodeURIComponent(episodeId)}`, { method: 'DELETE' })
      setEpisodeId(null)
      window.location.reload()
    } catch (error) {
      window.alert(`Delete failed: ${error.message}`)
      setDeletingEpisode(false)
    }
  }

  const ActiveComponent = TABS.find(t => t.id === activeTab)?.component || EpisodeTab

  return (
    <div className="app-shell">

      {/* ── Top nav ── */}
      <nav className="top-nav">
        <div className="nav-logo" title="Dandy Studio V3">
          <img
            className="nav-logo-image"
            src="/dandy-show-phil-jim.png?v=2"
            alt="The Dandy Show Phil and Jim"
          />
        </div>

        <div className="tab-bar">
          {TABS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              className={`tab-btn${activeTab === id ? ' active' : ''}`}
              onClick={() => setActiveTab(id)}
            >
              <Icon size={12} />
              {label}
            </button>
          ))}
        </div>

        <div className="nav-status">
          {activeTab === 'episodes' && episodeId && (
            <button
              className="btn btn-sm"
              type="button"
              onClick={deleteSelectedEpisode}
              disabled={deletingEpisode}
              title={`Delete episode ${episodeId}`}
              style={{
                marginRight: 12,
                border: '1px solid rgba(239,68,68,.65)',
                color: '#f87171',
                background: 'rgba(127,29,29,.18)',
              }}
            >
              <Trash2 size={11} /> {deletingEpisode ? 'DELETING…' : 'DELETE EPISODE'}
            </button>
          )}
          <span style={{ color: 'var(--gold)', marginRight: 10, letterSpacing: '.08em' }}>DANDY STUDIO V3</span>
          <div className={`status-dot${backendOk === true ? ' ok' : backendOk === false ? ' err' : ''}`} />
          <span>
            {backendOk === null  ? 'checking…' :
             backendOk === true  ? 'api online' :
                                   'api offline'}
          </span>
        </div>
      </nav>

      {/* ── Active tab ── */}
      <ActiveComponent episodeId={episodeId} onEpisodeChange={setEpisodeId} />
    </div>
  )
}
