import { useState } from 'react'
import { req, api } from '../lib/api'
import { Field, Spinner } from './ui'

const MOTIONS = ['none', 'fade', 'slide', 'zoom', 'reveal', 'pulse']
const id = () => crypto.randomUUID()
const empty = () => ({ version: 1, aspect: '16:9', background_color: '#0e1116', text_layers: [], visuals: [], sfx_tracks: [] })
const grid = { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 8 }

export default function VisualAdComposer({ episodeId, ad, assets, onSaved }) {
  const [composition, setComposition] = useState(() => structuredClone(ad.composition || empty()))
  const [dirty, setDirty] = useState(false)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [output, setOutput] = useState(ad.visual_export || null)
  const duration = Number(ad.duration_seconds || 30)
  const base = `/episodes/${encodeURIComponent(episodeId)}/ads/${encodeURIComponent(ad.ad_id)}`
  const set = (key, value) => { setComposition(prev => ({ ...prev, [key]: value })); setDirty(true); setOutput(null) }
  const patch = (track, layerId, values) => set(track, composition[track].map(layer => layer.id === layerId ? { ...layer, ...values } : layer))
  const remove = (track, layerId) => set(track, composition[track].filter(layer => layer.id !== layerId))
  const timed = () => ({ id: id(), start: 0, end: duration, animation_in: 'fade', animation_out: 'fade', animation_duration: .5, easing: 'ease_in_out' })
  const save = async () => {
    const result = await req(base + '/composition', { method: 'PUT', body: JSON.stringify(composition) })
    setDirty(false); onSaved(result.ad); return result
  }
  const saveClick = async () => {
    setBusy(true); setMessage('')
    try { await save(); setMessage('Composition saved to this ad') }
    catch (e) { setMessage(e.message) }
    finally { setBusy(false) }
  }
  const render = async () => {
    setBusy(true); setMessage('')
    try {
      await save()
      const result = await req(base + '/render', { method: 'POST' })
      setOutput(result); onSaved(result.ad); setMessage('Rendered from saved composition')
    } catch (e) { setMessage(e.message) }
    finally { setBusy(false) }
  }
  const number = (track, layer, key, label, min = 0, max = 120, step = .1) => <Field label={label}><input className="ds-input" type="number" min={min} max={max} step={step} value={layer[key]} disabled={busy} onChange={e => patch(track, layer.id, { [key]: Number(e.target.value) })} /></Field>
  const select = (track, layer, key, label, values) => <Field label={label}><select className="ds-select" value={layer[key]} disabled={busy} onChange={e => patch(track, layer.id, { [key]: e.target.value })}>{values.map(value => <option key={value}>{value}</option>)}</select></Field>
  const assetPicker = (track, layer, audio = false) => <Field label={audio ? 'Sound asset' : 'Image / video asset'}><select className="ds-select" value={layer.asset_id} disabled={busy} onChange={e => patch(track, layer.id, { asset_id: e.target.value })}><option value="">Select an uploaded ad asset</option>{assets.filter(asset => audio ? asset.content_type?.startsWith('audio/') : /^(image|video)\//.test(asset.content_type || '')).map(asset => <option key={asset.asset_id} value={asset.asset_id}>{asset.label || asset.original_name}</option>)}</select></Field>
  const allTimed = [...composition.text_layers, ...composition.visuals]
  return <div style={{ borderTop: '1px solid var(--rim)', paddingTop: 12 }}>
    <div className="section-head"><span className="section-label">Visual Ad Composer</span><button className="btn btn-solid btn-sm" onClick={saveClick} disabled={busy}>{busy ? <Spinner /> : null}{dirty ? 'SAVE CHANGES' : 'SAVE COMPOSITION'}</button><button className="btn btn-gold btn-sm" onClick={render} disabled={busy || !ad.audio_file}>{busy ? 'WORKING' : 'RENDER VIDEO'}</button></div>
    <div style={{ fontSize: '0.94rem', color: 'var(--steel)', marginBottom: 10 }}>Upload images, videos, and sounds above. Voice must be produced first. All tracks are saved with this ad; render uses that same state. No voice trimming or provider substitution.</div>
    <div style={grid}>
      <Field label="Video aspect"><select className="ds-select" value={composition.aspect} disabled={busy} onChange={e => set('aspect', e.target.value)}>{['16:9', '1:1', '9:16', '4:5'].map(value => <option key={value}>{value}</option>)}</select></Field>
      <Field label="Background color"><input type="color" value={composition.background_color} disabled={busy} onChange={e => set('background_color', e.target.value)} /></Field>
    </div>
    <div aria-label="Ad timeline" style={{ border: '1px solid var(--rim)', padding: 10, margin: '12px 0' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem' }}><span>0s</span><span>{duration}s requested</span></div>
      {[['TEXT', composition.text_layers], ['VISUAL', composition.visuals], ['VOICE', [{ id: 'voice', start: 0, end: Number(ad.actual_duration_seconds || duration) }]], ['SFX', composition.sfx_tracks.map(track => ({ ...track, end: Math.min(duration, track.start + .4) }))]].map(([name, layers]) => <div key={name} style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 6 }}>
        <span style={{ width: 55, fontSize: '0.81rem' }}>{name}</span><div style={{ flex: 1, height: 18, position: 'relative', background: 'var(--bg)' }}>{layers.map(layer => <span key={layer.id} title={name + ' · ' + layer.start + '–' + layer.end + 's'} style={{ position: 'absolute', left: (layer.start / duration * 100) + '%', width: Math.max(.8, Math.min(duration - layer.start, layer.end - layer.start) / duration * 100) + '%', height: 12, top: 3, background: name === 'SFX' ? 'var(--blue)' : 'var(--gold)', opacity: .7 }} />)}</div>
      </div>)}
      <div style={{ fontSize: '0.85rem', color: 'var(--steel)', marginTop: 6 }}>SFX marks show start offsets; the renderer validates actual sound length.</div>
    </div>
    <details open><summary>Text track · {composition.text_layers.length} layers</summary>
      <button className="btn btn-steel btn-sm" disabled={busy} onClick={() => set('text_layers', [...composition.text_layers, { ...timed(), role: 'headline', content: ad.product || ad.sponsor || '', x: .5, y: .45, font: 'Arial Bold', size: 64, align: 'center', color: '#ffffff' }])}>ADD TEXT</button>
      {composition.text_layers.map(layer => <div key={layer.id} style={{ padding: '10px 0', borderBottom: '1px solid var(--rim)' }}>
        <Field label="Text content"><textarea className="ds-textarea" value={layer.content} disabled={busy} onChange={e => patch('text_layers', layer.id, { content: e.target.value })} /></Field>
        <div style={grid}>{select('text_layers', layer, 'role', 'Text role', ['headline', 'subtitle', 'cta', 'offer_code', 'url', 'custom'])}{select('text_layers', layer, 'font', 'Font', ['Arial', 'Arial Bold', 'Georgia', 'Consolas'])}{number('text_layers', layer, 'size', 'Font size (px)', 12, 200, 1)}{select('text_layers', layer, 'align', 'Alignment', ['left', 'center', 'right'])}{number('text_layers', layer, 'x', 'X position (0–1)', 0, 1, .01)}{number('text_layers', layer, 'y', 'Y position (0–1)', 0, 1, .01)}{number('text_layers', layer, 'start', 'Start (s)')}{number('text_layers', layer, 'end', 'End (s)', .1, duration)}<Field label="Text color"><input type="color" value={layer.color} disabled={busy} onChange={e => patch('text_layers', layer.id, { color: e.target.value })} /></Field></div>
        <button className="btn btn-steel btn-sm" disabled={busy} onClick={() => remove('text_layers', layer.id)}>REMOVE TEXT</button>
      </div>)}
    </details>
    <details open><summary>Visual track · {composition.visuals.length} layers</summary>
      <button className="btn btn-steel btn-sm" disabled={busy} onClick={() => set('visuals', [...composition.visuals, { ...timed(), asset_id: '', role: 'background', x: .5, y: .5, width: 1, opacity: 1 }])}>ADD VISUAL</button>
      {composition.visuals.map(layer => <div key={layer.id} style={{ padding: '10px 0' }}><div style={grid}>{assetPicker('visuals', layer)}{select('visuals', layer, 'role', 'Visual role', ['background', 'logo', 'product', 'overlay'])}{number('visuals', layer, 'width', 'Width (canvas fraction)', .01, 1, .01)}{number('visuals', layer, 'opacity', 'Opacity', 0, 1, .01)}{number('visuals', layer, 'x', 'X position (0–1)', 0, 1, .01)}{number('visuals', layer, 'y', 'Y position (0–1)', 0, 1, .01)}{number('visuals', layer, 'start', 'Start (s)')}{number('visuals', layer, 'end', 'End (s)', .1, duration)}</div><button className="btn btn-steel btn-sm" disabled={busy} onClick={() => remove('visuals', layer.id)}>REMOVE VISUAL</button></div>)}
    </details>
    <details open><summary>Animation track · entrance / exit</summary>{allTimed.map(layer => {
      const track = composition.text_layers.some(text => text.id === layer.id) ? 'text_layers' : 'visuals'
      return <div key={layer.id} style={{ padding: '10px 0' }}><div style={{ fontSize: '0.94rem' }}>{layer.content || layer.role}</div><div style={grid}>{select(track, layer, 'animation_in', 'Entrance', MOTIONS)}{select(track, layer, 'animation_out', 'Exit', MOTIONS)}{number(track, layer, 'animation_duration', 'Motion duration (s)', .05, 5, .05)}{select(track, layer, 'easing', 'Easing', ['linear', 'ease_in_out'])}</div></div>
    })}</details>
    <details open><summary>SFX track · {composition.sfx_tracks.length} sounds</summary>
      <button className="btn btn-steel btn-sm" disabled={busy} onClick={() => set('sfx_tracks', [...composition.sfx_tracks, { id: id(), asset_id: '', start: 0, volume_db: -12, fade_in: .05, fade_out: .1 }])}>ADD SOUND EFFECT</button>
      {composition.sfx_tracks.map(layer => <div key={layer.id} style={{ padding: '10px 0' }}><div style={grid}>{assetPicker('sfx_tracks', layer, true)}{number('sfx_tracks', layer, 'start', 'Offset (s)', 0, duration)}{number('sfx_tracks', layer, 'volume_db', 'Volume (dB)', -60, 12, 1)}{number('sfx_tracks', layer, 'fade_in', 'Fade in (s)', 0, 10)}{number('sfx_tracks', layer, 'fade_out', 'Fade out (s)', 0, 10)}</div>{layer.asset_id && <audio controls preload="none" src={api.adAssetFileUrl(episodeId, ad.ad_id, layer.asset_id)} />}<button className="btn btn-steel btn-sm" disabled={busy} onClick={() => remove('sfx_tracks', layer.id)}>REMOVE SOUND</button></div>)}
    </details>
    {message && <div role="status" style={{ padding: '10px 0', fontSize: '1.04rem' }}>{message}</div>}
    {output?.download_url && <><video controls preload="metadata" src={output.download_url} style={{ width: '100%', maxHeight: 360, marginTop: 10 }} /><a className="btn btn-gold btn-sm" href={output.download_url} download>DOWNLOAD RENDERED AD</a></>}
  </div>
}
