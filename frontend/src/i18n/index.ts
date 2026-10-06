// The site in three languages. No provider and no library: the chosen
// language lives in a tiny store that components subscribe to, so
// anything rendered anywhere (including the error boundary, outside
// every provider) reads the same language.
import { Fragment, createElement, useSyncExternalStore, type ReactNode } from "react";

import { en, type MessageKey } from "./en";
import { ru } from "./ru";
import { uz } from "./uz";

export type { MessageKey };
export type Lang = "uz" | "ru" | "en";

export const LANGUAGES: { code: Lang; label: string; name: string }[] = [
  { code: "uz", label: "UZ", name: "O‘zbekcha" },
  { code: "ru", label: "RU", name: "Русский" },
  { code: "en", label: "EN", name: "English" },
];

const MESSAGES: Record<Lang, Record<MessageKey, string>> = { en, uz, ru };
// What dates and numbers are formatted with.
const LOCALES: Record<Lang, string> = { en: "en-US", uz: "uz-Latn-UZ", ru: "ru-RU" };
const STORAGE_KEY = "fincore:lang";

function isLang(value: unknown): value is Lang {
  return value === "uz" || value === "ru" || value === "en";
}

/** The language to start in: the one chosen before on this device,
 * else the browser's if it is one of ours, else English. */
function initialLang(): Lang {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (isLang(saved)) return saved;
  } catch {
    // Storage can be unavailable (private mode): fall through.
  }
  const browser = (typeof navigator !== "undefined" ? navigator.language : "").toLowerCase();
  if (browser.startsWith("uz")) return "uz";
  if (browser.startsWith("ru")) return "ru";
  return "en";
}

let current: Lang = initialLang();
const listeners = new Set<() => void>();

function apply(lang: Lang): void {
  if (typeof document !== "undefined") document.documentElement.lang = lang;
}
apply(current);

export function getLang(): Lang {
  return current;
}

export function setLang(lang: Lang): void {
  if (lang === current) return;
  current = lang;
  try {
    localStorage.setItem(STORAGE_KEY, lang);
  } catch {
    // The choice just won't be remembered.
  }
  apply(lang);
  listeners.forEach((listener) => listener());
}

/** For tests: back to the language a fresh visitor would get. */
export function resetLang(): void {
  current = initialLang();
  apply(current);
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

type Params = Record<string, string | number>;

function template(lang: Lang, key: MessageKey): string {
  // A key missing from a translation can't compile, but fall back anyway.
  return MESSAGES[lang][key] ?? en[key] ?? key;
}

/** `t("hello", { name })` with "Hello, {name}". Unknown placeholders
 * are left as written, which makes a mistake visible instead of blank. */
export function translate(lang: Lang, key: MessageKey, params?: Params): string {
  const text = template(lang, key);
  if (!params) return text;
  return text.replace(/\{(\w+)\}/g, (whole, name: string) =>
    name in params ? String(params[name]) : whole,
  );
}

/** The same, where a placeholder is an element (a link, a bold name):
 * the sentence stays one translatable unit and each language puts the
 * element where its own word order wants it. */
export function translateRich(
  lang: Lang,
  key: MessageKey,
  params: Record<string, ReactNode>,
): ReactNode {
  const parts = template(lang, key).split(/(\{\w+\})/g);
  return createElement(
    Fragment,
    null,
    ...parts.map((part, index) => {
      const name = /^\{(\w+)\}$/.exec(part)?.[1];
      return createElement(
        Fragment,
        { key: index },
        name !== undefined && name in params ? params[name] : part,
      );
    }),
  );
}

export interface I18n {
  lang: Lang;
  locale: string;
  t: (key: MessageKey, params?: Params) => string;
  tr: (key: MessageKey, params: Record<string, ReactNode>) => ReactNode;
  /** `key` if it is a message, else undefined: for text that comes
   * from the server (statuses, error titles) and may not be known. */
  maybe: (key: string, params?: Params) => string | undefined;
}

function build(lang: Lang): I18n {
  return {
    lang,
    locale: LOCALES[lang],
    t: (key, params) => translate(lang, key, params),
    tr: (key, params) => translateRich(lang, key, params),
    maybe: (key, params) =>
      key in en ? translate(lang, key as MessageKey, params) : undefined,
  };
}

const BUILT: Record<Lang, I18n> = { en: build("en"), uz: build("uz"), ru: build("ru") };

export function useI18n(): I18n {
  const lang = useSyncExternalStore(subscribe, getLang, getLang);
  return BUILT[lang];
}

/** Outside React (a class component, a plain function). */
export function i18n(): I18n {
  return BUILT[current];
}
