// App.jsx — Dandy Studio root
import { useState, useEffect } from 'react'
import { Mic2, Radio, Image, Settings, Sliders } from 'lucide-react'
import EpisodeTab from './components/EpisodeTab'
import AdTab      from './components/AdTab'
import SocialTab  from './components/SocialTab'
import SystemTab  from './components/SystemTab'
import StudioConsole from './components/StudioConsole'
import { api }    from './lib/api'

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

  useEffect(() => {
    api.health()
      .then(() => setBackendOk(true))
      .catch(() => setBackendOk(false))
  }, [])

  const ActiveComponent = TABS.find(t => t.id === activeTab)?.component || EpisodeTab

  return (
    <div className="app-shell">

      {/* ── Top nav ── */}
      <nav className="top-nav">
        <div className="nav-logo">
          <div className="nav-logo-mark">D</div>
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
          <div className={`status-dot${backendOk === true ? ' ok' : backendOk === false ? ' err' : ''}`} />
          <span>
            {backendOk === null  ? 'checking…' :
             backendOk === true  ? 'api online' :
                                   'api offline'}
          </span>
        </div>
      </nav>

      {/* ── Active tab ── */}
      <ActiveComponent />
    </div>
  )
}
