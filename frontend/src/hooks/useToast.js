// hooks/useToast.js
import { useState, useCallback } from 'react'

export function useToast() {
  const [toast, setToast] = useState({ visible: false, message: '' })

  const showToast = useCallback((message, duration = 2800) => {
    setToast({ visible: true, message })
    setTimeout(() => setToast({ visible: false, message: '' }), duration)
  }, [])

  return { toast, showToast }
}
