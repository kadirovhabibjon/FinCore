import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { StatusBadge } from "../components/ui";
import { localize } from "../lib/notifications";
import { reasonText } from "../lib/reasons";
import { en } from "./en";
import { getLang, i18n, LANGUAGES, resetLang, setLang, useI18n, type MessageKey } from "./index";
import { ru } from "./ru";
import { uz } from "./uz";

const KEYS = Object.keys(en) as MessageKey[];

function placeholders(text: string): string[] {
  return [...text.matchAll(/\{(\w+)\}/g)].map((match) => match[1]!).sort();
}

describe("translations", () => {
  it.each([
    ["uz", uz],
    ["ru", ru],
  ])("%s has every message, with the same placeholders", (_name, messages) => {
    expect(Object.keys(messages).sort()).toEqual([...KEYS].sort());
    for (const key of KEYS) {
      expect(messages[key].trim(), key).not.toBe("");
      expect(placeholders(messages[key]), key).toEqual(placeholders(en[key]));
    }
  });

  it("fills placeholders and leaves unknown ones visible", () => {
    setLang("en");
    expect(i18n().t("bell.labelUnread", { count: 3 })).toBe("Notifications, 3 unread");
    expect(i18n().t("bell.labelUnread")).toBe("Notifications, {count} unread");
  });
});

describe("language choice", () => {
  it("starts in English and remembers a change", () => {
    expect(getLang()).toBe("en");
    setLang("uz");
    expect(localStorage.getItem("fincore:lang")).toBe("uz");
    expect(document.documentElement.lang).toBe("uz");
    resetLang();
    expect(getLang()).toBe("uz");
  });

  it("ignores a saved value that is not a language", () => {
    localStorage.setItem("fincore:lang", "xx");
    resetLang();
    expect(getLang()).toBe("en");
  });

  it("re-renders what is on screen when the language changes", async () => {
    function Sample() {
      const { t, lang } = useI18n();
      return (
        <>
          <p>{t("bell.news")}</p>
          <select aria-label="language" value={lang} onChange={(e) => setLang(e.target.value as never)}>
            {LANGUAGES.map((item) => (
              <option key={item.code} value={item.code}>
                {item.label}
              </option>
            ))}
          </select>
          <StatusBadge status="COMPLETED" />
        </>
      );
    }
    render(<Sample />);
    expect(screen.getByText("News")).toBeInTheDocument();
    expect(screen.getByText("COMPLETED")).toBeInTheDocument();

    await userEvent.selectOptions(screen.getByLabelText("language"), "ru");
    expect(screen.getByText("Новости")).toBeInTheDocument();
    expect(screen.getByText("Выполнено")).toBeInTheDocument();

    act(() => setLang("uz"));
    expect(screen.getByText("Yangiliklar")).toBeInTheDocument();
    expect(screen.getByText("Bajarildi")).toBeInTheDocument();
  });
});

describe("server text in the reader's language", () => {
  const received = {
    id: "n1",
    type: "transfer.received",
    title: "Money received",
    body: "Aziza K. sent you 10.00 USD.",
    read: false,
    created_at: "2026-01-01T00:00:00Z",
    params: { amount: "10.00 USD", reference: "TRF-1", counterparty: "Aziza K." },
  };

  it("keeps the server's own words in English", () => {
    setLang("en");
    expect(localize(received, i18n())).toEqual({ title: received.title, body: received.body });
  });

  it("rebuilds a notification from its facts", () => {
    setLang("uz");
    expect(localize(received, i18n())).toEqual({
      title: "Pul kelib tushdi",
      body: "Aziza K. sizga 10.00 USD yubordi.",
    });
    setLang("ru");
    expect(localize({ ...received, params: { amount: "10.00 USD", reference: "TRF-1" } }, i18n()).body).toBe(
      "Вам поступило 10.00 USD.",
    );
  });

  it("falls back to the server text without facts or for an unknown type", () => {
    setLang("uz");
    expect(localize({ ...received, params: null }, i18n()).body).toBe(received.body);
    const announcement = { ...received, type: "announcement", title: "Maintenance", body: "Tonight." };
    expect(localize(announcement, i18n())).toEqual({ title: "Maintenance", body: "Tonight." });
  });

  it("translates a failure reason, known or not", () => {
    setLang("ru");
    const failed = {
      ...received,
      type: "transfer.failed",
      params: { amount: "5.00 USD", reference: "TRF-2", reason: "Insufficient Funds" },
    };
    expect(localize(failed, i18n()).body).toBe(
      "Ваш перевод TRF-2 на 5.00 USD не выполнен: Недостаточно средств.",
    );
    expect(reasonText("blocked by fraud check", i18n())).toBe("заблокировано проверкой безопасности");
    expect(reasonText("something new", i18n())).toBe("something new");
  });
});
