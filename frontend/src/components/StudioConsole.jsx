import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Sliders, Cpu, Monitor, Camera, Zap, Mic2, RefreshCw,
  Square, CheckCircle, AlertCircle, Headphones,
} from 'lucide-react'

import StudioTab from './StudioTab'
import './studio-console.css'


const STUDIO_VIEWS = [
  { id: 'audio', label: 'AUDIO MIX', icon: Sliders, legacyLabel: 'AUDIO MIX' },
  { id: 'qwen', label: 'QWEN TTS', icon: Cpu },
  { id: 'obs', label: 'OBS LIVE', icon: Monitor, legacyLabel: 'OBS LIVE' },
  { id: 'cams', label: 'CAMERAS', icon: Camera, legacyLabel: 'CAMERAS' },
  { id: 'automate', label: 'MACROS / TOOLS', icon: Zap, legacyLabel: 'MACROS / TOOLS' },
]

const QWEN_TABS = [
  { id: 'voice-lab', label: 'DANDY VOICE LAB' },
  { id: 'custom', label: 'CUSTOMVOICE', mode: 'custom' },
  { id: 'clone', label: 'VOICE CLONE', mode: 'clone' },
  { id: 'design', label: 'VOICEDESIGN', mode: 'design' },
  { id: 'tools', label: 'AUDIO / TOOLS' },
]

const MODE_ORDER = ['custom', 'clone', 'design']


function studioFetch(path, options = {}) {
  return fetch(`/api/qwen-studio${path}`, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  }).then(async (res) => {
    let payload = {}
    try {
      payload = await res.json()
    } catch {
      payload = {}
    }
    if (!res.ok) {
      throw new Error(payload.detail || `HTTP ${res.status}`)
    }
    return payload
  })
}


function LegacyStudioView({ view }) {
  const hostRef = useRef(null)

  useEffect(() => {
    const target = STUDIO_VIEWS.find((item) => item.id === view)?.legacyLabel
    if (!target || !hostRef.current) return undefined

    const timer = window.setTimeout(() => {
      const navButtons = Array.from(
        hostRef.current.querySelectorAll('.tab-body > div:nth-child(2) button')
      )
      const button = navButtons.find((item) => (
        item.textContent.replace(/\s+/g, ' ').trim() === target
      ))
      if (button) button.click()
    }, 0)

    return () => window.clearTimeout(timer)
  }, [view])

  return (
    <div ref={hostRef} className={`legacy-studio legacy-${view}`}>
      <StudioTab />
    </div>
  )
}


function QwenStatusLight({ ready, busy }) {
  const className = ready ? 'ready' : busy ? 'busy' : 'offline'
  const Icon = ready ? CheckCircle : AlertCircle
  return (
    <span className={`qwen-status-light ${className}`}>
      <Icon size={13} />
      {ready ? 'READY' : busy ? 'LOADING' : 'OFFLINE'}
    </span>
  )
}


function QwenStudio() {
  const [status, setStatus] = useState(null)
  const [activeTab, setActiveTab] = useState('custom')
  const [error, setError] = useState('')
  const [actionBusy, setActionBusy] = useState(false)
  const requestedModeRef = useRef(null)

  const refresh = useCallback(async () => {
    try {
      const data = await studioFetch('/status')
      setStatus(data)
      if (requestedModeRef.current && data?.modes?.[requestedModeRef.current]?.ready) {
        requestedModeRef.current = null
      }
      setError('')
      return data
    } catch (err) {
      setError(err?.message || 'Qwen Studio status unavailable')
      return null
    }
  }, [])

  useEffect(() => {
    void refresh()
    const timer = window.setInterval(() => void refresh(), 1500)
    return () => window.clearInterval(timer)
  }, [refresh])

  const startMode = useCallback(async (mode, force = false) => {
    if (!mode) return
    if (!force && status?.modes?.[mode]?.ready) return
    if (!force && requestedModeRef.current === mode) return

    requestedModeRef.current = mode
    setActionBusy(true)
    setError('')
    try {
      const data = await studioFetch(`/mode/${mode}/start`, { method: 'POST' })
      if (data?.status) setStatus(data.status)
    } catch (err) {
      requestedModeRef.current = null
      setError(err?.message || `Could not start Qwen ${mode}`)
    } finally {
      setActionBusy(false)
    }
  }, [status])

  const stopAll = useCallback(async () => {
    setActionBusy(true)
    setError('')
    requestedModeRef.current = null
    try {
      await studioFetch('/stop', { method: 'POST' })
      window.setTimeout(() => void refresh(), 800)
    } catch (err) {
      setError(err?.message || 'Could not stop Qwen')
    } finally {
      setActionBusy(false)
    }
  }, [refresh])

  const selectQwenTab = useCallback((tab) => {
    setActiveTab(tab.id)
    if (tab.mode) void startMode(tab.mode)
  }, [startMode])

  useEffect(() => {
    const tab = QWEN_TABS.find((item) => item.id === activeTab)
    if (tab?.mode && status && !status?.modes?.[tab.mode]?.ready) {
      void startMode(tab.mode)
    }
  }, [activeTab, startMode, status])

  const selectedMode = QWEN_TABS.find((item) => item.id === activeTab)?.mode || null
  const selectedConfig = selectedMode ? status?.modes?.[selectedMode] : null
  const selectedReady = Boolean(selectedConfig?.ready)
  const launcherBusy = Boolean(status?.launcher?.busy)

  const activeModeLabel = useMemo(() => {
    if (status?.multiple_modes_active) return 'MULTIPLE MODE LISTENERS'
    if (!status?.active_mode) return launcherBusy ? 'MODEL LOADING' : 'NO QWEN MODEL LOADED'
    return status?.modes?.[status.active_mode]?.label || status.active_mode.toUpperCase()
  }, [launcherBusy, status])

  return (
    <div className="qwen-console">
      <div className="qwen-console-head">
        <div>
          <div className="qwen-eyebrow">WINDOWS-NATIVE · LOCAL QWEN3-TTS · RTX 3050</div>
          <div className="qwen-title">DANDY QWEN TTS CONTROL</div>
          <div className="qwen-subtitle">
            One heavy Qwen model at a time. Switching tabs unloads the current mode and loads the selected mode.
          </div>
        </div>

        <div className="qwen-engine-actions">
          <div className="qwen-active-model">
            <span>ACTIVE</span>
            <strong>{activeModeLabel}</strong>
          </div>
          <button className="studio-action secondary" onClick={() => void refresh()} disabled={actionBusy}>
            <RefreshCw size={13} /> REFRESH
          </button>
          <button className="studio-action danger" onClick={() => void stopAll()} disabled={actionBusy}>
            <Square size={12} /> STOP QWEN
          </button>
        </div>
      </div>

      {error && <div className="qwen-error">{error}</div>}

      <div className="qwen-mode-strip">
        {MODE_ORDER.map((mode) => {
          const cfg = status?.modes?.[mode]
          return (
            <button
              key={mode}
              className={`qwen-mode-card${status?.active_mode === mode ? ' active' : ''}`}
              onClick={() => {
                setActiveTab(mode)
                void startMode(mode)
              }}
              disabled={actionBusy}
            >
              <div className="qwen-mode-card-head">
                <span>{cfg?.label || mode.toUpperCase()}</span>
                <QwenStatusLight ready={Boolean(cfg?.ready)} busy={launcherBusy && status?.launcher?.mode === mode} />
              </div>
              <div className="qwen-mode-port">{cfg?.port || (mode === 'custom' ? 8031 : mode === 'clone' ? 8032 : 8033)}</div>
            </button>
          )
        })}
      </div>

      <div className="qwen-tab-bar">
        {QWEN_TABS.map((tab) => (
          <button
            key={tab.id}
            className={`qwen-tab${activeTab === tab.id ? ' active' : ''}`}
            onClick={() => selectQwenTab(tab)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="qwen-workspace">
        {activeTab === 'voice-lab' && (
          <div className="voice-lab-grid">
            <div className="voice-lab-card phil">
              <div className="voice-lab-kicker">PHIL DANDY</div>
              <h3>VOICE IDENTITY LAB</h3>
              <p>
                Build Phil from a clean original reference clip with Qwen Base, save the approved clone prompt,
                then use Dandy's established Phil delivery and pacing on top of that identity.
              </p>
              <button className="studio-action primary" onClick={() => selectQwenTab(QWEN_TABS.find((t) => t.id === 'clone'))}>
                <Mic2 size={13} /> LOAD VOICE CLONE
              </button>
            </div>

            <div className="voice-lab-card jim">
              <div className="voice-lab-kicker">JIM DANDY</div>
              <h3>VOICE IDENTITY LAB</h3>
              <p>
                Build Jim from his original reference audio, save the approved reusable prompt, and preserve the
                slower, deliberate Jim delivery in the Dandy production layer.
              </p>
              <button className="studio-action primary" onClick={() => selectQwenTab(QWEN_TABS.find((t) => t.id === 'clone'))}>
                <Mic2 size={13} /> LOAD VOICE CLONE
              </button>
            </div>

            <div className="voice-lab-wide">
              <Headphones size={18} />
              <div>
                <strong>VOICE WORKFLOW</strong>
                <span>Reference audio → exact transcript → Qwen Base clone → compare → save approved prompt → Dandy Show voice.</span>
              </div>
            </div>
          </div>
        )}

        {selectedMode && (
          selectedReady ? (
            <iframe
              key={`${selectedMode}-${selectedConfig?.url}`}
              className="qwen-native-frame"
              src={selectedConfig.url}
              title={`Qwen ${selectedConfig.label}`}
              allow="microphone; clipboard-read; clipboard-write; autoplay"
            />
          ) : (
            <div className="qwen-loading-panel">
              <Cpu size={32} />
              <h3>LOADING {selectedConfig?.label || selectedMode.toUpperCase()}</h3>
              <p>
                Dandy is switching the GPU to the required Qwen checkpoint. The native Gradio page will appear here automatically when the listener is ready.
              </p>
              <QwenStatusLight ready={false} busy={launcherBusy || requestedModeRef.current === selectedMode} />
              <button className="studio-action primary" onClick={() => void startMode(selectedMode)} disabled={actionBusy || launcherBusy}>
                START {selectedConfig?.label || selectedMode.toUpperCase()}
              </button>
            </div>
          )
        )}

        {activeTab === 'tools' && (
          <div className="qwen-tools-grid">
            {MODE_ORDER.map((mode) => {
              const cfg = status?.modes?.[mode]
              return (
                <div key={mode} className="qwen-tool-card">
                  <div>
                    <strong>{cfg?.label || mode.toUpperCase()}</strong>
                    <span>{cfg?.checkpoint || 'Qwen3-TTS checkpoint'}</span>
                  </div>
                  <QwenStatusLight ready={Boolean(cfg?.ready)} busy={launcherBusy && status?.launcher?.mode === mode} />
                  <button className="studio-action secondary" onClick={() => {
                    setActiveTab(mode)
                    void startMode(mode)
                  }}>
                    LOAD
                  </button>
                </div>
              )
            })}
            <div className="qwen-tool-note">
              Native Gradio pages stay inside Dandy. No extra browser window is required. Deep model-specific controls remain available in the embedded page while Dandy owns model switching and status.
            </div>
          </div>
        )}
      </div>
    </div>
  )
}


export default function StudioConsole() {
  const [studioView, setStudioView] = useState('audio')

  return (
    <div className="tab-body dandy-studio-v2">
      <div className="studio-v2-nav">
        {STUDIO_VIEWS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            className={`studio-v2-tab${studioView === id ? ' active' : ''}`}
            onClick={() => setStudioView(id)}
          >
            <Icon size={14} />
            {label}
          </button>
        ))}
      </div>

      <div className="studio-v2-body">
        {studioView === 'qwen'
          ? <QwenStudio />
          : <LegacyStudioView view={studioView} />
        }
      </div>
    </div>
  )
}
