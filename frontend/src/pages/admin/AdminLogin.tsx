import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { ApiError, login } from "../../services/api";
import styles from "./AdminLogin.module.css";

export default function AdminLogin() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(username, password);
      navigate("/admin/dashboard", { replace: true });
    } catch (err) {
      if (err instanceof ApiError && err.status === 429) {
        setError(t("admin.login.rate_limited", { seconds: err.retryAfterSeconds ?? "a few" }));
      } else {
        setError(t("admin.login.invalid"));
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className={styles.wrap}>
      <h1>{t("admin.login.title")}</h1>
      <form className={styles.form} onSubmit={handleSubmit}>
        <div className={styles.field}>
          <label htmlFor="username">{t("admin.login.username")}</label>
          <input
            id="username"
            name="username"
            type="text"
            autoComplete="username"
            required
            value={username}
            onChange={(event) => setUsername(event.target.value)}
          />
        </div>
        <div className={styles.field}>
          <label htmlFor="password">{t("admin.login.password")}</label>
          <input
            id="password"
            name="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </div>
        {error && (
          <p className={styles.errorMsg} role="alert">
            {error}
          </p>
        )}
        <button type="submit" className={styles.submit} disabled={submitting}>
          {t("admin.login.submit")}
        </button>
      </form>
    </section>
  );
}
