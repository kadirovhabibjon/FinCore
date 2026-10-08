// Light, dark, or whatever the system uses. A forced theme is a
// data-theme attribute on <html> (styles.css keys the dark values on
// it); "system" removes the attribute and the media query decides.
// public/theme-boot.js applies the saved choice before the app loads.
import { useSyncExternalStore } from "react";

export type Theme = "system" | "light" | "dark";

const STORAGE_KEY = "fincore:theme";
const listeners = new Set<() => void>();

function saved(): Theme {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    if (value === "light" || value === "dark") return value;
  } catch {
    // Storage can be unavailable (private mode): follow the system.
  }
  return "system";
}

let current: Theme = saved();

function apply(theme: Theme): void {
  if (typeof document === "undefined") return;
  if (theme === "system") document.documentElement.removeAttribute("data-theme");
  else document.documentElement.setAttribute("data-theme", theme);
}
apply(current);

export function getTheme(): Theme {
  return current;
}

export function setTheme(theme: Theme): void {
  current = theme;
  try {
    if (theme === "system") localStorage.removeItem(STORAGE_KEY);
    else localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    // The choice just won't be remembered.
  }
  apply(theme);
  listeners.forEach((listener) => listener());
}

/** For tests: back to what a fresh visitor gets. */
export function resetTheme(): void {
  current = saved();
  apply(current);
  listeners.forEach((listener) => listener());
}

/** What is on screen right now, whichever way it was decided. */
export function shownTheme(): "light" | "dark" {
  if (current !== "system") return current;
  const dark =
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-color-scheme: dark)").matches;
  return dark ? "dark" : "light";
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useTheme(): Theme {
  return useSyncExternalStore(subscribe, getTheme, getTheme);
}
