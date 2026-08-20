import { useMemo } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import CertificationCard from "../../components/CertificationCard/CertificationCard";
import { AnimatedGroup } from "../../components/motion/AnimatedGroup";
import { InView } from "../../components/motion/InView";
import { ParallaxBlob } from "../../components/motion/ParallaxBlob";
import { TextEffect } from "../../components/motion/TextEffect";
import { ProjectShowcase } from "../../components/ProjectShowcase/ProjectShowcase";
import { StatCounter } from "../../components/StatCounter/StatCounter";
import { useAnalytics } from "../../hooks/useAnalytics";
import { useCertifications } from "../../hooks/useCertifications";
import { useMagnetic } from "../../hooks/useMagnetic";
import { useTilt } from "../../hooks/useTilt";
import { useProjects } from "../../hooks/useProjects";
import styles from "./Home.module.css";

function ScrollDownIcon() {
  return (
    <svg className={styles.scrollCueIcon} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M12 4v14m0 0l-6-6m6 6l6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export default function Home() {
  const { t } = useTranslation();
  const { track } = useAnalytics();
  const { data: projects } = useProjects();
  const { data: certifications } = useCertifications();
  const magnetic = useMagnetic<HTMLAnchorElement>();
  const portraitTilt = useTilt<HTMLDivElement>();

  const featuredProjects = useMemo(() => projects?.filter((project) => project.featured) ?? [], [projects]);
  const featuredCertifications = useMemo(
    () => certifications?.filter((certification) => certification.featured) ?? [],
    [certifications],
  );
  const technologyCount = useMemo(() => {
    if (!projects) return 0;
    return new Set(projects.flatMap((project) => project.technologies)).size;
  }, [projects]);

  function scrollToWork() {
    document.getElementById("work")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  return (
    <>
      <div className={`${styles.fullBleed} ${styles.decor} ${styles.heroBand} grain`}>
        <ParallaxBlob className={styles.blobMint} speed={0.25} />
        <ParallaxBlob className={styles.blobMauve} speed={-0.18} />
        <div className={`container ${styles.hero}`}>
          <div
            className={styles.portrait}
            ref={portraitTilt.ref}
            onMouseMove={portraitTilt.handleMouseMove}
            onMouseLeave={portraitTilt.handleMouseLeave}
          >
            <span className={styles.portraitSheen} aria-hidden="true" />
            <img
              className={styles.portraitImage}
              src="/images/rodrigo-lopez.jpg"
              alt={t("home.title")}
            />
          </div>
          <span className={styles.eyebrow}>{t("home.eyebrow")}</span>
          <TextEffect as="h1" text={t("home.title")} className={styles.title} />
          <p className={styles.tagline}>{t("home.tagline")}</p>
          <p className={styles.intro}>{t("home.intro")}</p>
          <div className={styles.actions}>
            <Link
              to="/projects"
              className={styles.primary}
              ref={magnetic.ref}
              onMouseMove={magnetic.handleMouseMove}
              onMouseLeave={magnetic.handleMouseLeave}
            >
              {t("home.cta_projects")}
            </Link>
            <a href="/cv.pdf" className={styles.secondary} download onClick={() => track("cv_download")}>
              {t("home.cta_cv")}
            </a>
          </div>

          {projects && certifications && (
            <div className={styles.statsRow}>
              <StatCounter value={projects.length} label={t("home.stat_projects")} />
              <StatCounter value={technologyCount} label={t("home.stat_technologies")} suffix="+" />
              <StatCounter value={certifications.length} label={t("home.stat_certifications")} />
            </div>
          )}

          <button type="button" className={styles.scrollCue} onClick={scrollToWork}>
            <ScrollDownIcon />
            {t("home.scroll_cue")}
          </button>
        </div>
      </div>

      <div id="work" className={`${styles.fullBleed} ${styles.sectionAlt}`}>
        <div className={`container ${styles.section}`}>
          <InView className={styles.sectionHead}>
            <span className={styles.eyebrow}>{t("home.projects_eyebrow")}</span>
            <h2 className={styles.sectionTitle}>{t("home.projects_title")}</h2>
            <p className={styles.sectionIntro}>{t("home.projects_intro")}</p>
          </InView>

          {featuredProjects.length > 0 && <ProjectShowcase projects={featuredProjects} />}

          <div className={styles.viewAllRow}>
            <Link to="/projects" className={styles.viewAll}>
              {t("home.projects_cta")} →
            </Link>
          </div>
        </div>
      </div>

      <div className={`${styles.fullBleed} ${styles.decor}`}>
        <ParallaxBlob className={styles.blobTan} speed={0.2} />
        <div className={`container ${styles.section}`}>
          <InView className={styles.sectionHead}>
            <span className={styles.eyebrow}>{t("home.certifications_eyebrow")}</span>
            <h2 className={styles.sectionTitle}>{t("home.certifications_title")}</h2>
            <p className={styles.sectionIntro}>{t("home.certifications_intro")}</p>
          </InView>

          {featuredCertifications.length > 0 && (
            <AnimatedGroup className={styles.grid}>
              {featuredCertifications.map((certification) => (
                <CertificationCard key={certification.slug} certification={certification} />
              ))}
            </AnimatedGroup>
          )}

          <div className={styles.viewAllRow}>
            <Link to="/skills" className={styles.viewAll}>
              {t("home.certifications_cta")} →
            </Link>
          </div>
        </div>
      </div>

      <div className={`${styles.fullBleed} ${styles.decor} ${styles.closingBand} grain`}>
        <div className={`container ${styles.closing}`}>
          <InView>
            <h2 className={styles.closingTitle}>{t("home.closing_title")}</h2>
            <p className={styles.closingBody}>{t("home.closing_body")}</p>
            <Link to="/contact" className={styles.closingCta}>
              {t("home.closing_cta")}
            </Link>
          </InView>
        </div>
      </div>
    </>
  );
}
