import type { I18n } from "../i18n";

/** Why an operation failed, in the reader's language. The server gives
 * either one of the API's error titles (what the ledger refused with)
 * or a fixed phrase of its own; anything else is shown as it came. */
export function reasonText(reason: string, i18n: I18n): string {
  return i18n.maybe(`reason.${reason}`) ?? i18n.maybe(`error.${reason}`) ?? reason;
}
