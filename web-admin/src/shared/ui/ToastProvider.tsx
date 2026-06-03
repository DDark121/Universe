import { createContext, useCallback, useContext, useMemo, useState, type PropsWithChildren } from 'react'

type ToastType = 'success' | 'error' | 'info'

type ToastItem = {
  id: number
  message: string
  type: ToastType
}

type ToastContextValue = {
  push: (message: string, type?: ToastType) => void
}

const ToastContext = createContext<ToastContextValue | null>(null)

export function ToastProvider({ children }: PropsWithChildren) {
  const [items, setItems] = useState<ToastItem[]>([])

  const push = useCallback((message: string, type: ToastType = 'info') => {
    const id = Date.now() + Math.floor(Math.random() * 1000)
    setItems((prev) => [...prev, { id, message, type }])
    window.setTimeout(() => {
      setItems((prev) => prev.filter((item) => item.id !== id))
    }, 3200)
  }, [])

  const value = useMemo(() => ({ push }), [push])

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        style={{
          position: 'fixed',
          right: 16,
          bottom: 16,
          zIndex: 40,
          display: 'grid',
          gap: 8,
          maxWidth: 360,
        }}
      >
        {items.map((item) => (
          <div
            key={item.id}
            className="card"
            style={{
              padding: '10px 12px',
              borderColor:
                item.type === 'success'
                  ? 'rgba(79, 103, 52, 0.6)'
                  : item.type === 'error'
                    ? 'rgba(140, 63, 57, 0.6)'
                    : 'rgba(11, 22, 30, 0.2)',
            }}
          >
            {item.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const context = useContext(ToastContext)
  if (!context) {
    throw new Error('Toast context is unavailable')
  }
  return context
}
