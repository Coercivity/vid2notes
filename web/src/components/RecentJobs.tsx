import { loadRecentJobs } from "../recent";

interface Props {
  onOpen: (id: string) => void;
}

export function RecentJobs({ onOpen }: Props) {
  const jobs = loadRecentJobs();
  if (jobs.length === 0) {
    return null;
  }

  return (
    <section className="card">
      <h2>Recent</h2>
      <ul className="recent">
        {jobs.map((job) => (
          <li key={job.id}>
            <button className="link" onClick={() => onOpen(job.id)}>
              {job.title ?? job.url}
            </button>
            <span className="muted">{new Date(job.createdAt).toLocaleString()}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
