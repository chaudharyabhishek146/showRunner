// Mirrors backend/agent/models.py. Keep the two in sync.

export type ServerEventType =
  | "plan"
  | "step_start"
  | "narration"
  | "screenshot"
  | "step_done"
  | "answer"
  | "status"
  | "error"
  | "complete";

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
  | "paused"
  | "done"
  | "stopped"
  | "error";
