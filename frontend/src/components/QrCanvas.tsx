import { useEffect, useRef, useState, type ReactNode } from "react";

import { useI18n } from "../i18n";

const SIZE = 220;

/** Some text as a QR code, drawn on a canvas in the browser: nothing is
 * fetched, and nothing about it leaves the page. */
export function QrCanvas({
  text,
  label,
  children,
}: {
  text: string;
  /** What the picture is, for someone who can't see it. */
  label: string;
  /** The caption under it. */
  children: ReactNode;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const { t } = useI18n();
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    // Loaded on demand: most visits never open a code.
    import("qrcode")
      .then((qrcode) => {
        if (cancelled || !canvas.current) return;
        return qrcode.toCanvas(canvas.current, text, {
          width: SIZE,
          margin: 2,
          errorCorrectionLevel: "M",
        });
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [text]);

  return (
    <figure className="card-qr">
      {failed ? (
        <p className="muted">{t("qr.unavailable")}</p>
      ) : (
        <canvas ref={canvas} width={SIZE} height={SIZE} role="img" aria-label={label} />
      )}
      <figcaption className="muted small">{children}</figcaption>
    </figure>
  );
}
