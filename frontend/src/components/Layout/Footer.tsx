import { useTranslation } from "react-i18next";

import { GITHUB_URL, LINKEDIN_URL } from "../../config/profile";
import styles from "./Footer.module.css";

export default function Footer() {
  const { t } = useTranslation();
  const year = new Date().getFullYear();

  return (
    <footer className={styles.footer}>
      <div className={`container ${styles.inner}`}>
        <span className={styles.copy}>
          © {year} {t("home.title")}. {t("footer.rights")}
          <span className={styles.disclaimer}>{t("footer.disclaimer")}</span>
        </span>
        <span className={styles.links}>
          <a href={GITHUB_URL} target="_blank" rel="noreferrer">
            GitHub
          </a>
          <a href={LINKEDIN_URL} target="_blank" rel="noreferrer">
            LinkedIn
          </a>
        </span>
      </div>
    </footer>
  );
}
