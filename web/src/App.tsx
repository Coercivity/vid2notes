import { useEffect, useState } from "react";
import { JobView } from "./components/JobView";
import { NewJobForm } from "./components/NewJobForm";
import { RecentJobs } from "./components/RecentJobs";
import { rememberJob } from "./recent";

function readJobId(): string | null {
  return new URLSearchParams(window.location.search).get("job");
}

export function App() {
  const [jobId, setJobId] = useState<string | null>(readJobId);

  useEffect(() => {
    const onPopState = () => setJobId(readJobId());
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  const open = (id: string | null) => {
    const url = id ? `?job=${id}` : window.location.pathname;
    window.history.pushState(null, "", url);
    setJobId(id);
  };

  return (
    <div className="app">
      <header className="header">
        <button className="logo" onClick={() => open(null)}>
          vid2notes
        </button>
        <span className="tagline">sheet music from video to PDF</span>
      </header>
      <main>
        {jobId ? (
          <JobView id={jobId} onNew={() => open(null)} />
        ) : (
          <>
            <NewJobForm
              onCreated={(job) => {
                rememberJob(job);
                open(job.id);
              }}
            />
            <RecentJobs onOpen={open} />
          </>
        )}
      </main>
    </div>
  );
}
