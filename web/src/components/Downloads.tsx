import { Job } from "../api";

interface Props {
  job: Job;
}

function plural(count: number, word: string): string {
  return `${count} ${word}${count === 1 ? "" : "s"}`;
}

export function Downloads({ job }: Props) {
  const facts = [
    job.pageCount != null && plural(job.pageCount, "page"),
    job.noteCount != null && plural(job.noteCount, "note"),
    job.tempo != null && `${Math.round(job.tempo)} BPM`,
    job.timeSignature,
    job.keyName,
  ].filter(Boolean);

  const files = [
    { url: job.pdfUrl, label: "Download PDF", primary: true },
    { url: job.midiUrl, label: "MIDI", primary: false },
    { url: job.musicXmlUrl, label: "MusicXML", primary: false },
  ].filter((file) => file.url);

  if (files.length === 0) {
    return null;
  }

  return (
    <div className="notice notice-success">
      <span>
        Sheet music is ready{facts.length > 0 && <span className="muted"> · {facts.join(" · ")}</span>}
      </span>
      <div className="downloads">
        {files.map((file) => (
          <a key={file.label} className={file.primary ? "button primary" : "button"} href={file.url!} download>
            {file.label}
          </a>
        ))}
      </div>
    </div>
  );
}
