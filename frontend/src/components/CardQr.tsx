import { useEffect, useRef, useState } from "react";

import { formatCardNumber } from "../lib/card";
import { receiveLink } from "../lib/qr";

const SIZE = 220;

/** A wallet's card as a QR code. Scanned with a phone's camera it opens
 * the Send page with this card filled in; FinCore's own scanner reads
 * it too. Drawn on a canvas in the browser: nothing is fetched. */
export function CardQr({ cardNumber }: { cardNumber: string }) {
  const canvas = useRef<HTMLCanvasElement>(null);
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
        <p className="muted">The code can&apos;t be drawn in this browser. Share the number.</p>
      ) : (
        <canvas
          ref={canvas}
          width={SIZE}
          height={SIZE}
          role="img"
          aria-label={`QR code for card ${formatCardNumber(cardNumber)}`}
        />
      )}
      <figcaption className="muted small">
        Scan to send money to this card: with a phone&apos;s camera, or with Scan QR code on
        FinCore&apos;s Send page.
      </figcaption>
    </figure>
  );
}
