import { useTranslation } from "react-i18next";

import { InView } from "../../components/motion/InView";
import PageHeader from "../../components/PageHeader/PageHeader";
import styles from "./About.module.css";

const META_KEYS = ["location", "email", "education", "focus"] as const;

export default function About() {
  const { t } = useTranslation();

  // `about.body` is an array of paragraphs, so the bio reads as prose rather
  // than one dense block. Guard the cast: a malformed bundle shouldn't blank
  // the page.
  const paragraphs = t("about.body", { returnObjects: true });
  const bodyParagraphs = Array.isArray(paragraphs) ? (paragraphs as string[]) : [String(paragraphs)];

  return (
    <section className="page-section">
      <PageHeader eyebrow={t("about.eyebrow")} title={t("about.title")} />
      <InView className={styles.layout}>
        <div className={styles.bio}>
          {bodyParagraphs.map((paragraph) => (
            <p key={paragraph}>{paragraph}</p>
          ))}
        </div>
        <div className={styles.meta}>
          <h2 className={styles.metaTitle}>{t("about.meta_title")}</h2>
          <ul className={styles.metaList}>
            {META_KEYS.map((key) => (
              <li key={key}>{t(`about.${key}`)}</li>
            ))}
          </ul>
        </div>
      </InView>
    </section>
  );
}
