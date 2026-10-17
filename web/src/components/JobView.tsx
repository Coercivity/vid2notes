import { useEffect } from "react";
import { rememberJob } from "../recent";
import { formatTime } from "../time";
import { isRunning, useJob } from "../useJob";
import { ExtractPanel } from "./ExtractPanel";
import { ProgressBar } from "./ProgressBar";

interface Props {
  id: string;
  onNew: () => void;
}

export function JobView({ id, onNew }: Props) {
  const { job, setJob, error } = useJob(id);

  useEffect(() => {
    if (job?.title) rememberJob(job);
  }, [job?.title]);

  if (error && !job) {
    return (
      <section className="card">
        <p className="error">{error}</p>
        <button onClick={onNew}>New job</button>
      </section>
    );
  }

  if (!job) {
    return <section className="card muted">Loading…</section>;
  }

  const running = isRunning(job);

  return (
    <>
      <section className="card">
        <div className="job-head">
          <div>
            <h1>{job.title ?? "Video"}</h1>
            <a className="muted" href={job.url} target="_blank" rel="noreferrer">
              {job.url}
            </a>
            {job.durationSeconds != null && (
              <span className="muted">
                {" "}· {formatTime(job.durationSeconds)} · {job.width}×{job.height}
              </span>
            )}
          </div>
          <button onClick={onNew}>New job</button>
        </div>

        {running && (
          <ProgressBar
            title={job.status === "analyzing" ? "Analyzing video" : "Building sheet music"}
            stage={job.stage}
            progress={job.progress}
          />
        )}

        {job.status === "failed" && (
          <div className="notice notice-error">
            <strong>Failed to {job.stage === "extract" ? "build the PDF" : "process the video"}.</strong>
            <span>{job.error}</span>
          </div>
        )}

        {job.status === "completed" && job.pdfUrl && (
          <div className="notice notice-success">
            <span>
              PDF is ready: {job.pageCount} {job.pageCount === 1 ? "page" : "pages"}.
            </span>
            <a className="button primary" href={job.pdfUrl} download>
              Download PDF
            </a>
          </div>
        )}

        {error && <p className="error">{error}</p>}
      </section>

      {!running && job.previews.length > 0 && <ExtractPanel job={job} onStarted={setJob} />}
    </>
  );
}
