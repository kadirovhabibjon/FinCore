import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import * as api from "../api/endpoints";
import { Empty, ErrorAlert, Loading, Money } from "../components/ui";
import { columnPath, compact, monthLabel, niceTicks } from "../lib/chart";
import { formatMinor } from "../lib/money";
import { useI18n } from "../i18n";

const PERIODS = [6, 12];
const HEIGHT = 260;
const MARGIN = { top: 12, right: 8, bottom: 28, left: 48 };
const BAR_MAX = 24;
const BAR_GAP = 2;

/** How wide the chart has to draw itself, so its text stays one size on
 * a phone and on a desktop instead of scaling with the picture. */
function useWidth(fallback: number) {
  const element = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(fallback);
  useEffect(() => {
    const node = element.current;
    if (!node || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => {
      if (entry && entry.contentRect.width > 0) setWidth(entry.contentRect.width);
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  return [element, width] as const;
}

/** Money in and out per month. Two series on one axis, in one currency
 * at a time: UZS and USD amounts differ by four orders of magnitude and
 * would not share a scale honestly. */
export function StatsPage() {
  const { t, locale } = useI18n();
  const [months, setMonths] = useState(PERIODS[0] ?? 6);
  const [currency, setCurrency] = useState("");
  const stats = useQuery({
    queryKey: ["stats", months],
    queryFn: () => api.getStats(months),
    // A changed period keeps the old picture up while the new one loads.
    placeholderData: (previous) => previous,
  });

  const available = stats.data?.currencies ?? [];
  const shown = available.find((item) => item.currency === currency) ?? available[0];

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <h1>{t("stats.title")}</h1>
          <p className="muted">{t("stats.subtitle")}</p>
        </div>
        <Link to="/transactions" className="button button-ghost">
          {t("common.history")}
        </Link>
      </header>
      <div className="inline-form viz-filters" role="group" aria-label={t("stats.filters")}>
        <select
          aria-label={t("stats.period")}
          value={months}
          onChange={(event) => setMonths(Number(event.target.value))}
        >
          {PERIODS.map((count) => (
            <option key={count} value={count}>
              {t("stats.lastMonths", { count })}
            </option>
          ))}
        </select>
        {available.length > 1 && (
          <select
            aria-label={t("stats.currency")}
            value={shown?.currency}
            onChange={(event) => setCurrency(event.target.value)}
          >
            {available.map((item) => (
              <option key={item.currency}>{item.currency}</option>
            ))}
          </select>
        )}
      </div>
      <ErrorAlert error={stats.error} />
      {stats.isPending ? (
        <Loading what={t("stats.loading")} />
      ) : !shown ? (
        <Empty>{t("stats.empty")}</Empty>
      ) : (
        <div className={stats.isPlaceholderData ? "viz-root viz-stale" : "viz-root"}>
          <Totals stats={shown} />
          <div className="card">
            <MonthlyChart stats={shown} />
            <details className="viz-table">
              <summary>{t("stats.asTable")}</summary>
              <table className="table">
                <thead>
                  <tr>
                    <th>{t("stats.month")}</th>
                    <th className="num">{t("stats.in")}</th>
                    <th className="num">{t("stats.out")}</th>
                    <th className="num">{t("stats.net")}</th>
                  </tr>
                </thead>
                <tbody>
                  {shown.months.map((month) => (
                    <tr key={month.month}>
                      <td data-label={t("stats.month")}>
                        {monthLabel(month.month, true, locale)}
                      </td>
                      <td className="num" data-label={t("stats.in")}>
                        <Money minor={month.in_minor} currency={shown.currency} />
                      </td>
                      <td className="num" data-label={t("stats.out")}>
                        <Money minor={month.out_minor} currency={shown.currency} />
                      </td>
                      <td className="num" data-label={t("stats.net")}>
                        <Money minor={month.in_minor - month.out_minor} currency={shown.currency} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
          </div>
        </div>
      )}
    </section>
  );
}

function Totals({ stats }: { stats: api.CurrencyStats }) {
  const { t } = useI18n();
  const net = stats.total_in_minor - stats.total_out_minor;
  return (
    <div className="stats viz-tiles">
      <div className="card stat">
        <span className="muted small">{t("stats.in")}</span>
        <Money minor={stats.total_in_minor} currency={stats.currency} />
      </div>
      <div className="card stat">
        <span className="muted small">{t("stats.out")}</span>
        <Money minor={stats.total_out_minor} currency={stats.currency} />
      </div>
      <div className="card stat">
        <span className="muted small">{t("stats.net")}</span>
        <span className="money">
          {net > 0 ? "+" : ""}
          {formatMinor(net, stats.currency)}
        </span>
      </div>
    </div>
  );
}

function MonthlyChart({ stats }: { stats: api.CurrencyStats }) {
  const { t, locale } = useI18n();
  const [container, width] = useWidth(640);
  // Which month the pointer or keyboard is on.
  const [active, setActive] = useState<number | null>(null);

  const plotWidth = Math.max(width - MARGIN.left - MARGIN.right, 60);
  const plotHeight = HEIGHT - MARGIN.top - MARGIN.bottom;
  const baseline = MARGIN.top + plotHeight;
  // Major units, for the scale only.
  const major = (minor: number) => minor / 100;
  const largest = Math.max(...stats.months.flatMap((m) => [major(m.in_minor), major(m.out_minor)]));
  const ticks = niceTicks(largest);
  const top = ticks.at(-1) ?? 1;
  const y = (value: number) => baseline - (value / top) * plotHeight;

  const band = plotWidth / stats.months.length;
  // Thin marks: capped, never filling the band.
  const bar = Math.max(Math.min(BAR_MAX, (band - BAR_GAP) / 2 - 4), 3);
  const focused = active === null ? null : stats.months[active];
  // Every other label when months get crowded on a phone.
  const labelEvery = band < 34 ? 2 : 1;

  return (
    <figure className="viz-chart">
      <figcaption className="viz-head">
        <strong>{t("stats.perMonth", { currency: stats.currency })}</strong>
        <ul className="viz-legend">
          <li>
            <span className="viz-swatch viz-in" aria-hidden="true" /> {t("stats.in")}
          </li>
          <li>
            <span className="viz-swatch viz-out" aria-hidden="true" /> {t("stats.out")}
          </li>
        </ul>
      </figcaption>
      <div className="viz-plot" ref={container}>
        <svg
          width={width}
          height={HEIGHT}
          // A group, not one image: each month inside is focusable and
          // announces its own two values.
          role="group"
          aria-label={t("stats.chartLabel", { currency: stats.currency })}
        >
          {ticks.map((tick) => (
            <g key={tick}>
              <line
                className="viz-grid"
                x1={MARGIN.left}
                x2={MARGIN.left + plotWidth}
                y1={y(tick)}
                y2={y(tick)}
              />
              <text className="viz-tick" x={MARGIN.left - 8} y={y(tick)} dy="0.32em" textAnchor="end">
                {compact(tick)}
              </text>
            </g>
          ))}
          {stats.months.map((month, index) => {
            const centre = MARGIN.left + band * index + band / 2;
            return (
              <g
                key={month.month}
                className={active === index ? "viz-group viz-active" : "viz-group"}
                tabIndex={0}
                role="img"
                aria-label={t("stats.monthLabel", {
                  month: monthLabel(month.month, true, locale),
                  in: formatMinor(month.in_minor, stats.currency),
                  out: formatMinor(month.out_minor, stats.currency),
                })}
                onPointerEnter={() => setActive(index)}
                onPointerLeave={() => setActive(null)}
                onFocus={() => setActive(index)}
                onBlur={() => setActive(null)}
              >
                {/* The whole band is the target, not just the painted pixels. */}
                <rect
                  className="viz-hit"
                  x={MARGIN.left + band * index}
                  y={MARGIN.top}
                  width={band}
                  height={plotHeight}
                />
                <path
                  className="viz-in"
                  d={columnPath(
                    centre - bar - BAR_GAP / 2,
                    baseline,
                    bar,
                    baseline - y(major(month.in_minor)),
                  )}
                />
                <path
                  className="viz-out"
                  d={columnPath(
                    centre + BAR_GAP / 2,
                    baseline,
                    bar,
                    baseline - y(major(month.out_minor)),
                  )}
                />
                {index % labelEvery === 0 && (
                  <text className="viz-tick" x={centre} y={baseline + 18} textAnchor="middle">
                    {monthLabel(month.month, false, locale)}
                  </text>
                )}
              </g>
            );
          })}
          <line
            className="viz-axis"
            x1={MARGIN.left}
            x2={MARGIN.left + plotWidth}
            y1={baseline}
            y2={baseline}
          />
        </svg>
        {focused && active !== null && (
          <div
            className={
              active >= stats.months.length / 2 ? "viz-tooltip viz-tooltip-left" : "viz-tooltip"
            }
            // Positioned from the data, so it has to be a computed style.
            style={{ left: MARGIN.left + band * active + band / 2 }}
            role="status"
          >
            <span className="muted small">{monthLabel(focused.month, true, locale)}</span>
            <span className="viz-tooltip-row">
              <span className="viz-key viz-in" aria-hidden="true" />
              <strong>{formatMinor(focused.in_minor, stats.currency)}</strong>
              <span className="muted small">{t("stats.inShort")}</span>
            </span>
            <span className="viz-tooltip-row">
              <span className="viz-key viz-out" aria-hidden="true" />
              <strong>{formatMinor(focused.out_minor, stats.currency)}</strong>
              <span className="muted small">{t("stats.outShort")}</span>
            </span>
          </div>
        )}
      </div>
    </figure>
  );
}
