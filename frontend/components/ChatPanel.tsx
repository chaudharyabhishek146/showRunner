"use client";

import { useEffect, useRef, useState } from "react";
import type { ChatMessage } from "@/lib/types";

interface Props {
  messages: ChatMessage[];
  thinking: boolean;
  disabled: boolean;
  onAsk: (text: string) => void;
}

const SUGGESTIONS = [
  "Can one issue live on two boards?",
  "How is this different from labels?",
  "Skip ahead to the project board",
];

/** The left half: narration as it's spoken, plus the interrupt box. */
export default function ChatPanel({
  messages,
  thinking,
  disabled,
  onAsk,
}: Props) {
  const [draft, setDraft] = useState("");
  const feedRef = useRef<HTMLDivElement>(null);

  // Pin to the newest line; the demo is a live feed, not a scrollback.
  useEffect(() => {
    feedRef.current?.scrollTo({
      top: feedRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages.length, thinking]);

  const submit = (text: string) => {
    if (!text.trim() || disabled) return;
    onAsk(text);
    setDraft("");
  };

  return (
    <section className="chat">
      <div className="chat__feed" ref={feedRef}>
        {messages.length === 0 && (
          <p className="chat__hint">
            Start the walkthrough — narration appears here. Interrupt with a
            question at any time and the browser will hold its place.
          </p>
        )}

        {messages.map((m) => (
          <article key={m.id} className={`bubble bubble--${m.role}`}>
            {m.role !== "system" && (
              <span className="bubble__who">
                {m.role === "agent" ? "Agent" : "You"}
              </span>
            )}
            <p className="bubble__text">{m.text}</p>
          </article>
        ))}

        {thinking && (
          <article className="bubble bubble--agent bubble--thinking">
            <span className="bubble__who">Agent</span>
            <p className="bubble__text">
              <i /> <i /> <i />
            </p>
          </article>
        )}
      </div>

      <div className="chat__suggestions">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            className="chip"
            disabled={disabled}
            onClick={() => submit(s)}
          >
            {s}
          </button>
        ))}
      </div>

      <form
        className="chat__composer"
        onSubmit={(e) => {
          e.preventDefault();
          submit(draft);
        }}
      >
        <input
          className="chat__input"
          value={draft}
          disabled={disabled}
          placeholder="Interrupt with a question…"
          onChange={(e) => setDraft(e.target.value)}
        />
        <button className="chat__send" type="submit" disabled={disabled || !draft.trim()}>
          Ask
        </button>
      </form>
    </section>
  );
}
