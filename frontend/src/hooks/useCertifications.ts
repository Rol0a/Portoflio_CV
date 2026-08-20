import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { getCertifications } from "../services/api";
import type { Certification } from "../types";

interface AsyncState<T> {
  data: T | null;
  loading: boolean;
  error: boolean;
}

export function useCertifications(featured?: boolean): AsyncState<Certification[]> {
  const { i18n } = useTranslation();
  const [state, setState] = useState<AsyncState<Certification[]>>({ data: null, loading: true, error: false });

  useEffect(() => {
    let cancelled = false;
    setState({ data: null, loading: true, error: false });

    getCertifications(i18n.language, featured)
      .then((certifications) => {
        if (!cancelled) setState({ data: certifications, loading: false, error: false });
      })
      .catch(() => {
        if (!cancelled) setState({ data: null, loading: false, error: true });
      });

    return () => {
      cancelled = true;
    };
  }, [i18n.language, featured]);

  return state;
}
