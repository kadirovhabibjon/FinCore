import { formatCardNumber } from "../lib/card";
import { receiveLink } from "../lib/qr";
import { useI18n } from "../i18n";
import { QrCanvas } from "./QrCanvas";

/** A wallet's card as a QR code. Scanned with a phone's camera it opens
 * the Send page with this card filled in; FinCore's own scanner reads
 * it too. */
export function CardQr({ cardNumber }: { cardNumber: string }) {
  const { t } = useI18n();
  return (
    <QrCanvas
      text={receiveLink(window.location.origin, cardNumber)}
      label={t("qr.label", { card: formatCardNumber(cardNumber) })}
    >
      {t("qr.caption")}
    </QrCanvas>
  );
}
