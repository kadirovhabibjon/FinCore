import { useState, type ReactNode } from "react";

import { ApiError } from "../api/client";
import { formatMinor } from "../lib/money";
import { useI18n } from "../i18n";

/** What the API said went wrong. Its titles and details are English;
 * in another language the title is shown translated when it is one we
 * know (and the English detail dropped), otherwise as the API sent it. */
export function ErrorAlert({ error }: { error: unknown }) {
  const { t, lang, maybe } = useI18n();
  if (!error) return null;
  let message = t("common.error.generic");
  if (error instanceof ApiError) {
    const known = lang === "en" ? undefined : maybe(`error.${error.title}`);
    message =
      known ??
      (error.detail && error.detail !== error.title
        ? `${error.title} — ${error.detail}`
        : error.title);
  }
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
  const { maybe } = useI18n();
  return (
    <span className={`badge badge-${STATUS_TONES[status] ?? "neutral"}`}>
      {maybe(`status.${status}`) ?? status}
    </span>
  );
}

export function DateTime({ value }: { value: string | null | undefined }) {
  const { locale } = useI18n();
  if (!value) return <span className="muted">—</span>;
  const date = new Date(value);
  return <time dateTime={value}>{date.toLocaleString(locale)}</time>;
}

export function ShortId({ id }: { id: string }) {
  return (
    <code className="short-id" title={id}>
      {id.slice(0, 8)}
    </code>
  );
}

export function CopyButton({ text, label }: { text: string; label?: string }) {
  const { t } = useI18n();
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
      {copied ? t("common.copied") : (label ?? t("common.copy"))}
    </button>
  );
}

export function Loading({ what }: { what?: string }) {
  const { t } = useI18n();
  return (
    <p className="muted" role="status">
      {what ?? t("common.loading")}…
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
  const { t } = useI18n();
  if (offset === 0 && count < limit) return null;
  return (
    <nav className="pager" aria-label={t("common.pagination")}>
      <button
        type="button"
        className="button button-ghost"
        disabled={offset === 0}
        onClick={() => onChange(Math.max(0, offset - limit))}
      >
        {t("common.newer")}
      </button>
      <span className="muted">
        {count === 0 ? t("common.noMore") : `${offset + 1}–${offset + count}`}
      </span>
      <button
        type="button"
        className="button button-ghost"
        disabled={count < limit}
        onClick={() => onChange(offset + limit)}
      >
        {t("common.older")}
      </button>
    </nav>
  );
}
