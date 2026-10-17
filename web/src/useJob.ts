import { useCallback, useEffect, useState } from "react";
import { api, Job } from "./api";

const POLL_INTERVAL_MS = 1500;

export function isRunning(job: Job | null): boolean {
  return job?.status === "analyzing" || job?.status === "extracting";
}

export function useJob(id: string) {
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setJob(await api.getJob(id));
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [id]);

  useEffect(() => {
    setJob(null);
    refresh();
  }, [refresh]);

  useEffect(() => {
    if (!isRunning(job)) {
      return;
    }
    const timer = window.setTimeout(refresh, POLL_INTERVAL_MS);
    return () => window.clearTimeout(timer);
  }, [job, refresh]);

  return { job, setJob, error };
}
