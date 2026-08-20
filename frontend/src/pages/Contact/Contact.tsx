import { useState } from "react";
import { useTranslation } from "react-i18next";

import { GITHUB_URL, LINKEDIN_URL } from "../../config/profile";
import { InView } from "../../components/motion/InView";
import PageHeader from "../../components/PageHeader/PageHeader";
import { useAnalytics } from "../../hooks/useAnalytics";
import { ApiError, postContactMessage } from "../../services/api";
import styles from "./Contact.module.css";

type Status = "idle" | "sending" | "sent" | "error";

export default function Contact() {
  const { t } = useTranslation();
  const { track } = useAnalytics();
  const [status, setStatus] = useState<Status>("idle");
  const [errorKey, setErrorKey] = useState("contact.error");

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (status === "sending") return;

    const form = event.currentTarget;
    const data = new FormData(form);
    setStatus("sending");

    // Records only that a submission happened — never the field values.
    // Asserted in src/hooks/useAnalytics.test.tsx.
    track("contact_click");

    try {
      await postContactMessage({
        name: String(data.get("name") ?? ""),
        email: String(data.get("email") ?? ""),
        message: String(data.get("message") ?? ""),
        website: String(data.get("website") ?? ""),
      });
      setStatus("sent");
      form.reset();
    } catch (error) {
      // Tell the visitor what actually went wrong, so they can fall back to
      // the direct email link rather than assuming the message was sent.
      setErrorKey(
        error instanceof ApiError && error.status === 429
          ? "contact.error_rate_limited"
          : "contact.error",
      );
      setStatus("error");
    }
  }

  return (
    <section className="page-section">
      <PageHeader eyebrow={t("contact.eyebrow")} title={t("contact.title")} intro={t("contact.intro")} />
      <div className={styles.layout}>
        <InView className={styles.formCol}>
          <form className={styles.form} onSubmit={handleSubmit}>
            <div className={styles.field}>
              <label htmlFor="name">{t("contact.name")}</label>
              <input id="name" name="name" type="text" maxLength={100} required />
            </div>
            <div className={styles.field}>
              <label htmlFor="email">{t("contact.email")}</label>
              <input id="email" name="email" type="email" maxLength={254} required />
            </div>
            <div className={styles.field}>
              <label htmlFor="message">{t("contact.message")}</label>
              <textarea id="message" name="message" rows={5} maxLength={5000} required />
            </div>

            {/* Honeypot: hidden from people and from screen readers, and kept
                out of the tab order, so only a form-filling bot completes it.
                Styled off-screen rather than display:none — some bots skip
                fields that are not rendered at all. */}
            <div className={styles.honeypot} aria-hidden="true">
              <label htmlFor="website">Website</label>
              <input id="website" name="website" type="text" tabIndex={-1} autoComplete="off" />
            </div>

            <button type="submit" className={styles.submit} disabled={status === "sending"}>
              {status === "sending" ? t("contact.sending") : t("contact.send")}
            </button>

            {/* role=status announces the outcome to screen readers without
                moving focus away from the form. */}
            <p className={styles.status} role="status" aria-live="polite">
              {status === "sent" && t("contact.success")}
              {status === "error" && t(errorKey)}
            </p>
          </form>
        </InView>

        <InView delay={0.08} className={styles.elsewhere}>
          <h2 className={styles.elsewhereTitle}>{t("contact.elsewhere_title")}</h2>
          <p className={styles.elsewhereBody}>{t("contact.elsewhere_body")}</p>
          <ul className={styles.elsewhereList}>
            <li>{t("about.email")}</li>
            <li>{t("about.location")}</li>
            <li>
              <a href={GITHUB_URL} target="_blank" rel="noreferrer">
                GitHub ↗
              </a>
            </li>
            <li>
              <a href={LINKEDIN_URL} target="_blank" rel="noreferrer">
                LinkedIn ↗
              </a>
            </li>
          </ul>
        </InView>
      </div>
    </section>
  );
}
