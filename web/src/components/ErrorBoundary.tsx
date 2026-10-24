import { Component, type ErrorInfo, type ReactNode } from "react";

interface State {
  failed: boolean;
}

/** Last-resort guard so a rendering bug shows a message instead of a blank page. */
export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("UI crashed", error, info.componentStack);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 px-6 text-center">
        <h1 className="text-xl font-semibold">Something went wrong</h1>
        <p className="max-w-sm text-sm text-muted">
          The page hit an unexpected error. Reloading usually fixes it; your data and chat are safe
          on the server.
        </p>
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-ink"
        >
          Reload
        </button>
      </div>
    );
  }
}
