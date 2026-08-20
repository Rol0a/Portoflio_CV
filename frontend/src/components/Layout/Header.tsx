import { useEffect, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";

import LanguageSwitcher from "../LanguageSwitcher/LanguageSwitcher";
import styles from "./Header.module.css";

const NAV_ITEMS = [
  { to: "/", key: "home", end: true },
  { to: "/experience", key: "experience", end: false },
  { to: "/skills", key: "skills", end: false },
  { to: "/projects", key: "projects", end: false },
  { to: "/contact", key: "contact", end: false },
] as const;

function MenuIcon({ open }: { open: boolean }) {
  return (
    <svg className={styles.menuIcon} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      {open ? (
        <path d="M6 6l12 12M18 6L6 18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      ) : (
        <path d="M4 7h16M4 12h16M4 17h16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      )}
    </svg>
  );
}

export default function Header() {
  const { t } = useTranslation();
  const location = useLocation();
  const [open, setOpen] = useState(false);

  // Close the mobile menu on every navigation, including a tap on the link
  // the visitor is already on (e.g. re-tapping the current page).
  useEffect(() => {
    setOpen(false);
  }, [location.pathname]);

  return (
    <header className={styles.header}>
      <div className={`container ${styles.inner}`}>
        <NavLink to="/" className={styles.brand}>
          {t("home.title")}
        </NavLink>

        <button
          type="button"
          className={styles.menuToggle}
          aria-expanded={open}
          aria-controls="main-nav"
          aria-label={open ? "Close menu" : "Open menu"}
          onClick={() => setOpen((value) => !value)}
        >
          <MenuIcon open={open} />
        </button>

        <nav id="main-nav" className={`${styles.nav} ${open ? styles.navOpen : ""}`} aria-label="Main navigation">
          <ul className={styles.navList}>
            {NAV_ITEMS.map(({ to, key, end }) => (
              <li key={key}>
                <NavLink to={to} end={end}>
                  {t(`nav.${key}`)}
                </NavLink>
              </li>
            ))}
          </ul>
          <LanguageSwitcher />
        </nav>
      </div>
    </header>
  );
}
