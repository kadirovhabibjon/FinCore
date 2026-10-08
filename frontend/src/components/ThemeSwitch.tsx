import { useI18n, type MessageKey } from "../i18n";
import { setTheme, shownTheme, useTheme, type Theme } from "../lib/theme";

const SUN = (
  <>
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
  </>
);
const MOON = <path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z" />;

/** One button in the top bar: switches to the other of light and dark. */
export function ThemeButton() {
  const { t } = useI18n();
  useTheme();
  const dark = shownTheme() === "dark";
  const label = dark ? t("theme.toLight") : t("theme.toDark");
  return (
    <button
      type="button"
      className="button button-ghost theme-button"
      aria-label={label}
      title={label}
      onClick={() => setTheme(dark ? "light" : "dark")}
    >
      <svg
        viewBox="0 0 24 24"
        width="20"
        height="20"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
        focusable="false"
      >
        {dark ? SUN : MOON}
      </svg>
    </button>
  );
}

const CHOICES: { theme: Theme; label: MessageKey }[] = [
  { theme: "system", label: "theme.system" },
  { theme: "light", label: "theme.light" },
  { theme: "dark", label: "theme.dark" },
];

/** All three choices, on the Account page. */
export function ThemeChoice() {
  const { t } = useI18n();
  const theme = useTheme();
  return (
    <div className="card theme-choice" role="group" aria-label={t("theme.title")}>
      {CHOICES.map((choice) => (
        <button
          key={choice.theme}
          type="button"
          className="button button-ghost"
          aria-pressed={theme === choice.theme}
          onClick={() => setTheme(choice.theme)}
        >
          {t(choice.label)}
        </button>
      ))}
    </div>
  );
}
