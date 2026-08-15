"use client";

import type { RunStatus } from "@/lib/types";

interface Props {
  screenshot: string | null;
  caption: string;
  currentUrl: string;
  status: RunStatus;
}

/**
 * The right half: what the agent is actually looking at.
 *
 * Frames are base64 PNGs pushed over the same WebSocket as the narration, so
 * the picture and the words can't drift apart.
 */
export default function BrowserPanel({
  screenshot,
  caption,
  currentUrl,
  status,
}: Props) {
  return (
    <section className="browser">
      <header className="browser__chrome">
        <span className="browser__lights">
          <i /> <i /> <i />
        </span>
        <span className="browser__url" title={currentUrl}>
          {currentUrl || "about:blank"}
        </span>
        <span className={`browser__badge browser__badge--${status}`}>
          {status === "paused" ? "PAUSED" : status.toUpperCase()}
        </span>
      </header>

      <div className="browser__viewport">
        {screenshot ? (
          <img
            className="browser__frame"
            src={`data:image/png;base64,${screenshot}`}
            alt={caption || "Live browser view"}
          />
        ) : (
          <div className="browser__idle">
            <div className="browser__idle-mark">▶</div>
            <p>The live browser appears here once the walkthrough starts.</p>
          </div>
        )}

        {status === "paused" && screenshot && (
          <div className="browser__freeze">
            <span>Holding position while I answer</span>
          </div>
        )}
      </div>

      {caption && <footer className="browser__caption">{caption}</footer>}
    </section>
  );
}
