import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import * as api from "../../api/endpoints";
import { DailyChart } from "../../components/admin/DailyChart";
import { Empty, ErrorAlert, Loading, Money } from "../../components/ui";
import { useI18n } from "../../i18n";
import { dayLabel } from "../../lib/chart";
import { formatMinor } from "../../lib/money";

const PERIODS = [7, 14, 30];

/** The console's first page: what is waiting for staff, and what the
 * platform did lately. One currency at a time - UZS and USD amounts
 * differ by four orders of magnitude and do not add up. Every part
 * loads on its own, so one service being down blanks one part. */
export function AdminDashboardPage() {
  const { t, locale } = useI18n();
  const [days, setDays] = useState(PERIODS[1] ?? 14);
  const [currency, setCurrency] = useState("");
  const platform = useQuery({
    queryKey: ["admin", "stats", "platform", days],
    queryFn: () => api.adminPlatformStats(days),
    placeholderData: (previous) => previous,
    refetchInterval: 60_000,
  });
  const users = useQuery({
    queryKey: ["admin", "stats", "users", days],
    queryFn: () => api.adminUserStats(days),
    placeholderData: (previous) => previous,
    refetchInterval: 60_000,
  });
  // The same query the menu's count uses.
  const support = useQuery({
    queryKey: ["admin", "support", "inbox", "open"],
    queryFn: () => api.adminSupportInbox("OPEN"),
  });

  const currencies = platform.data?.currencies ?? [];
  // Until one is chosen: the currency most of the activity is in.
  const operations = (item: (typeof currencies)[number]) =>
    item.days.reduce((sum, day) => sum + day.transfers + day.payments + day.exchanges, 0);
  const busiest = [...currencies].sort((a, b) => operations(b) - operations(a))[0];
  const shown = currencies.find((item) => item.currency === currency) ?? busiest;
  const today = shown?.days.at(-1);
  const newToday = users.data?.days.at(-1)?.registered ?? 0;
  const notActive = users.data
    ? users.data.total - (users.data.by_status["ACTIVE"] ?? 0)
    : 0;

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <h1>{t("admin.dash.title")}</h1>
          <p className="muted">{t("admin.dash.subtitle")}</p>
        </div>
        <div className="inline-form">
          {currencies.length > 1 && (
            <select
              aria-label={t("admin.dash.currency")}
              value={shown?.currency ?? ""}
              onChange={(event) => setCurrency(event.target.value)}
            >
              {currencies.map((item) => (
                <option key={item.currency}>{item.currency}</option>
              ))}
            </select>
          )}
          <select
            aria-label={t("admin.dash.period")}
            value={days}
            onChange={(event) => setDays(Number(event.target.value))}
          >
            {PERIODS.map((period) => (
              <option key={period} value={period}>
                {t("admin.dash.lastDays", { days: period })}
              </option>
            ))}
          </select>
        </div>
      </header>
      <ErrorAlert error={platform.error ?? users.error} />

      <div className="stats">
        <div className="card stat">
          <span className="muted small">{t("admin.dash.users")}</span>
          <strong className="stat-number">{users.data ? users.data.total : "—"}</strong>
          {users.data && (
            <span className="muted small">
              {t("admin.dash.usersNew", { count: newToday })}
              {notActive > 0 && ` · ${t("admin.dash.usersBlocked", { count: notActive })}`}
            </span>
          )}
        </div>
        <div className="card stat">
          <span className="muted small">{t("admin.dash.reviews")}</span>
          <strong className="stat-number">
            {platform.data ? platform.data.awaiting_review : "—"}
          </strong>
          <Link className="small" to="/admin/reviews">
            {t("admin.dash.reviewsLink")}
          </Link>
        </div>
        <div className="card stat">
          <span className="muted small">{t("admin.dash.support")}</span>
          <strong className="stat-number">
            {support.data ? support.data.waiting_count : "—"}
          </strong>
          <Link className="small" to="/admin/support">
            {t("admin.dash.supportLink")}
          </Link>
        </div>
      </div>

      {platform.isPending ? (
        <Loading what={t("admin.dash.loading")} />
      ) : !shown || !today ? (
        !platform.error && <Empty>{t("admin.dash.none")}</Empty>
      ) : (
        <>
          <h2>{t("admin.dash.today", { currency: shown.currency })}</h2>
          <div className="stats">
            <div className="card stat">
              <span className="muted small">{t("admin.dash.operations")}</span>
              <strong className="stat-number">
                {today.transfers + today.payments + today.exchanges}
              </strong>
              <span className="muted small">
                {today.transfers} {t("admin.dash.transfers")} · {today.payments}{" "}
                {t("admin.dash.payments")} · {today.exchanges} {t("admin.dash.exchanges")}
              </span>
            </div>
            <div className="card stat">
              <span className="muted small">{t("admin.dash.volume")}</span>
              <Money minor={today.volume_minor} currency={shown.currency} />
            </div>
            <div className="card stat">
              <span className="muted small">{t("admin.dash.failed")}</span>
              <strong className="stat-number">{today.failed}</strong>
              <Link className="small" to="/admin/transactions?status=FAILED">
                {t("admin.nav.transactions")}
              </Link>
            </div>
          </div>

          <div className="dash-charts">
            <div className="card">
              <DailyChart
                title={t("admin.dash.opsPerDay", { currency: shown.currency })}
                ariaLabel={t("admin.dash.opsChart", { currency: shown.currency })}
                unit={t("admin.dash.operations").toLowerCase()}
                locale={locale}
                days={shown.days.map((day) => {
                  const count = day.transfers + day.payments + day.exchanges;
                  return {
                    date: day.date,
                    value: count,
                    label: t("admin.dash.dayOps", {
                      date: dayLabel(day.date, locale, true),
                      count,
                    }),
                    detail: (
                      <span className="muted small">
                        {day.transfers} {t("admin.dash.transfers")} · {day.payments}{" "}
                        {t("admin.dash.payments")} · {day.exchanges} {t("admin.dash.exchanges")}
                        <br />
                        {day.failed} {t("admin.dash.failedShort")} ·{" "}
                        {formatMinor(day.volume_minor, shown.currency)} {t("admin.dash.movedShort")}
                      </span>
                    ),
                  };
                })}
              />
              <details className="viz-table">
                <summary>{t("admin.dash.asTable")}</summary>
                <table className="table">
                  <thead>
                    <tr>
                      <th>{t("admin.dash.day")}</th>
                      <th className="num">{t("admin.dash.colTransfers")}</th>
                      <th className="num">{t("admin.dash.colPayments")}</th>
                      <th className="num">{t("admin.dash.colExchanges")}</th>
                      <th className="num">{t("admin.dash.failed")}</th>
                      <th className="num">{t("admin.dash.volume")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {shown.days.map((day) => (
                      <tr key={day.date}>
                        <td data-label={t("admin.dash.day")}>{dayLabel(day.date, locale, true)}</td>
                        <td className="num" data-label={t("admin.dash.colTransfers")}>
                          {day.transfers}
                        </td>
                        <td className="num" data-label={t("admin.dash.colPayments")}>
                          {day.payments}
                        </td>
                        <td className="num" data-label={t("admin.dash.colExchanges")}>
                          {day.exchanges}
                        </td>
                        <td className="num" data-label={t("admin.dash.failed")}>
                          {day.failed}
                        </td>
                        <td className="num" data-label={t("admin.dash.volume")}>
                          <Money minor={day.volume_minor} currency={shown.currency} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </details>
            </div>
            {users.data && (
              <div className="card">
                <DailyChart
                  title={t("admin.dash.usersPerDay")}
                  ariaLabel={t("admin.dash.usersChart")}
                  unit={t("admin.dash.newShort")}
                  locale={locale}
                  days={users.data.days.map((day) => ({
                    date: day.date,
                    value: day.registered,
                    label: t("admin.dash.dayUsers", {
                      date: dayLabel(day.date, locale, true),
                      count: day.registered,
                    }),
                  }))}
                />
                <details className="viz-table">
                  <summary>{t("admin.dash.asTable")}</summary>
                  <table className="table">
                    <thead>
                      <tr>
                        <th>{t("admin.dash.day")}</th>
                        <th className="num">{t("admin.dash.colNew")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {users.data.days.map((day) => (
                        <tr key={day.date}>
                          <td data-label={t("admin.dash.day")}>
                            {dayLabel(day.date, locale, true)}
                          </td>
                          <td className="num" data-label={t("admin.dash.colNew")}>
                            {day.registered}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </details>
              </div>
            )}
          </div>
        </>
      )}
    </section>
  );
}
