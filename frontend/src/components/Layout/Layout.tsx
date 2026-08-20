import { Outlet } from "react-router-dom";

import { ScrollProgress } from "../motion/ScrollProgress";
import Header from "./Header";
import Footer from "./Footer";

export default function Layout() {
  return (
    <>
      <a href="#main-content" className="skip-link">
        Skip to content
      </a>
      <ScrollProgress />
      <Header />
      <main id="main-content" className="container">
        <Outlet />
      </main>
      <Footer />
    </>
  );
}
