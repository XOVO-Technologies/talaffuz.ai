import { useEffect, useRef, useState } from "react";
import { formatDuration } from "../format";
import type { JobEvent } from "../types";
import { ProgressBar } from "./ProgressBar";

const TITLES: Record<string, string> = { process: "Cleaning and transcribing", romanize: "Writing Roman Urdu" };

export function JobProgress({ running, event }: { running: string; event: JobEvent | null }) {
  const base = useRef<{ t: number; done: number } | null>(null);
  const [etaSeconds, setEta] = useState<number | null>(null);

  useEffect(() => {
    base.current = null;
    setEta(null);
  }, [running]);

  // Estimate the time left from how fast clips have been finishing since this page started watching.
  useEffect(() => {
    if (!event || event.done === undefined || event.total === undefined) return;
    const now = Date.now();
    if (!base.current || event.done < base.current.done) base.current = { t: now, done: event.done };
    const gained = event.done - base.current.done;
    if (gained >= 2) setEta(((event.total - event.done) * ((now - base.current.t) / gained)) / 1000);
  }, [event]);

  const progress = event?.progress ?? null;
  const title = TITLES[running] ?? "Working";
  return (
    <div className="job" role="status" aria-live="polite">
      <div className="job-top">
        <strong>{title}…</strong>
        <span className="job-meta">
          {progress !== null && `${Math.round(progress * 100)}%`}
          {etaSeconds !== null && ` · about ${formatDuration(etaSeconds)} left`}
        </span>
      </div>
      <ProgressBar value={progress} label={title} thick />
      <span className="job-meta">{event?.message ?? "Starting…"}</span>
    </div>
  );
}
