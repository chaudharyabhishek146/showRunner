"use client";

import { useEffect, useState } from "react";
import BrowserPanel from "@/components/BrowserPanel";
import ChatPanel from "@/components/ChatPanel";
import SetupPanel from "@/components/SetupPanel";
import StepProgress from "@/components/StepProgress";
import { useWalkthrough } from "@/lib/websocket";

export default function Home() {
  const w = useWalkthrough();
  const [setupOpen, setSetupOpen] = useState(true);

  const notStarted = w.status === "idle" || w.status === "connecting";
  const running =
    w.status === "running" || w.status === "paused" || w.status === "pausing";
  const busy = running || w.status === "planning";

  // Setup takes the whole width; once there's a plan the demo needs that room,
  // so fold it away. The presenter can reopen it to run something else.
  useEffect(() => {
    if (w.plan) setSetupOpen(false);
  }, [w.plan]);

  // Ticks the "taking questions" countdown. Local, because a per-second event
  // from the server would be a lot of traffic to say nothing new.
  const [secondsLeft, setSecondsLeft] = useState<number | null>(null);
  useEffect(() => {
    if (!w.questionsUntil) {
      setSecondsLeft(null);
      return;
    }
    const tick = () =>
      setSecondsLeft(Math.max(0, Math.round((w.questionsUntil! - Date.now()) / 1000)));
    tick();
    const id = setInterval(tick, 250);
    return () => clearInterval(id);
  }, [w.questionsUntil]);

  // Keep backend awake (useful for free tier deployments) by pinging every 2 minutes
  useEffect(() => {
    const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    const intervalId = setInterval(() => {
      fetch(`${API}/ping`).catch(() => {});
    }, 2 * 60 * 1000);
    return () => clearInterval(intervalId);
  }, []);

  return (
    <main className="shell">
      <header className="topbar">
        <div className="topbar__brand">
          <span className="topbar__mark">◉</span>
          <div>
            <h1>Platform Walkthrough Agent</h1>
            <p>{w.statusText}</p>
            {w.demoTab && (
              <p className="topbar__scope">
                Demoing <strong>{w.demoTab.host}</strong>
                {w.scope.length > 0 && ` · scope: ${w.scope.join(", ")}`}
              </p>
            )}
          </div>
        </div>

        <div className="topbar__controls">
          {secondsLeft !== null && (
            <span className="asking">
              Taking questions · {secondsLeft}s
            </span>
          )}

          <span className={`dot dot--${w.connected ? "on" : "off"}`} />

          <button
            className={`btn btn--toggle${setupOpen ? " is-on" : ""}`}
            onClick={() => setSetupOpen((open) => !open)}
          >
            {setupOpen ? "Hide setup" : "New demo"}
          </button>

          {w.status === "paused" ? (
            <button className="btn" onClick={w.resume}>
              Resume
            </button>
          ) : (
            <button
              className="btn"
              onClick={w.pause}
              disabled={!running || w.status === "pausing"}
            >
              {w.status === "pausing" ? "Pausing…" : "Pause"}
            </button>
          )}

          <button className="btn" onClick={w.skip} disabled={!running}>
            {/* Same control, honest about what it does right now: during a
                question window there is no step to skip, only silence. */}
            {secondsLeft === null ? "Skip step" : "Carry on"}
          </button>

          <button className="btn" onClick={w.stop} disabled={notStarted}>
            Stop
          </button>

          <button
            className={`btn btn--toggle${w.voiceOn ? " is-on" : ""}`}
            onClick={w.toggleVoice}
            title="Read narration aloud"
          >
            {w.voiceOn ? "🔊 Voice on" : "🔇 Voice off"}
          </button>
        </div>
      </header>

      {w.prompt && (
        <section className="agentprompt">
          <p className="agentprompt__q">{w.prompt.question}</p>
          <div className="agentprompt__opts">
            {w.prompt.options.map((option, i) => (
              <button
                key={option}
                className={`btn${i === 0 ? " btn--primary" : ""}`}
                onClick={() => w.reply(option)}
              >
                {option}
              </button>
            ))}
          </div>
        </section>
      )}

      {setupOpen && (
        <SetupPanel
          demo={w.demo}
          tabs={w.tabs}
          chromeAttached={w.chromeAttached}
          chromeHint={w.chromeHint}
          chromeCommand={w.chromeCommand}
          tabsLoading={w.tabsLoading}
          busy={busy}
          connected={w.connected}
          onRefreshTabs={w.requestTabs}
          onStart={w.start}
        />
      )}

      <StepProgress
        plan={w.plan}
        stepStatus={w.stepStatus}
        activeStep={w.activeStep}
      />

      <div className="split">
        <ChatPanel
          messages={w.messages}
          thinking={w.thinking}
          disabled={!w.connected}
          onAsk={w.ask}
        />
        <BrowserPanel
          screenshot={w.screenshot}
          screenshotMime={w.screenshotMime}
          caption={w.caption}
          currentUrl={w.currentUrl}
          status={w.status}
        />
      </div>
    </main>
  );
}
