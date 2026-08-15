"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type {
  ChatMessage,
  Plan,
  RunStatus,
  ServerEvent,
  StepStatus,
} from "./types";
import { speak, cancelSpeech } from "./voice";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000/ws";

let messageSeq = 0;
const nextId = () => `m${++messageSeq}`;

export interface WalkthroughState {
  connected: boolean;
  status: RunStatus;
  statusText: string;
  plan: Plan | null;
  messages: ChatMessage[];
  screenshot: string | null;
  caption: string;
  currentUrl: string;
  activeStep: number | null;
  stepStatus: Record<number, StepStatus>;
  thinking: boolean;
  voiceOn: boolean;
}

/**
 * Owns the WebSocket and folds the server's event stream into render state.
 *
 * The socket is opened once and kept for the life of the page — reconnecting
 * mid-demo would orphan the browser session on the backend.
 */
export function useWalkthrough() {
  const socketRef = useRef<WebSocket | null>(null);
  const [state, setState] = useState<WalkthroughState>({
    connected: false,
    status: "connecting",
    statusText: "Connecting to the agent…",
    plan: null,
    messages: [],
    screenshot: null,
    caption: "",
    currentUrl: "",
    activeStep: null,
    stepStatus: {},
    thinking: false,
    voiceOn: true,
  });

  const voiceOnRef = useRef(true);
  voiceOnRef.current = state.voiceOn;

  const push = useCallback((msg: Omit<ChatMessage, "id" | "at">) => {
    setState((s) => ({
      ...s,
      messages: [...s.messages, { ...msg, id: nextId(), at: Date.now() }],
    }));
  }, []);

  useEffect(() => {
    const ws = new WebSocket(WS_URL);
    socketRef.current = ws;

    ws.onopen = () =>
      setState((s) => ({ ...s, connected: true, status: "idle" }));

    ws.onclose = () =>
      setState((s) => ({
        ...s,
        connected: false,
        statusText: "Disconnected from the agent.",
      }));

    ws.onerror = () =>
      setState((s) => ({
        ...s,
        status: "error",
        statusText: `Could not reach the agent at ${WS_URL}.`,
      }));

    ws.onmessage = (raw) => {
      const event = JSON.parse(raw.data) as ServerEvent;
      handleEvent(event, setState, push, voiceOnRef);
    };

    return () => {
      cancelSpeech();
      ws.close();
    };
  }, [push]);

  const send = useCallback((payload: Record<string, unknown>) => {
    const ws = socketRef.current;
    if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify(payload));
  }, []);

  const start = useCallback(
    (workflow = "") => {
      setState((s) => ({ ...s, status: "planning", messages: [] }));
      send({ type: "start", workflow });
    },
    [send],
  );

  const ask = useCallback(
    (text: string) => {
      if (!text.trim()) return;
      cancelSpeech(); // stop narrating the moment someone interrupts
      push({ role: "client", text });
      setState((s) => ({ ...s, thinking: true }));
      send({ type: "question", text });
    },
    [push, send],
  );

  const pause = useCallback(() => send({ type: "pause" }), [send]);
  const resume = useCallback(() => send({ type: "resume" }), [send]);
  const skip = useCallback(() => send({ type: "skip" }), [send]);
  const stop = useCallback(() => {
    cancelSpeech();
    send({ type: "stop" });
  }, [send]);

  const toggleVoice = useCallback(() => {
    setState((s) => {
      if (s.voiceOn) cancelSpeech();
      return { ...s, voiceOn: !s.voiceOn };
    });
  }, []);

  return { ...state, start, ask, pause, resume, skip, stop, toggleVoice };
}

type Setter = React.Dispatch<React.SetStateAction<WalkthroughState>>;

function handleEvent(
  event: ServerEvent,
  setState: Setter,
  push: (m: Omit<ChatMessage, "id" | "at">) => void,
  voiceOn: React.MutableRefObject<boolean>,
) {
  switch (event.type) {
    case "plan": {
      const plan = event.payload as unknown as Plan;
      setState((s) => ({
        ...s,
        plan,
        status: "running",
        stepStatus: Object.fromEntries(
          plan.steps.map((step) => [step.id, "pending" as StepStatus]),
        ),
      }));
      push({ role: "system", text: `Plan ready — ${plan.summary}` });
      break;
    }

    case "step_start":
      setState((s) => ({
        ...s,
        activeStep: event.step_id,
        status: "running",
        stepStatus: { ...s.stepStatus, [event.step_id!]: "active" },
      }));
      push({ role: "system", text: `Step ${event.step_id}: ${event.text}` });
      break;

    case "narration":
      push({ role: "agent", text: event.text, stepId: event.step_id });
      if (voiceOn.current) speak(event.text);
      break;

    case "screenshot":
      setState((s) => ({
        ...s,
        screenshot: event.image,
        caption: event.text,
        currentUrl: (event.payload?.url as string) ?? s.currentUrl,
      }));
      break;

    case "step_done":
      setState((s) => ({
        ...s,
        stepStatus: { ...s.stepStatus, [event.step_id!]: "done" },
      }));
      break;

    case "answer":
      setState((s) => ({ ...s, thinking: false }));
      push({ role: "agent", text: event.text, stepId: event.step_id });
      if (voiceOn.current) speak(event.text);
      break;

    case "status": {
      const t = event.text.toLowerCase();
      setState((s) => ({
        ...s,
        statusText: event.text,
        status:
          t === "paused"
            ? "paused"
            : t === "running"
              ? "running"
              : t === "stopped"
                ? "stopped"
                : s.status,
      }));
      break;
    }

    case "complete":
      cancelSpeech();
      setState((s) => ({ ...s, status: "done", activeStep: null }));
      push({ role: "system", text: "Walkthrough complete." });
      break;

    case "error":
      setState((s) => ({ ...s, status: "error", thinking: false }));
      push({ role: "system", text: event.text });
      break;
  }
}
