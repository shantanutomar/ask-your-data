import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";
import type { DatasetSummary } from "../types/api";

export function useDataset() {
  const [dataset, setDataset] = useState<DatasetSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .getDataset()
      .then((r) => {
        if (!cancelled) setDataset(r.dataset);
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const loadSample = useCallback(async () => {
    const r = await api.loadSample();
    setDataset(r.dataset);
    return r.dataset;
  }, []);

  const reset = useCallback(async () => {
    await api.resetDataset();
    setDataset(null);
  }, []);

  return { dataset, setDataset, loading, error, loadSample, reset };
}
