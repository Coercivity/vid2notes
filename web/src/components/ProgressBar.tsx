const STAGES: Record<string, string> = {
  queued: "Queued",
  downloading: "Downloading video",
  analyzing: "Analyzing frames",
  uploading: "Saving results",
  extracting: "Extracting notes",
  rendering: "Building PDF",
};

interface Props {
  title: string;
  stage: string | null;
  progress: number;
}

export function ProgressBar({ title, stage, progress }: Props) {
  const label = stage ? STAGES[stage] ?? stage : "Processing";
  return (
    <div className="progress">
      <div className="progress-head">
        <strong>{title}</strong>
        <span className="muted">
          {label} · {progress}%
        </span>
      </div>
      <div className="progress-track" role="progressbar" aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100}>
        <div className="progress-fill" style={{ width: `${progress}%` }} />
      </div>
    </div>
  );
}
