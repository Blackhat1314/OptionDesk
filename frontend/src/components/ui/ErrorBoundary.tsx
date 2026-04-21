import React, { Component, ErrorInfo } from 'react';

interface Props {
  children: React.ReactNode;
  fallback?: React.ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    this.setState({ errorInfo });
    console.error('ErrorBoundary caught:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;

      return (
        <div className="flex items-center justify-center h-full p-6">
          <div className="border border-market-down/30 bg-market-down/5 p-6 max-w-lg w-full font-mono">
            <div className="text-market-down text-sm font-bold mb-3">
              ⚠ COMPONENT ERROR
            </div>
            <div className="text-text-secondary text-xs mb-3">
              {this.state.error?.message || 'Unknown error occurred'}
            </div>
            {this.state.errorInfo && (
              <pre className="text-text-muted text-2xs overflow-auto max-h-40 bg-bg-primary p-2 border border-border-primary">
                {this.state.errorInfo.componentStack?.slice(0, 500)}
              </pre>
            )}
            <button
              className="mt-4 px-4 py-1.5 border border-accent-yellow text-accent-yellow text-xs hover:bg-accent-yellow hover:text-black transition-colors"
              onClick={() => this.setState({ hasError: false, error: null, errorInfo: null })}
            >
              RETRY
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
