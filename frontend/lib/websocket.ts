"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type {
  AgentPrompt,
  ChatMessage,
  DemoConfig,
  DemoRequest,
  Plan,
  RunStatus,
  ServerEvent,
  StepStatus,
  TabInfo,
} from "./types";
import { speak, cancelSpeech } from "./voice";
import { fetchDemoConfig, fetchTabs } from "./api";

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
  // Live frames arrive as JPEG, post-action stills as PNG.
  screenshotMime: "image/png" | "image/jpeg";
  caption: string;
  currentUrl: string;
  activeStep: number | null;
  stepStatus: Record<number, StepStatus>;
  thinking: boolean;
  voiceOn: boolean;
  // The tab the agent settled on, echoed back once it has picked one.
  demoTab: TabInfo | null;
  // Hosts the demo is allowed to visit, derived from that tab.
  scope: string[];
  // When the agent has stopped to take questions, and until when (epoch ms).
  questionsUntil: number | null;
  // A question the agent is waiting on *us* to answer, e.g. signing in.
  prompt: AgentPrompt | null;
  // What this build demos. Null until the config has loaded.
  demo: DemoConfig | null;
  // The presenter's open tabs, and why we might not have any.
  tabs: TabInfo[];
  chromeAttached: boolean;
  chromeHint: string;
  chromeCommand: string;
  tabsLoading: boolean;
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
    screenshotMime: "image/png",
    caption: "",
    currentUrl: "",
    activeStep: null,
    stepStatus: {},
    thinking: false,
    voiceOn: true,
    demoTab: null,
    scope: [],
    questionsUntil: null,
    prompt: null,
    demo: null,
    tabs: [],
    chromeAttached: false,
    chromeHint: "",
    chromeCommand: "",
    tabsLoading: true,
  });

  const voiceOnRef = useRef(true);
  voiceOnRef.current = state.voiceOn;

  const promptRef = useRef<AgentPrompt | null>(null);
  promptRef.current = state.prompt;

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

  /** Ask the backend which tabs are open. Safe to call repeatedly. */
  const refreshTabs = useCallback(async () => {
    setState((s) => ({ ...s, tabsLoading: true }));
    try {
      const result = await fetchTabs();
      setState((s) => ({
        ...s,
        tabs: result.tabs,
        chromeAttached: result.attached,
        chromeHint: result.hint,
        // The command is only worth showing when the presenter has to run it
        // themselves — otherwise starting the demo opens Chrome for them.
        chromeCommand: result.auto_launch ? "" : result.command ?? "",
        tabsLoading: false,
      }));
    } catch (err) {
      setState((s) => ({
        ...s,
        tabsLoading: false,
        chromeAttached: false,
        chromeHint:
          err instanceof Error
            ? `Couldn't reach the agent: ${err.message}`
            : "Couldn't reach the agent.",
      }));
    }
  }, []);

  // Tabs are fetched once on load so the picker is populated before the
  // presenter has done anything — this is the first thing they look at.
  useEffect(() => {
    void refreshTabs();
    fetchDemoConfig()
      .then((demo) => setState((s) => ({ ...s, demo })))
      .catch(() => {});
  }, [refreshTabs]);

  const send = useCallback((payload: Record<string, unknown>) => {
    const ws = socketRef.current;
    if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify(payload));
  }, []);

  const start = useCallback(
    (request: DemoRequest) => {
      setState((s) => ({ ...s, status: "planning", messages: [] }));
      send({ type: "start", ...request });
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

  // Once a session exists the socket has the fresher listing, so prefer it and
  // fall back to REST only when the socket isn't up.
  const requestTabs = useCallback(() => {
    if (socketRef.current?.readyState === WebSocket.OPEN) {
      setState((s) => ({ ...s, tabsLoading: true }));
      send({ type: "list_tabs" });
    } else {
      void refreshTabs();
    }
  }, [send, refreshTabs]);

  /** Answer whatever the agent is currently waiting on. */
  const reply = useCallback(
    (option: string) => {
      const pending = promptRef.current;
      if (!pending) return;
      // Read from a ref, not from inside a setState updater: StrictMode runs
      // updaters twice, and sending the reply twice would answer the *next*
      // prompt with this click.
      send({ type: "reply", prompt_id: pending.id, text: option });
      setState((s) => ({ ...s, prompt: null }));
    },
    [send],
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

  return {
    ...state,
    start,
    ask,
    pause,
    resume,
    skip,
    stop,
    toggleVoice,
    requestTabs,
    reply,
  };
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

    // Continuous live stream — image only. Touching the caption here would
    // make it flicker several times a second.
    case "frame":
      setState((s) => ({
        ...s,
        screenshot: event.image,
        screenshotMime: "image/jpeg",
      }));
      break;

    // Post-action still: full-quality PNG plus the trace line and URL.
    case "screenshot":
      setState((s) => ({
        ...s,
        screenshot: event.image,
        screenshotMime: "image/png",
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

    // The agent is waiting on the presenter — surface it and speak it, since
    // the presenter may well be looking at the browser, not the app.
    case "prompt": {
      const payload = event.payload ?? {};
      setState((s) => ({
        ...s,
        prompt: {
          id: (payload.id as string) ?? "prompt",
          question: event.text,
          options: (payload.options as string[]) ?? ["OK"],
        },
      }));
      push({ role: "agent", text: event.text });
      if (voiceOn.current) speak(event.text);
      break;
    }

    // The live session's view of the tabs — more current than the REST call,
    // and the only listing available once a demo has taken the browser over.
    case "tabs":
      setState((s) => ({
        ...s,
        tabs: (event.payload?.tabs as TabInfo[] | undefined) ?? s.tabs,
        chromeAttached: true,
        chromeHint: "",
        tabsLoading: false,
      }));
      break;

    case "status": {
      const t = event.text.toLowerCase();
      const tab = event.payload?.tab as TabInfo | undefined;
      const asking = t === "taking questions";
      const window = (event.payload?.seconds as number | undefined) ?? 0;
      setState((s) => ({
        ...s,
        statusText: event.text,
        // Any other status ends the window — the demo has moved on.
        questionsUntil: asking ? Date.now() + window * 1000 : null,
        demoTab: tab ?? s.demoTab,
        scope: (event.payload?.scope as string[] | undefined) ?? s.scope,
        currentUrl: tab?.url ?? s.currentUrl,
        status:
          t === "pausing"
            ? "pausing"
            : t === "paused"
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
