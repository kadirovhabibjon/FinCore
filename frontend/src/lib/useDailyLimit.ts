import { useQuery } from "@tanstack/react-query";

import * as api from "../api/endpoints";
import { useI18n } from "../i18n";
import { formatMinor, toMinor } from "./money";

/** The chosen card's daily limit, for a form that is about to send
 * from it: `over(amount)` is the message to show when a (valid) amount
 * won't fit in what is left, else null. The server decides for real;
 * this only saves the customer a failed operation. If the limit can't
 * be read, nothing is held back here. */
export function useDailyLimit(wallet: api.Wallet | undefined) {
  const { t } = useI18n();
  const limit = useQuery({
    queryKey: ["limit", wallet?.id],
    queryFn: () => api.getWalletLimit(wallet!.id),
    enabled: !!wallet,
    retry: false,
  });
  const remaining = limit.data?.remaining_minor ?? null;
  return {
    refresh: () => void limit.refetch(),
    over(amount: string): string | null {
      if (!wallet || remaining === null) return null;
      if (toMinor(amount, wallet.currency) <= remaining) return null;
      return t("limit.over", { remaining: formatMinor(remaining, wallet.currency) });
    },
  };
}
