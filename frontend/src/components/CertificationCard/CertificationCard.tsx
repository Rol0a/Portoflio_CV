import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { useTilt } from "../../hooks/useTilt";
import type { Certification } from "../../types";
import styles from "./CertificationCard.module.css";

interface CertificationCardProps {
  certification: Certification;
}

export default function CertificationCard({ certification }: CertificationCardProps) {
  const { t, i18n } = useTranslation();
  const tilt = useTilt<HTMLDivElement>();
  const [badgeFailed, setBadgeFailed] = useState(false);

  // A stale/broken badge URL on one certification shouldn't hide a working
  // badge on another — reset per certification, same as ProjectDetail's hero.
  useEffect(() => {
    setBadgeFailed(false);
  }, [certification.badgeImageUrl]);

  const issued = new Intl.DateTimeFormat(i18n.language, { year: "numeric", month: "short" }).format(
    new Date(certification.issueDate),
  );
  const initials = certification.issuer
    .split(" ")
    .map((word) => word[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  return (
    <div
      className={styles.card}
      ref={tilt.ref}
      onMouseMove={tilt.handleMouseMove}
      onMouseLeave={tilt.handleMouseLeave}
    >
      <span className={styles.sheen} aria-hidden="true" />
      <div className={styles.badgeRow}>
        {certification.badgeImageUrl && !badgeFailed ? (
          <img
            className={styles.badge}
            src={certification.badgeImageUrl}
            alt=""
            onError={() => setBadgeFailed(true)}
          />
        ) : (
          <span className={styles.badgePlaceholder} aria-hidden="true">
            {initials}
          </span>
        )}
        <div>
          <p className={styles.issuer}>{certification.issuer}</p>
          <h3 className={styles.title}>{certification.title}</h3>
        </div>
      </div>
      {certification.description && <p className={styles.desc}>{certification.description}</p>}
      <div className={styles.meta}>
        <span>
          {t("certifications.issued")} {issued}
        </span>
        {certification.credentialUrl && (
          <a
            className={styles.link}
            href={certification.credentialUrl}
            target="_blank"
            rel="noreferrer"
          >
            {t("certifications.view_credential")}
          </a>
        )}
      </div>
    </div>
  );
}
