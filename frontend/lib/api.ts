// REST calls for everything that happens *before* a walkthrough starts.
// The WebSocket carries the demo itself; setup is plain HTTP so the tab picker
// and the document upload work on page load, with no session to establish.

import type { DemoConfig, DocumentSummary, TabInfo } from "./types";

const API =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function json<T>(response: Response): Promise<T> {
  if (!response.ok) {
    // FastAPI puts the useful part in `detail`; surfacing the raw status here
    // would hide "couldn't read any text out of that PDF".
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? `${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

export interface TabsResponse {
  attached: boolean;
  tabs: TabInfo[];
  hint: string;
  /** True when starting a demo can open Chrome itself. */
  auto_launch?: boolean;
  command?: string;
}

/** What this build demos — and whether the presenter may change it. */
export async function fetchDemoConfig(): Promise<DemoConfig> {
  return json<DemoConfig>(await fetch(`${API}/demo`));
}

export async function fetchTabs(): Promise<TabsResponse> {
  return json<TabsResponse>(await fetch(`${API}/tabs`));
}

export async function uploadDocument(file: File): Promise<DocumentSummary> {
  const form = new FormData();
  form.append("file", file);
  return json<DocumentSummary>(
    await fetch(`${API}/document`, { method: "POST", body: form }),
  );
}

export interface SampleDoc {
  name: string;
  title: string;
}

/** The bundled example docs — a one-click way to try the agent out. */
export async function fetchSamples(): Promise<SampleDoc[]> {
  const body = await json<{ samples: SampleDoc[] }>(
    await fetch(`${API}/samples`),
  );
  return body.samples;
}

export async function fetchSampleDoc(name = ""): Promise<string> {
  const body = await json<{ content: string }>(
    await fetch(`${API}/sample-doc?name=${encodeURIComponent(name)}`),
  );
  return body.content;
}

export async function pasteDocument(
  text: string,
  name = "pasted document",
): Promise<DocumentSummary> {
  return json<DocumentSummary>(
    await fetch(`${API}/document/text`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, text }),
    }),
  );
}
