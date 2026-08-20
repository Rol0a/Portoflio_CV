import { Route, Routes, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Suspense, lazy, useEffect } from "react";

import { useAnalytics } from "./hooks/useAnalytics";
import Layout from "./components/Layout/Layout";
import Home from "./pages/Home/Home";
import About from "./pages/About/About";
import Skills from "./pages/Skills/Skills";
import ProjectList from "./pages/Projects/ProjectList";
import ProjectDetail from "./pages/Projects/ProjectDetail";
import Certifications from "./pages/Certifications/Certifications";
import Contact from "./pages/Contact/Contact";
import AdminLogin from "./pages/admin/AdminLogin";
import NotFound from "./pages/NotFound";

// recharts (~450kB) is only needed by the admin dashboard — code-split so
// public visitors never download it.
const AdminDashboard = lazy(() => import("./pages/admin/AdminDashboard"));
const NetworkHealth = lazy(() => import("./pages/admin/NetworkHealth"));

export default function App() {
  const { i18n } = useTranslation();
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

  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Home />} />
        <Route path="about" element={<About />} />
        <Route path="skills" element={<Skills />} />
        <Route path="projects" element={<ProjectList />} />
        <Route path="projects/:slug" element={<ProjectDetail />} />
        <Route path="certifications" element={<Certifications />} />
        <Route path="contact" element={<Contact />} />
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
