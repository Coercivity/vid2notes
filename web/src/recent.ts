import { Job } from "./api";

const KEY = "vid2notes.recent";
const LIMIT = 10;

export interface RecentJob {
  id: string;
  url: string;
  title: string | null;
  createdAt: string;
}

export function loadRecentJobs(): RecentJob[] {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? "[]") as RecentJob[];
  } catch {
    return [];
  }
}

export function rememberJob(job: Job): void {
  const entry: RecentJob = { id: job.id, url: job.url, title: job.title, createdAt: job.createdAt };
  const rest = loadRecentJobs().filter((j) => j.id !== job.id);
  try {
    localStorage.setItem(KEY, JSON.stringify([entry, ...rest].slice(0, LIMIT)));
  } catch {
    return;
  }
}
