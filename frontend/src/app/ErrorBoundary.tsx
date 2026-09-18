import { AlertTriangle } from 'lucide-react'
import { Component, type ErrorInfo, type ReactNode } from 'react'

import styles from './ErrorBoundary.module.css'
import { Button } from '@/design-system'

interface ErrorBoundaryProps {
  children: ReactNode
}

interface ErrorBoundaryState {
  error: Error | null
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Unhandled error in TrackFlow UI:', error, info.componentStack)
  }

  render() {
    if (this.state.error) {
      return (
        <div className={styles.wrap}>
          <AlertTriangle size={32} className={styles.icon} />
          <div className={styles.title}>Something went wrong</div>
          <div className={styles.message}>
            This part of the page hit an unexpected error. Try reloading — if it keeps
            happening, the details below might help track it down.
          </div>
          <div className={styles.details}>{this.state.error.message}</div>
          <Button variant="primary" onClick={() => window.location.reload()}>
            Reload page
          </Button>
        </div>
      )
    }
    return this.props.children
  }
}
