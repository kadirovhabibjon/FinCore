import { useState, type ReactNode } from "react";

import { columnPath, compact, dayLabel, niceTicks } from "../../lib/chart";
import { useWidth } from "../../lib/useWidth";

const HEIGHT = 220;
const MARGIN = { top: 12, right: 8, bottom: 26, left: 36 };
const BAR_MAX = 22;

export interface ChartDay {
  /** "2026-10-08" */
  date: string;
  value: number;
  /** What a screen reader hears for this day. */
  label: string;
  /** What the tooltip adds under the value: the breakdown. */
  detail?: ReactNode;
}

/** One count per day as columns: a single series on one axis, named by
 * its title (so no legend), with a readout for the day under the
 * pointer or the keyboard. The numbers are also given as a table by
 * whoever uses this. */
export function DailyChart({
  title,
  ariaLabel,
  days,
  unit,
  locale,
}: {
  title: string;
  ariaLabel: string;
  days: ChartDay[];
  /** What the value counts, in the tooltip: "operations". */
  unit: string;
  locale: string;
}) {
  const [container, width] = useWidth(520);
  const [active, setActive] = useState<number | null>(null);

  const plotWidth = Math.max(width - MARGIN.left - MARGIN.right, 60);
  const plotHeight = HEIGHT - MARGIN.top - MARGIN.bottom;
  const baseline = MARGIN.top + plotHeight;
  // Counts: whole ticks only, and room for at least one.
  const ticks = niceTicks(Math.max(...days.map((day) => day.value), 1)).filter(Number.isInteger);
  const top = ticks.at(-1) ?? 1;
  const y = (value: number) => baseline - (value / top) * plotHeight;
  const band = plotWidth / Math.max(days.length, 1);
  const bar = Math.max(Math.min(BAR_MAX, band - 6), 3);
  // Fewer labels when days get crowded.
  const labelEvery = Math.ceil(30 / band);
  const focused = active === null ? null : days[active];

  return (
    <figure className="viz-chart viz-root">
      <figcaption className="viz-head">
        <strong>{title}</strong>
      </figcaption>
      <div className="viz-plot" ref={container}>
        <svg width={width} height={HEIGHT} role="group" aria-label={ariaLabel}>
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
          {days.map((day, index) => {
            const centre = MARGIN.left + band * index + band / 2;
            return (
              <g
                key={day.date}
                className={active === index ? "viz-group viz-active" : "viz-group"}
                tabIndex={0}
                role="img"
                aria-label={day.label}
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
                  d={columnPath(centre - bar / 2, baseline, bar, baseline - y(day.value))}
                />
                {(index % labelEvery === 0 || index === days.length - 1) && (
                  <text className="viz-tick" x={centre} y={baseline + 17} textAnchor="middle">
                    {dayLabel(day.date, locale)}
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
            className={active >= days.length / 2 ? "viz-tooltip viz-tooltip-left" : "viz-tooltip"}
            // Positioned from the data, so it has to be a computed style.
            style={{ left: MARGIN.left + band * active + band / 2 }}
            role="status"
          >
            <span className="muted small">{dayLabel(focused.date, locale, true)}</span>
            <span className="viz-tooltip-row">
              <span className="viz-key viz-in" aria-hidden="true" />
              <strong>{focused.value}</strong>
              <span className="muted small">{unit}</span>
            </span>
            {focused.detail}
          </div>
        )}
      </div>
    </figure>
  );
}
