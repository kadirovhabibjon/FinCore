import { useEffect, useRef, useState } from "react";

import { formatCardNumber } from "../lib/card";
import { receiveLink } from "../lib/qr";
import { useI18n } from "../i18n";

const SIZE = 220;

/** A wallet's card as a QR code. Scanned with a phone's camera it opens
 * the Send page with this card filled in; FinCore's own scanner reads
 * it too. Drawn on a canvas in the browser: nothing is fetched. */
export function CardQr({ cardNumber }: { cardNumber: string }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const { t } = useI18n();
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    // Loaded on demand: most visits to a wallet never open the code.
    import("qrcode")
      .then((qrcode) => {
        if (cancelled || !canvas.current) return;
        return qrcode.toCanvas(canvas.current, receiveLink(window.location.origin, cardNumber), {
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
  }, [cardNumber]);

  return (
    <figure className="card-qr">
      {failed ? (
        <p className="muted">{t("qr.unavailable")}</p>
      ) : (
        <canvas
          ref={canvas}
          width={SIZE}
          height={SIZE}
          role="img"
          aria-label={t("qr.label", { card: formatCardNumber(cardNumber) })}
        />
      )}
      <figcaption className="muted small">
        {t("qr.caption")}
      </figcaption>
    </figure>
  );
}
