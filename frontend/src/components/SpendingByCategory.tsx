import { useQuery } from "@tanstack/react-query";

import * as api from "../api/endpoints";
import { useI18n } from "../i18n";
import { formatMinor } from "../lib/money";
import { ErrorAlert, Loading } from "./ui";

/** What the money out went on: one bar per category, longest first.
 * Bars rather than a pie - lengths on a common baseline compare at a
 * glance, slices don't - and one hue, since the bars differ in size,
 * not in kind. Every bar carries its amount and share as text, so
 * nothing is read from colour or length alone. */
export function SpendingByCategory({ months, currency }: { months: number; currency: string }) {
  const { t, maybe } = useI18n();
  const spending = useQuery({
    queryKey: ["stats", "categories", months],
    queryFn: () => api.getSpending(months),
    placeholderData: (previous) => previous,
  });
  const shown = spending.data?.currencies.find((item) => item.currency === currency);
  const largest = shown?.categories[0]?.amount_minor ?? 0;

  return (
    <section className="card spend" aria-labelledby="spend-title">
      <h2 id="spend-title">{t("spend.title", { currency })}</h2>
      <p className="muted small">{t("spend.subtitle")}</p>
      <ErrorAlert error={spending.error} />
      {spending.isPending ? (
        <Loading what={t("spend.loading")} />
      ) : !shown || shown.total_minor === 0 ? (
        !spending.error && <p className="muted">{t("spend.empty")}</p>
      ) : (
        <>
          <ul className="spend-list" aria-label={t("spend.list")}>
            {shown.categories.map((item) => {
              const name = maybe(`category.${item.category}`) ?? item.category;
              const amount = formatMinor(item.amount_minor, currency);
              // Whole percent of the total; under one still shows as "<1".
              const exact = (item.amount_minor / shown.total_minor) * 100;
              const share = exact > 0 && exact < 1 ? "<1" : String(Math.round(exact));
              return (
                <li
                  key={item.category}
                  aria-label={t("spend.row", { category: name, amount, share, count: item.count })}
                >
                  <span className="spend-head" aria-hidden="true">
                    <strong>{name}</strong>
                    <span>
                      {amount} <span className="muted small">· {share}%</span>
                    </span>
                  </span>
                  <span className="spend-track" aria-hidden="true">
                    <span
                      className="spend-bar"
                      // Sized from the data, so it has to be a computed style.
                      style={{ width: `${Math.max((item.amount_minor / largest) * 100, 1)}%` }}
                    />
                  </span>
                  <span className="muted small" aria-hidden="true">
                    {t("spend.count", { count: item.count })}
                  </span>
                </li>
              );
            })}
          </ul>
          <p className="spend-total">
            <span className="muted">{t("spend.total")}</span>{" "}
            <strong>{formatMinor(shown.total_minor, currency)}</strong>
          </p>
        </>
      )}
    </section>
  );
}
