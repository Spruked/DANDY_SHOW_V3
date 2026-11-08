// components/ui.jsx — Dandy Studio shared UI primitives

import { Children, cloneElement, isValidElement, useEffect, useId, useRef } from 'react'

export function Modal({ title, onClose, children, footer, wide }) {
  const titleId = useId()
  const dialogRef = useRef(null)
  const closeRef = useRef(onClose)
  closeRef.current = onClose
  useEffect(() => {
    const previousFocus = document.activeElement
    const dialog = dialogRef.current
    const focusable = () => [...dialog.querySelectorAll('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), a[href], [tabindex="0"]')]
    focusable()[0]?.focus()
    const onKeyDown = (event) => {
      if (event.key === 'Escape') { event.preventDefault(); closeRef.current() }
      if (event.key !== 'Tab') return
      const items = focusable()
      const first = items[0], last = items[items.length - 1]
      if (!first) { event.preventDefault(); return }
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
    }
    dialog.addEventListener('keydown', onKeyDown)
    return () => { dialog.removeEventListener('keydown', onKeyDown); previousFocus?.focus?.() }
  }, [])
  return (
    <div className="modal-overlay" onClick={e => { if (e.target === e.currentTarget) onClose() }}>
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby={titleId} className={`modal-box${wide ? ' wide' : ''}`}>
        <div className="modal-head">
          <span id={titleId} className="modal-title">{title}</span>
          <button className="icon-btn" aria-label="Close dialog" onClick={onClose} style={{ marginLeft: 8 }}>✕</button>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-footer">{footer}</div>}
      </div>
    </div>
  )
}

export function Field({ label, children }) {
  const generatedId = useId()
  const content = Children.toArray(children)
  const control = content.find(child => isValidElement(child) && ['input', 'select', 'textarea'].includes(child.type))
  const controlId = control?.props.id || generatedId
  return (
    <div className="field">
      {control ? <label className="field-label" htmlFor={controlId}>{label}</label> : <div className="field-label">{label}</div>}
      {content.map(child => child === control ? cloneElement(child, { id: controlId }) : child)}
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
  return <div className="toast" role="status" aria-live="polite">{message}</div>
}
