import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Suspense, lazy, useEffect } from "react";

import { useAnalytics } from "./hooks/useAnalytics";
import Layout from "./components/Layout/Layout";
import Home from "./pages/Home/Home";
import Experience from "./pages/Experience/Experience";
import ProjectList from "./pages/Projects/ProjectList";
import ProjectDetail from "./pages/Projects/ProjectDetail";
import Contact from "./pages/Contact/Contact";
import AdminLogin from "./pages/admin/AdminLogin";
import NotFound from "./pages/NotFound";

// recharts (~450kB) is only needed by the admin dashboard — code-split so
// public visitors never download it.
const AdminDashboard = lazy(() => import("./pages/admin/AdminDashboard"));

// Skills carries ~40kB of inlined SVG icon paths (see components/SkillBadge/
// icons.ts). Measured: static-importing it put 20kB gzipped into the entry
// bundle that only one route ever reads. Split for the same reason as recharts.
const Skills = lazy(() => import("./pages/Skills/Skills"));
const NetworkHealth = lazy(() => import("./pages/admin/NetworkHealth"));

export default function App() {
  const { i18n, t } = useTranslation();
  const { track } = useAnalytics();
  const location = useLocation();

  useEffect(() => {
    document.documentElement.lang = i18n.language;
  }, [i18n.language]);

  useEffect(() => {
    // Admin's own visits to /admin* shouldn't pollute the traffic they're viewing.
    if (location.pathname.startsWith("/admin")) return;
    track("page_view", { metadata: { path: location.pathname } });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname]);

  useEffect(() => {
    // The admin screens are monochrome by design — see the `:root[data-admin]`
    // block in styles/global.css. Stamping the document root rather than the
    // page's own <section> is the whole point: it takes the shared header,
    // footer and body ground monochrome too, instead of framing a black-and-
    // white dashboard in cream.
    if (!location.pathname.startsWith("/admin")) return;
    document.documentElement.setAttribute("data-admin", "");
    return () => document.documentElement.removeAttribute("data-admin");
  }, [location.pathname]);

  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Home />} />
        <Route path="experience" element={<Experience />} />
        <Route
          path="skills"
          element={
            <Suspense fallback={<p className="page-section">{t("common.loading")}</p>}>
              <Skills />
            </Suspense>
          }
        />
        <Route path="projects" element={<ProjectList />} />
        <Route path="projects/:slug" element={<ProjectDetail />} />
        <Route path="contact" element={<Contact />} />

        {/* Both pages were merged away, but their URLs are the ones already
            sitting in someone's history, a CV PDF, or a LinkedIn post. Redirect
            rather than 404. `replace` keeps the dead URL out of the back stack. */}
        <Route path="about" element={<Navigate to="/experience" replace />} />
        <Route path="certifications" element={<Navigate to="/skills" replace />} />

        <Route path="admin" element={<AdminLogin />} />
        <Route
          path="admin/dashboard"
          element={
            <Suspense fallback={null}>
              <AdminDashboard />
            </Suspense>
          }
        />
        <Route
          path="admin/network-health"
          element={
            <Suspense fallback={null}>
              <NetworkHealth />
            </Suspense>
          }
        />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
