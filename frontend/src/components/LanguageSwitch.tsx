import { LANGUAGES, setLang, useI18n, type Lang } from "../i18n";

/** UZ / RU / EN. The choice applies at once and is remembered on this
 * device. */
export function LanguageSwitch({ className = "" }: { className?: string }) {
  const { t, lang } = useI18n();
  return (
    <select
      className={`lang-select ${className}`.trim()}
      aria-label={t("common.language")}
      value={lang}
      onChange={(event) => setLang(event.target.value as Lang)}
    >
      {LANGUAGES.map((language) => (
        <option key={language.code} value={language.code} title={language.name}>
          {language.label}
        </option>
      ))}
    </select>
  );
}
