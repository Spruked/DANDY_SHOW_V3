// components/ui.jsx — Dandy Studio shared UI primitives

export function Modal({ title, onClose, children, footer, wide }) {
  return (
    <div className="modal-overlay" onClick={e => { if (e.target === e.currentTarget) onClose() }}>
      <div className={`modal-box${wide ? ' wide' : ''}`}>
        <div className="modal-head">
          <span className="modal-title">{title}</span>
          <button className="icon-btn" onClick={onClose} style={{ marginLeft: 8 }}>✕</button>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-footer">{footer}</div>}
      </div>
    </div>
  )
}

export function Field({ label, children }) {
  return (
    <div className="field">
      <div className="field-label">{label}</div>
      {children}
    </div>
  )
}

export function StatBox({ val, label, tone }) {
  return (
    <div className="stat-box">
      <div className={`stat-val${tone ? ` ${tone}` : ''}`}>{val ?? '—'}</div>
      <div className="stat-label">{label}</div>
    </div>
  )
}

export function SectionHead({ label, children }) {
  return (
    <div className="section-head">
      <span className="section-label">{label}</span>
      {children}
    </div>
  )
}

export function Spinner({ size = 14 }) {
  return (
    <span
      className="spinner"
      style={{ width: size, height: size }}
    />
  )
}

export function Empty({ msg }) {
  return <div className="empty-msg">{msg}</div>
}

export function Badge({ type = 'steel', children }) {
  return <span className={`badge badge-${type}`}>{children}</span>
}

export function Divider() {
  return <div className="divider" />
}

export function Toast({ visible, message }) {
  if (!visible) return null
  return <div className="toast">{message}</div>
}
