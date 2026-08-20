import { useTranslation } from "react-i18next";

import { useAnalytics } from "../../hooks/useAnalytics";
import styles from "./LanguageSwitcher.module.css";

const LANGUAGES = [
  { code: "en", label: "EN" },
  { code: "es", label: "ES" },
] as const;

export default function LanguageSwitcher() {
  const { i18n } = useTranslation();
  const { track } = useAnalytics();

  function handleChange(code: string) {
    track("language_change", { metadata: { from: i18n.language, to: code } });
    i18n.changeLanguage(code);
  }

  return (
    <div className={styles.switcher} role="group" aria-label="Language selection">
      {LANGUAGES.map(({ code, label }) => (
        <button
          key={code}
          type="button"
          aria-pressed={i18n.language.startsWith(code)}
          onClick={() => handleChange(code)}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
