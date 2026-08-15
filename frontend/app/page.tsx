"use client";

import BrowserPanel from "@/components/BrowserPanel";
import ChatPanel from "@/components/ChatPanel";
import StepProgress from "@/components/StepProgress";
import { useWalkthrough } from "@/lib/websocket";

export default function Home() {
  const w = useWalkthrough();

  const notStarted = w.status === "idle" || w.status === "connecting";
  const running = w.status === "running" || w.status === "paused";

  return (
    <main className="shell">
      <header className="topbar">
        <div className="topbar__brand">
          <span className="topbar__mark">◉</span>
          <div>
            <h1>Platform Walkthrough Agent</h1>
            <p>{w.statusText}</p>
          </div>
        </div>

        <div className="topbar__controls">
          <span className={`dot dot--${w.connected ? "on" : "off"}`} />

          <button
            className="btn btn--primary"
            onClick={() => w.start()}
            disabled={!w.connected || running || w.status === "planning"}
          >
            {w.status === "planning" ? "Planning…" : "Start walkthrough"}
          </button>

          {w.status === "paused" ? (
            <button className="btn" onClick={w.resume}>
              Resume
            </button>
          ) : (
            <button className="btn" onClick={w.pause} disabled={!running}>
              Pause
            </button>
          )}

          <button className="btn" onClick={w.skip} disabled={!running}>
            Skip step
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
          caption={w.caption}
          currentUrl={w.currentUrl}
          status={w.status}
        />
      </div>
    </main>
  );
}
