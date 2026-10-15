"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import {
  BACKEND_STARTUP_REQUEST_TIMEOUT_MS,
  BACKEND_STARTUP_RETRY_DELAY_MS,
  shouldRetryBackendStartup,
} from "@/lib/backend-readiness.mjs";

export default function BackendStartupNotice() {
  const router = useRouter();
  const [run, setRun] = useState(0);
  const [status, setStatus] = useState<"starting" | "unavailable">("starting");

  const retry = useCallback(() => {
    setStatus("starting");
    setRun((current) => current + 1);
  }, []);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let attempt = 0;

    const checkReadiness = async () => {
      try {
        const response = await fetch("/api/health/ready", {
          cache: "no-store",
          signal: AbortSignal.timeout(BACKEND_STARTUP_REQUEST_TIMEOUT_MS),
        });
        if (response.ok) {
          if (!cancelled) router.refresh();
          return;
        }
      } catch {
        // Free services can take a while to wake. Retry for a bounded period.
      }

      attempt += 1;
      if (cancelled) return;
      if (shouldRetryBackendStartup(attempt)) {
        timer = setTimeout(checkReadiness, BACKEND_STARTUP_RETRY_DELAY_MS);
      } else {
        setStatus("unavailable");
      }
    };

    void checkReadiness();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [router, run]);

  return (
    <main className="shell">
      <section className="status-card" aria-labelledby="backend-start-title">
        <p className="eyebrow">KnowFlow portfolio demo</p>
        <h1 id="backend-start-title">
          {status === "starting" ? "Starting demo environment…" : "Demo environment is taking longer than expected"}
        </h1>
        <p className="description" role={status === "starting" ? "status" : "alert"} aria-live="polite">
          {status === "starting"
            ? "The backend may be waking up. KnowFlow will continue automatically when it is ready."
            : "The backend did not become ready within a few minutes. You can retry shortly."}
        </p>
        {status === "starting" ? (
          <div className="status-row"><span className="status-dot" aria-hidden="true" />Checking backend readiness</div>
        ) : (
          <button className="button button-primary" type="button" onClick={retry}>Retry</button>
        )}
      </section>
    </main>
  );
}
