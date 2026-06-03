import { Component, type ErrorInfo, type PropsWithChildren, type ReactNode } from 'react'

import { reportClientError } from '@/shared/telemetry/clientLogger'
import { Card } from '@/shared/ui/Card'

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
      message: error.message,
      stack: error.stack,
      context: {
        source: 'error-boundary',
        componentStack: errorInfo.componentStack,
      },
    })
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <div className="login-view">
          <Card>
            <h2>Критическая ошибка интерфейса</h2>
            <p className="muted">Обновите страницу. Если ошибка повторяется, проверьте API и логи браузера.</p>
          </Card>
        </div>
      )
    }

    return this.props.children
  }
}
