import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { getProject, getProjects } from "../services/api";
import type { ProjectDetail, ProjectListItem } from "../types";

interface AsyncState<T> {
  data: T | null;
  loading: boolean;
  error: boolean;
}

export function useProjects(category?: string, featured?: boolean): AsyncState<ProjectListItem[]> {
  const { i18n } = useTranslation();
  const [state, setState] = useState<AsyncState<ProjectListItem[]>>({ data: null, loading: true, error: false });

  useEffect(() => {
    let cancelled = false;
    setState({ data: null, loading: true, error: false });

    getProjects(i18n.language, category, featured)
      .then((projects) => {
        if (!cancelled) setState({ data: projects, loading: false, error: false });
      })
      .catch(() => {
        if (!cancelled) setState({ data: null, loading: false, error: true });
      });

    return () => {
      cancelled = true;
    };
  }, [i18n.language, category, featured]);

  return state;
}

export function useProject(slug: string | undefined): AsyncState<ProjectDetail | null> {
  const { i18n } = useTranslation();
  const [state, setState] = useState<AsyncState<ProjectDetail | null>>({ data: null, loading: true, error: false });

  useEffect(() => {
    if (!slug) {
      setState({ data: null, loading: false, error: false });
      return;
    }

    let cancelled = false;
    setState({ data: null, loading: true, error: false });

    getProject(slug, i18n.language)
      .then((project) => {
        if (!cancelled) setState({ data: project, loading: false, error: false });
      })
      .catch(() => {
        if (!cancelled) setState({ data: null, loading: false, error: true });
      });

    return () => {
      cancelled = true;
    };
  }, [slug, i18n.language]);

  return state;
}
