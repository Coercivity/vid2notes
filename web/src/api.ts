export type JobStatus = "analyzing" | "awaitingCrop" | "extracting" | "completed" | "failed";
export type SheetLayout = "pages" | "scroll";

export interface Crop {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface Job {
  id: string;
  url: string;
  status: JobStatus;
  stage: string | null;
  progress: number;
  title: string | null;
  durationSeconds: number | null;
  width: number | null;
  height: number | null;
  previews: string[];
  suggestedLayout: SheetLayout | null;
  suggestedCrop: Crop | null;
  layout: SheetLayout | null;
  crop: Crop | null;
  startSeconds: number | null;
  endSeconds: number | null;
  pdfUrl: string | null;
  pageCount: number | null;
  error: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface ExtractOptions {
  crop: Crop;
  layout: SheetLayout;
  startSeconds: number | null;
  endSeconds: number | null;
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    throw new Error(await describeError(response));
  }
  return (await response.json()) as T;
}

async function describeError(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (body?.errors) {
      return Object.values(body.errors as Record<string, string[]>).flat().join("; ");
    }
    return body?.error ?? body?.title ?? `Error ${response.status}`;
  } catch {
    return `Error ${response.status}`;
  }
}

export const api = {
  createJob: (url: string) => request<Job>("/jobs", { method: "POST", body: JSON.stringify({ url }) }),
  getJob: (id: string) => request<Job>(`/jobs/${id}`),
  extract: (id: string, options: ExtractOptions) =>
    request<Job>(`/jobs/${id}/extract`, { method: "POST", body: JSON.stringify(options) }),
};
