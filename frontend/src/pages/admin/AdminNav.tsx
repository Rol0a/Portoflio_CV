import { NavLink } from "react-router-dom";
import { useTranslation } from "react-i18next";

import styles from "./AdminNav.module.css";

export default function AdminNav() {
  const { t } = useTranslation();

  return (
    <nav className={styles.nav} aria-label="Admin sections">
      <NavLink
        to="/admin/dashboard"
        className={({ isActive }) => `${styles.link} ${isActive ? styles.active : ""}`}
      >
        {t("admin.nav_analytics")}
      </NavLink>
      <NavLink
        to="/admin/network-health"
        className={({ isActive }) => `${styles.link} ${isActive ? styles.active : ""}`}
      >
        {t("admin.nav_network")}
      </NavLink>
    </nav>
  );
}
