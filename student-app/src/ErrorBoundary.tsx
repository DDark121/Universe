import { Component, type ErrorInfo, type PropsWithChildren, type ReactNode } from 'react'

import { reportClientError } from './clientLogger'

type State = {
  hasError: boolean
}

export class ErrorBoundary extends Component<PropsWithChildren, State> {
  constructor(props: PropsWithChildren) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError(): State {
    return { hasError: true }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    void reportClientError({
      message: error.message || 'Student app render failure',
      stack: error.stack,
      context: {
        source: 'react.error_boundary',
        componentStack: errorInfo.componentStack,
      },
    })
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <div className="splash-screen">
          <div className="panel" style={{ maxWidth: 720 }}>
            <h1>Критическая ошибка mini app</h1>
            <p className="muted">Обновите приложение из Telegram. Если ошибка повторяется, проверьте backend и client logs.</p>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}
