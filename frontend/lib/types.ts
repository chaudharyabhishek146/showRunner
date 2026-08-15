// Mirrors backend/agent/models.py. Keep the two in sync.

export type ServerEventType =
  | "plan"
  | "step_start"
  | "narration"
  | "screenshot"
  | "frame"
  | "step_done"
  | "answer"
  | "status"
  | "error"
  | "complete"
  | "tabs"
  | "prompt";

export interface ServerEvent {
  type: ServerEventType;
  step_id: number | null;
  text: string;
  image: string | null;
  payload: Record<string, unknown> | null;
}

export interface Step {
  id: number;
  title: string;
  goal: string;
  doc_reference: string;
  narration: string;
}

export interface Plan {
  workflow_name: string;
  summary: string;
  steps: Step[];
}

/** One open tab in the presenter's Chrome — a candidate demo surface. */
export interface TabInfo {
  index: number;
  title: string;
  url: string;
  host: string;
  active: boolean;
}

export interface DocumentSummary {
  id: string;
  name: string;
  chars: number;
  uploaded_at: string;
  preview: string;
}

/** What the presenter supplies to define a demo. All of it is per-run. */
export interface DemoRequest {
  doc_id: string;
  focus: string;
  tab: string;
  /** Inline text, for a document that was pasted rather than uploaded. */
  doc?: string;
  /** Replay a remembered walkthrough instead of planning a fresh one. */
  workflow?: string;
}

/** A question the agent is waiting on the presenter to answer, with buttons. */
export interface AgentPrompt {
  id: string;
  question: string;
  options: string[];
}

/** What this build is configured to demo, and whether that's fixed. */
export interface DemoConfig {
  locked: boolean;
  title: string;
  focus: string;
  tab: string;
  sample: string;
}

export type StepStatus = "pending" | "active" | "done";

export interface ChatMessage {
  id: string;
  role: "agent" | "client" | "system";
  text: string;
  stepId?: number | null;
  at: number;
}

export type RunStatus =
  | "connecting"
  | "idle"
  | "planning"
  | "running"
  | "pausing"
  | "paused"
  | "done"
  | "stopped"
  | "error";
