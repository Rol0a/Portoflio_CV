import { useTranslation } from "react-i18next";

import CertificationCard from "../../components/CertificationCard/CertificationCard";
import { AnimatedGroup } from "../../components/motion/AnimatedGroup";
import PageHeader from "../../components/PageHeader/PageHeader";
import { useCertifications } from "../../hooks/useCertifications";
import styles from "./Certifications.module.css";

export default function Certifications() {
  const { t } = useTranslation();
  const { data: certifications, loading, error } = useCertifications();

  return (
    <section className="page-section">
      <PageHeader
        eyebrow={t("certifications.eyebrow")}
        title={t("certifications.title")}
        intro={t("certifications.intro")}
      />
      {loading && <p>{t("common.loading")}</p>}
      {error && <p role="alert">{t("common.error")}</p>}
      {!loading && !error && certifications && certifications.length === 0 && <p>{t("common.empty")}</p>}
      {!loading && !error && certifications && certifications.length > 0 && (
        <AnimatedGroup className={styles.grid}>
          {certifications.map((certification) => (
            <CertificationCard key={certification.slug} certification={certification} />
          ))}
        </AnimatedGroup>
      )}
    </section>
  );
}
