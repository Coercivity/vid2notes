import { FormEvent, useState } from "react";
import { api, Job } from "../api";

interface Props {
  onCreated: (job: Job) => void;
}

export function NewJobForm({ onCreated }: Props) {
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onCreated(await api.createJob(url.trim()));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="card">
      <h1>Link to a sheet music video</h1>
      <p className="muted">YouTube or any link supported by yt-dlp.</p>
      <form className="url-form" onSubmit={submit}>
        <input
          type="url"
          required
          placeholder="https://www.youtube.com/watch?v=..."
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          disabled={busy}
        />
        <button className="primary" type="submit" disabled={busy || !url.trim()}>
          {busy ? "Submitting…" : "Process"}
        </button>
      </form>
      {error && <p className="error">{error}</p>}
    </section>
  );
}
