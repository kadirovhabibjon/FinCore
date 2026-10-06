import { Component, type ErrorInfo, type ReactNode } from "react";
import { i18n } from "../i18n";

/** Last line of defence against a blank page: an exception while
 * rendering shows what happened (and a way out) instead of unmounting
 * the whole app into a white screen. */
export class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("FinCore render error", error, info.componentStack);
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    const { t } = i18n();
    return (
      <div className="auth-page">
        <div className="card auth-card" role="alert">
          <h1>{t("shell.crash.title")}</h1>
          <pre className="error-details">{error.message}</pre>
          <p className="muted small">{navigator.userAgent}</p>
          <button type="button" className="button" onClick={() => window.location.reload()}>
            {t("shell.crash.reload")}
          </button>
        </div>
      </div>
    );
  }
}
