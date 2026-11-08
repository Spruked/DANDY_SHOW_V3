import { useEffect, useState } from 'react'
import { req } from '../lib/api'

export default function VaultStatus() {
  const [state, setState] = useState(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  useEffect(() => {
    let live = true
    async function poll() {
      try { const result = await req('/vault/status'); if (live) setState(result) }
      catch { if (live) setState(previous => ({ ...previous, status: 'unavailable' })) }
    }
    poll()
    const timer = setInterval(poll, 5000)
    return () => { live = false; clearInterval(timer) }
  }, [])

  async function action(kind) {
    setBusy(true); setMessage('')
    try {
      const result = await req(`/vault/${kind}`, { method: 'POST' })
      setMessage(kind === 'verify' ? (result.valid ? `Verified ${result.objects_checked} objects and ${result.ledger_entries} ledger entries.` : 'Verification failed. Inspect the vault status.') : `Saved ${result.file_count} files.`)
      setState(await req('/vault/status'))
    } catch (e) { setMessage(e.message) } finally { setBusy(false) }
  }
  if (!state) return null
  const receipt = state.latest_project_receipt
  return <details className="vault-status" style={{ flexShrink: 0, padding: '5px 16px', borderBottom: '1px solid var(--rim)', fontSize: '.8rem', color: ['error', 'unavailable'].includes(state.status) ? 'var(--gold)' : 'var(--steel)', maxHeight: 200, overflow: 'auto' }}>
    <summary>VAULT / AIMS · {state.enabled === false ? 'disabled' : state.status || 'pending'}{receipt ? ` · ${receipt.file_count} project files in last snapshot` : ''}</summary>
    <p>Automatic local snapshots every {state.sync_interval_seconds || 30} seconds while the studio is running. Last saved: {state.last_snapshot_at || 'pending'}.</p>
    <p style={{ overflowWrap: 'anywhere' }}>{state.vault_root}<br />AIMS ledger: {state.aims_store}</p>
    {state.last_error && <p role="alert">{state.last_error}</p>}
    <div className="gap-row"><button className="btn btn-steel btn-sm" disabled={busy} onClick={() => action('snapshot')}>{busy ? 'WORKING…' : 'SNAPSHOT NOW'}</button><button className="btn btn-steel btn-sm" disabled={busy} onClick={() => action('verify')}>VERIFY VAULT</button></div>
    {message && <p role="status">{message}</p>}
  </details>
}
