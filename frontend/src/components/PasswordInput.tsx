import { useState, type InputHTMLAttributes } from "react";
import { useI18n } from "../i18n";

type Props = Omit<InputHTMLAttributes<HTMLInputElement>, "type">;

/** A password field with an eye button that shows or hides what's typed,
 * so a long password can be checked on a phone keyboard before submitting. */
export function PasswordInput(props: Props) {
  const { t } = useI18n();
  const [visible, setVisible] = useState(false);
  return (
    <span className="password-field">
      <input {...props} type={visible ? "text" : "password"} />
      <button
        type="button"
        className="password-toggle"
        aria-label={visible ? t("common.hidePassword") : t("common.showPassword")}
        aria-pressed={visible}
        onClick={() => setVisible((shown) => !shown)}
      >
        {visible ? <EyeOffIcon /> : <EyeIcon />}
      </button>
    </span>
  );
}

function EyeIcon() {
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false">
      <path
        d="M1.5 12S5.5 4.5 12 4.5 22.5 12 22.5 12 18.5 19.5 12 19.5 1.5 12 1.5 12Z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
      <circle cx="12" cy="12" r="3.2" fill="none" stroke="currentColor" strokeWidth="1.8" />
    </svg>
  );
}

function EyeOffIcon() {
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false">
      <path
        d="M3 3l18 18M10.6 5.1A10.4 10.4 0 0 1 12 4.5c6.5 0 10.5 7.5 10.5 7.5a17.6 17.6 0 0 1-3.2 4.1M6.6 6.6C3.4 8.6 1.5 12 1.5 12s4 7.5 10.5 7.5a9.8 9.8 0 0 0 5.4-1.6M9.9 9.9a3.2 3.2 0 0 0 4.2 4.2"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
