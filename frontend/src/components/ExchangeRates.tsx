import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { getExchangeRates } from "../api/rates";
import { convert, currencyName, formatRate, parseAmount } from "../lib/rates";
import { DateTime, Loading } from "./ui";
import { useI18n } from "../i18n";

const POPULAR = ["USD", "EUR", "RUB", "GBP", "KZT", "CNY", "TRY", "AED"];
const STORAGE_KEY = "fincore:rates-pair";

function storedPair(): { from: string; to: string } {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null") as unknown;
    if (saved && typeof saved === "object") {
      const { from, to } = saved as Record<string, unknown>;
      if (typeof from === "string" && typeof to === "string") return { from, to };
    }
  } catch {
    // Unreadable storage or a value written by hand: use the default pair.
  }
  return { from: "USD", to: "UZS" };
}

/** Reference rates and a converter. Information only: FinCore wallets
 * hold UZS or USD; exchanging between those two is the Exchange page,
 * which gets its own, binding quote from the server. */
export function ExchangeRates() {
  const { t, tr, locale } = useI18n();
  const rates = useQuery({
    queryKey: ["rates"],
    queryFn: getExchangeRates,
    staleTime: 10 * 60 * 1000,
    // The gateway already answers from its cache when the provider is
    // down; if even that fails, say so rather than keep a spinner up.
    retry: false,
  });
  const [pair, setPair] = useState(storedPair);
  const [amount, setAmount] = useState("1");

  function choose(next: { from: string; to: string }) {
    setPair(next);
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    } catch {
      // The choice just won't be remembered.
    }
  }

  const table = rates.data?.rates;
  const codes = table ? Object.keys(table).sort() : [];
  // A remembered currency the provider no longer lists falls back to the default.
  const from = table && table[pair.from] === undefined ? "USD" : pair.from;
  const to = table && table[pair.to] === undefined ? "UZS" : pair.to;
  const parsed = parseAmount(amount);
  const result = table && parsed !== null ? convert(parsed, from, to, table) : null;
  const options = codes.map((code) => (
    <option key={code} value={code}>
      {code} — {currencyName(code, locale)}
    </option>
  ));

  return (
    <section className="rates" aria-labelledby="rates-heading">
      <h2 id="rates-heading">{t("rates.title")}</h2>
      {rates.isError && <p className="muted">{t("rates.unavailable")}</p>}
      {rates.isPending ? (
        <Loading what={t("rates.loading")} />
      ) : table ? (
        <div className="rates-layout">
          <div className="card rates-converter">
            <label>
              {t("rates.amount")}
              <input
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                inputMode="decimal"
                aria-invalid={parsed === null}
              />
            </label>
            <div className="rates-pair">
              <label>
                {t("rates.from")}
                <select value={from} onChange={(e) => choose({ from: e.target.value, to })}>
                  {options}
                </select>
              </label>
              <button
                type="button"
                className="button button-ghost rates-swap"
                aria-label={t("rates.swap")}
                onClick={() => choose({ from: to, to: from })}
              >
                ⇄
              </button>
              <label>
                {t("rates.to")}
                <select value={to} onChange={(e) => choose({ from, to: e.target.value })}>
                  {options}
                </select>
              </label>
            </div>
            <output className="rates-result" aria-live="polite">
              {result === null ? (
                <span className="muted">{t("rates.enter")}</span>
              ) : (
                <>
                  <span className="muted">
                    {formatRate(parsed ?? 0)} {from} =
                  </span>{" "}
                  <strong>
                    {formatRate(result)} {to}
                  </strong>
                </>
              )}
            </output>
          </div>
          <div className="card">
            <ul className="rates-list">
              {POPULAR.filter((code) => code !== to && table[code] !== undefined).map((code) => (
                <li key={code}>
                  <button
                    type="button"
                    className="rates-row"
                    onClick={() => choose({ from: code, to })}
                    aria-pressed={code === from}
                  >
                    <span>
                      <strong>{code}</strong>{" "}
                      <span className="muted small">{currencyName(code, locale)}</span>
                    </span>
                    <span>
                      {formatRate(convert(1, code, to, table) ?? 0)} {to}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </div>
      ) : null}
      {rates.data && (
        <p className="muted small">
          {tr("rates.note", {
            updated: rates.data.updatedAt
              ? tr("rates.updated", {
                  when: <DateTime value={rates.data.updatedAt.toISOString()} />,
                })
              : "",
            source: (
              <a href="https://www.exchangerate-api.com" target="_blank" rel="noreferrer">
                ExchangeRate-API
              </a>
            ),
          })}
        </p>
      )}
    </section>
  );
}
