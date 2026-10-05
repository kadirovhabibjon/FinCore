import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { getExchangeRates } from "../api/rates";
import { convert, currencyName, formatRate, parseAmount } from "../lib/rates";
import { DateTime, Loading } from "./ui";

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
 * hold UZS or USD and never exchange one for the other. */
export function ExchangeRates() {
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
      {code} — {currencyName(code)}
    </option>
  ));

  return (
    <section className="rates" aria-labelledby="rates-heading">
      <h2 id="rates-heading">Exchange rates</h2>
      {rates.isError && <p className="muted">Exchange rates are unavailable right now.</p>}
      {rates.isPending ? (
        <Loading what="Loading rates" />
      ) : table ? (
        <div className="rates-layout">
          <div className="card rates-converter">
            <label>
              Amount
              <input
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                inputMode="decimal"
                aria-invalid={parsed === null}
              />
            </label>
            <div className="rates-pair">
              <label>
                From
                <select value={from} onChange={(e) => choose({ from: e.target.value, to })}>
                  {options}
                </select>
              </label>
              <button
                type="button"
                className="button button-ghost rates-swap"
                aria-label="Swap currencies"
                onClick={() => choose({ from: to, to: from })}
              >
                ⇄
              </button>
              <label>
                To
                <select value={to} onChange={(e) => choose({ from, to: e.target.value })}>
                  {options}
                </select>
              </label>
            </div>
            <output className="rates-result" aria-live="polite">
              {result === null ? (
                <span className="muted">Enter an amount</span>
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
                      <span className="muted small">{currencyName(code)}</span>
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
          Reference rates for information only
          {rates.data.updatedAt && (
            <>
              , updated <DateTime value={rates.data.updatedAt.toISOString()} />
            </>
          )}
          . FinCore wallets hold UZS or USD and don&apos;t exchange currencies. Source:{" "}
          <a href="https://www.exchangerate-api.com" target="_blank" rel="noreferrer">
            ExchangeRate-API
          </a>
          .
        </p>
      )}
    </section>
  );
}
