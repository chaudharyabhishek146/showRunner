"use client";

import { useEffect, useState } from "react";
import {
  fetchSampleDoc,
  fetchSamples,
  pasteDocument,
  uploadDocument,
  type SampleDoc,
} from "@/lib/api";
import type {
  DemoConfig,
  DemoRequest,
  DocumentSummary,
  TabInfo,
} from "@/lib/types";

interface Props {
  demo: DemoConfig | null;
  tabs: TabInfo[];
  chromeAttached: boolean;
  chromeHint: string;
  chromeCommand: string;
  tabsLoading: boolean;
  busy: boolean;
  /** Separate from `busy`: "no socket" and "a demo is running" look identical
   *  to a disabled button, and telling the presenter "Running…" when nothing
   *  is running sends them looking for a demo that never started. */
  connected: boolean;
  onRefreshTabs: () => void;
  onStart: (request: DemoRequest) => void;
}

/**
 * Everything the presenter supplies before a demo: the product document, the
 * flow they want shown, and which of their open tabs to show it in.
 *
 * Nothing here is configured ahead of time — that's the point. The same build
 * demos GitHub, YouTube, or an internal tool, depending only on what's typed
 * in this panel.
 */
export default function SetupPanel({
  demo,
  tabs,
  chromeAttached,
  chromeHint,
  chromeCommand,
  tabsLoading,
  busy,
  connected,
  onRefreshTabs,
  onStart,
}: Props) {
  const [doc, setDoc] = useState<DocumentSummary | null>(null);
  const [pasted, setPasted] = useState("");
  const [focus, setFocus] = useState("");
  const [tab, setTab] = useState("");
  const [note, setNote] = useState("");
  const [working, setWorking] = useState(false);
  const [copied, setCopied] = useState(false);
  const [samples, setSamples] = useState<SampleDoc[]>([]);

  useEffect(() => {
    fetchSamples().then(setSamples).catch(() => setSamples([]));
  }, []);

  /** Wraps the async setup calls so one failure can't leave the panel stuck. */
  async function run(label: string, fn: () => Promise<void>) {
    setWorking(true);
    setNote(label);
    try {
      await fn();
    } catch (err) {
      setNote(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setWorking(false);
    }
  }

  const onFile = (file: File | undefined) => {
    if (!file) return;
    void run(`Reading ${file.name}…`, async () => {
      const summary = await uploadDocument(file);
      setDoc(summary);
      setPasted("");
      setNote(`${summary.name} — ${summary.chars.toLocaleString()} characters`);
    });
  };

  const usePasted = () =>
    run("Saving the document…", async () => {
      const summary = await pasteDocument(pasted);
      setDoc(summary);
      setNote(`${summary.name} — ${summary.chars.toLocaleString()} characters`);
    });

  const useSample = (sample: SampleDoc) =>
    run(`Loading ${sample.title}…`, async () => {
      const content = await fetchSampleDoc(sample.name);
      setPasted(content);
      const summary = await pasteDocument(content, sample.title);
      setDoc(summary);
      setNote(`${sample.title} — ${summary.chars.toLocaleString()} characters`);
    });

  const copyCommand = async () => {
    await navigator.clipboard.writeText(chromeCommand);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // The document is the only hard requirement: without it there's nothing to
  // plan from. An empty tab hint just means "use whatever is in front of me".
  const ready = doc !== null && !busy && !working && connected;

  // Locked build: one demo, no inputs, identical every time. The presenter
  // gets a Start button and nothing they can accidentally change on stage.
  if (demo?.locked) {
    return (
      <section className="setup setup--locked">
        <div>
          <span className="setup__label">This demo</span>
          <h2 className="setup__locked-title">{demo.title}</h2>
          <p className="setup__hint">
            Showing {demo.focus} in your <strong>{demo.tab}</strong> tab. I'll
            open Chrome if it isn't ready, and ask whether you want to sign in
            before I plan anything.
          </p>
        </div>
        <button
          className="btn btn--primary"
          onClick={() => onStart({ doc_id: "", focus: "", tab: "" })}
          disabled={busy || !connected}
        >
          {!connected ? "Connecting…" : busy ? "Running…" : "Start walkthrough"}
        </button>
      </section>
    );
  }

  return (
    <section className="setup">
      <div className="setup__grid">
        <div className="setup__field">
          <label className="setup__label" htmlFor="setup-doc">
            1 · Product document
          </label>
          <input
            id="setup-doc"
            className="setup__file"
            type="file"
            accept=".md,.txt,.pdf,.docx,.html,.htm"
            onChange={(e) => onFile(e.target.files?.[0])}
            disabled={busy}
          />
          <textarea
            className="setup__paste"
            placeholder="…or paste the flow description here"
            value={pasted}
            onChange={(e) => setPasted(e.target.value)}
            disabled={busy}
            rows={3}
          />
          <div className="setup__row">
            <button
              className="btn btn--small"
              onClick={usePasted}
              disabled={busy || working || !pasted.trim()}
            >
              Use pasted text
            </button>
            {samples.map((sample) => (
              <button
                key={sample.name}
                className="btn btn--small"
                onClick={() => useSample(sample)}
                disabled={busy || working}
                title={sample.title}
              >
                {/* The product name is the useful part — "YouTube", not
                    "YouTube — Search and Watch Later". */}
                {sample.title.split(/[—–:]/)[0].trim()} sample
              </button>
            ))}
          </div>
        </div>

        <div className="setup__field">
          <label className="setup__label" htmlFor="setup-focus">
            2 · What should I demo?
          </label>
          <input
            id="setup-focus"
            className="setup__input"
            placeholder="e.g. how a viewer builds a playlist"
            value={focus}
            onChange={(e) => setFocus(e.target.value)}
            disabled={busy}
          />
          <p className="setup__hint">
            Plain English. The agent plans against this and the live page.
          </p>
        </div>

        <div className="setup__field">
          <div className="setup__labelrow">
            <label className="setup__label" htmlFor="setup-tab">
              3 · Which tab?
            </label>
            <button
              className="btn btn--small"
              onClick={onRefreshTabs}
              disabled={busy || tabsLoading}
            >
              {tabsLoading ? "Looking…" : "Refresh"}
            </button>
          </div>

          <input
            id="setup-tab"
            className="setup__input"
            placeholder="youtube, github.com, or a full URL"
            value={tab}
            onChange={(e) => setTab(e.target.value)}
            disabled={busy}
          />

          {chromeAttached ? (
            <ul className="tablist">
              {tabs.map((t) => (
                <li key={t.index}>
                  <button
                    className={`tablist__item${
                      tab && (t.host === tab || t.url === tab)
                        ? " is-picked"
                        : ""
                    }`}
                    onClick={() => setTab(t.host || t.url)}
                    disabled={busy}
                    title={t.url}
                  >
                    <span className="tablist__host">{t.host}</span>
                    <span className="tablist__title">{t.title || t.url}</span>
                  </button>
                </li>
              ))}
              {tabs.length === 0 && !tabsLoading && (
                <li className="setup__hint">
                  No tabs open yet — open the product in Chrome, then refresh.
                </li>
              )}
            </ul>
          ) : (
            <div className="setup__warn">
              <p>{chromeHint || "Not connected to Chrome yet."}</p>
              {chromeCommand && (
                <>
                  <code className="setup__cmd">{chromeCommand}</code>
                  <button className="btn btn--small" onClick={copyCommand}>
                    {copied ? "Copied" : "Copy command"}
                  </button>
                </>
              )}
            </div>
          )}
        </div>
      </div>

      <div className="setup__footer">
        <span className="setup__note">
          {note || (doc ? "Ready when you are." : "Start with a document.")}
        </span>
        <button
          className="btn btn--primary"
          onClick={() =>
            onStart({ doc_id: doc?.id ?? "", focus, tab })
          }
          disabled={!ready}
        >
          {!connected ? "Connecting…" : busy ? "Running…" : "Start walkthrough"}
        </button>
      </div>
    </section>
  );
}
