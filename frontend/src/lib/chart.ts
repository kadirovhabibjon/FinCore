// Scale arithmetic for the statistics chart. Floats are fine here and
// nowhere else in this app: these numbers place marks and label an axis,
// they are never shown as an amount (those go through formatMinor).

/** Round tick values from 0 up to at least `max`: 0, 500, 1000, ... */
export function niceTicks(max: number, count = 4): number[] {
  if (!(max > 0)) return [0, 1];
  const rough = max / count;
  const magnitude = 10 ** Math.floor(Math.log10(rough));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * magnitude).find((s) => s >= rough) ?? rough;
  const ticks: number[] = [];
  for (let value = 0; value < max + step; value += step) {
    // Multiplying back avoids 0.30000000000000004-style steps.
    ticks.push(Math.round(value / step) * step);
    if (value >= max) break;
  }
  return ticks;
}

/** 1500000 -> "1.5M", 25000 -> "25K", 950 -> "950": axis labels only. */
export function compact(value: number): string {
  const format = (scaled: number, suffix: string) =>
    `${Number(scaled.toFixed(scaled < 10 ? 1 : 0))}${suffix}`;
  if (value >= 1e9) return format(value / 1e9, "B");
  if (value >= 1e6) return format(value / 1e6, "M");
  if (value >= 1e3) return format(value / 1e3, "K");
  return String(Number(value.toFixed(2)));
}

/** "2026-10" -> "Oct" (and "Jan 2026" when a year starts, or `withYear`). */
export function monthLabel(key: string, withYear = false, locale = "en-US"): string {
  const [year, month] = key.split("-").map(Number);
  const date = new Date(Date.UTC(year ?? 1970, (month ?? 1) - 1, 1));
  const name = new Intl.DateTimeFormat(locale, { month: "short", timeZone: "UTC" }).format(date);
  return withYear || month === 1 ? `${name} ${year}` : name;
}

/** A column with a rounded top and a square foot on the baseline. */
export function columnPath(x: number, baseline: number, width: number, height: number): string {
  if (height <= 0) return "";
  const radius = Math.min(4, width / 2, height);
  const top = baseline - height;
  return [
    `M${x},${baseline}`,
    `V${top + radius}`,
    `Q${x},${top} ${x + radius},${top}`,
    `H${x + width - radius}`,
    `Q${x + width},${top} ${x + width},${top + radius}`,
    `V${baseline}`,
    "Z",
  ].join(" ");
}

/** "2026-10-08" -> "8" or, where a month starts or `full`, "8 Oct". */
export function dayLabel(date: string, locale: string, full = false): string {
  const moment = new Date(`${date}T00:00:00Z`);
  const day = moment.getUTCDate();
  if (!full && day !== 1) return String(day);
  return new Intl.DateTimeFormat(locale, { day: "numeric", month: "short", timeZone: "UTC" }).format(
    moment,
  );
}
