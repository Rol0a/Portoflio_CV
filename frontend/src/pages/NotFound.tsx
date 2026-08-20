import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

export default function NotFound() {
  const { t } = useTranslation();

  return (
    <section>
      <h1>{t("not_found.title")}</h1>
      <p>{t("not_found.body")}</p>
      <Link to="/">{t("not_found.home_link")}</Link>
    </section>
  );
}
