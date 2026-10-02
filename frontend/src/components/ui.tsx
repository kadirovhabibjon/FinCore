import { useState, type ReactNode } from "react";

import { ApiError } from "../api/client";
import { formatMinor } from "../lib/money";

export function ErrorAlert({ error }: { error: unknown }) {
  if (!error) return null;
  const message =
    error instanceof ApiError
      ? error.detail && error.detail !== error.title
        ? `${error.title} — ${error.detail}`
        : error.title
      : "Something went wrong. Check your connection and try again.";
  return (
    <div className="alert alert-error" role="alert">
      {message}
    </div>
  );
}

export function Notice({ children }: { children: ReactNode }) {
  return (
    <div className="alert alert-info" role="status">
      {children}
    </div>
  );
}

export function Money({ minor, currency }: { minor: number; currency: string }) {
  return <span className="money">{formatMinor(minor, currency)}</span>;
}

const STATUS_TONES: Record<string, string> = {
  COMPLETED: "good",
  SUCCESS: "good",
  ACTIVE: "good",
  SUCCEEDED: "good",
  ALLOW: "good",
  PENDING: "warn",
  PROCESSING: "warn",
  CREATED: "warn",
  PARTIALLY_REFUNDED: "warn",
  REVIEW: "warn",
  SUSPENDED: "warn",
  FAILED: "bad",
  BLOCKED: "bad",
  DISABLED: "bad",
  EXPIRED: "bad",
  BLOCK: "bad",
};

export function StatusBadge({ status }: { status: string }) {
  return <span className={`badge badge-${STATUS_TONES[status] ?? "neutral"}`}>{status}</span>;
}

export function DateTime({ value }: { value: string | null | undefined }) {
  if (!value) return <span className="muted">—</span>;
  const date = new Date(value);
  return <time dateTime={value}>{date.toLocaleString()}</time>;
}

export function ShortId({ id }: { id: string }) {
  return (
    <code className="short-id" title={id}>
      {id.slice(0, 8)}
    </code>
  );
}

export function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      className="button button-small button-ghost"
      onClick={async () => {
        try {
          // Like randomUUID, the Clipboard API is secure-context only.
          if (!navigator.clipboard) return;
          await navigator.clipboard.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        } catch {
          // Clipboard access can be denied; the value is still on screen.
        }
      }}
    >
      {copied ? "Copied" : label}
    </button>
  );
}

export function Loading({ what = "Loading" }: { what?: string }) {
  return (
    <p className="muted" role="status">
      {what}…
    </p>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="empty">{children}</p>;
}

export function Pager({
  offset,
  limit,
  count,
  onChange,
}: {
  offset: number;
  limit: number;
  count: number;
  onChange: (offset: number) => void;
}) {
  if (offset === 0 && count < limit) return null;
  return (
    <nav className="pager" aria-label="Pagination">
      <button
        type="button"
        className="button button-ghost"
        disabled={offset === 0}
        onClick={() => onChange(Math.max(0, offset - limit))}
      >
        Newer
      </button>
      <span className="muted">
        {count === 0 ? "No more" : `${offset + 1}–${offset + count}`}
      </span>
      <button
        type="button"
        className="button button-ghost"
        disabled={count < limit}
        onClick={() => onChange(offset + limit)}
      >
        Older
      </button>
    </nav>
  );
}
