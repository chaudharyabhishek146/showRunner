"use client";

/**
 * Narration read aloud via the Web Speech API.
 *
 * Browser-native TTS is deliberate: no audio round trip, so speech starts the
 * same frame the narration text arrives and stays in step with the browser
 * panel. A server-side TTS call would put a second or two between what the
 * viewer reads and what they hear.
 */

function synth(): SpeechSynthesis | null {
  if (typeof window === "undefined" || !("speechSynthesis" in window))
    return null;
  return window.speechSynthesis;
}

/** Prefer a natural English voice; fall back to whatever the platform gives. */
function pickVoice(s: SpeechSynthesis): SpeechSynthesisVoice | null {
  const voices = s.getVoices();
  if (!voices.length) return null;
  const preferred = ["Samantha", "Google US English", "Microsoft Aria"];
  for (const name of preferred) {
    const match = voices.find((v) => v.name.includes(name));
    if (match) return match;
  }
  return voices.find((v) => v.lang.startsWith("en")) ?? voices[0];
}

export function speak(text: string): void {
  const s = synth();
  if (!s || !text.trim()) return;
  s.cancel(); // one voice at a time — never let two lines overlap

  const utterance = new SpeechSynthesisUtterance(text);
  const voice = pickVoice(s);
  if (voice) utterance.voice = voice;
  utterance.rate = 1.02;
  utterance.pitch = 1.0;
  s.speak(utterance);
}

export function cancelSpeech(): void {
  synth()?.cancel();
}

export function voiceSupported(): boolean {
  return synth() !== null;
}
