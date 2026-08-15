/**
 * Generates the pitch deck for the Platform Walkthrough Agent.
 *
 * Kept in the repo next to build_report.py so both deliverables can be
 * regenerated when the project changes.
 *
 *     node docs/build_deck.js
 *
 * Every slide carries the spoken script in its speaker notes.
 */

const pptxgen = require("pptxgenjs");
const path = require("path");

// Not "platform-walkthrough-agent.pptx": converting that to PDF for review
// would land on the build report's filename and overwrite it.
const OUT = path.join(__dirname, "walkthrough-agent-deck.pptx");

// The product's own palette. The app is a dark tool with a single orange
// accent, so the deck is too — a judge who sees the screen share and then the
// deck should read them as one thing.
const BG = "0F1219";
const SURFACE = "1A202C";
const SURFACE_2 = "232B3A";
const ACCENT = "FF5C00";
const ACCENT_DEEP = "3A2010";
const TEXT = "EDF1F8";
const MUTED = "8E99AE";
const GREEN = "34D399";

const TITLE_FONT = "Cambria";
const BODY_FONT = "Calibri";
const MONO = "Courier New";

const W = 13.333;
const H = 7.5;
const M = 0.62; // page margin

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // must be set before any slide is added
pres.author = "ShowRunner";
pres.title = "Platform Walkthrough Agent";

// ---------------------------------------------------------------- helpers

function slide(notes) {
  const s = pres.addSlide();
  s.background = { color: BG };
  if (notes) s.addNotes(notes);
  return s;
}

/** Slide title plus optional deck (kicker) line above it. */
function heading(s, kicker, title, opts = {}) {
  const y = opts.y === undefined ? 0.5 : opts.y;
  if (kicker) {
    s.addText(kicker.toUpperCase(), {
      x: M, y: y, w: 9, h: 0.3,
      fontFace: BODY_FONT, fontSize: 11, bold: true, color: ACCENT,
      charSpacing: 2, margin: 0,
    });
  }
  s.addText(title, {
    // h has to be passed for a two-line title — the box does not grow, and a
    // clipped title is the most visible defect a deck can ship.
    x: M, y: y + (kicker ? 0.34 : 0), w: opts.w || 11.6, h: opts.h || 0.72,
    fontFace: TITLE_FONT, fontSize: opts.size || 34, bold: true, color: TEXT,
    lineSpacing: (opts.size || 34) * 1.16, valign: "top", margin: 0,
  });
}

/** A surface card. Fresh option objects each call — pptxgenjs mutates them. */
function card(s, x, y, w, h, fill) {
  s.addShape(pres.ShapeType.roundRect, {
    x, y, w, h,
    rectRadius: 0.08,
    fill: { color: fill || SURFACE },
    line: { color: fill || SURFACE, width: 0.5 },
  });
}

/** The recurring motif: a filled circle carrying a number or short glyph. */
function bubble(s, x, y, label, size = 0.44, fill = ACCENT, color = "0F1219") {
  s.addShape(pres.ShapeType.ellipse, {
    x, y, w: size, h: size,
    fill: { color: fill },
    line: { color: fill, width: 0.5 },
  });
  s.addText(String(label), {
    x, y, w: size, h: size,
    fontFace: BODY_FONT, fontSize: 14, bold: true, color,
    align: "center", valign: "middle", margin: 0,
  });
}

/**
 * Monospace trace block on an inset panel.
 *
 * The panel sizes itself to the number of lines: a fixed height left an inch
 * of dead space under short traces, which reads as a layout mistake rather
 * than as breathing room. `h` is treated as a minimum.
 */
function trace(s, x, y, w, h, lines, fontSize = 11) {
  const natural = (lines.length * fontSize * 1.45) / 72 + 0.34;
  h = Math.max(Math.min(h, natural), Math.min(h, 0.6));
  s.addShape(pres.ShapeType.roundRect, {
    x, y, w, h,
    rectRadius: 0.05,
    fill: { color: "0A0D13" },
    line: { color: SURFACE_2, width: 1 },
  });
  s.addText(lines.join("\n"), {
    x: x + 0.22, y: y + 0.16, w: w - 0.44, h: h - 0.32,
    fontFace: MONO, fontSize, color: "B9C4D6",
    lineSpacing: fontSize * 1.45, valign: "top", margin: 0,
  });
}

function body(s, x, y, w, h, text, opts = {}) {
  s.addText(text, {
    x, y, w, h,
    fontFace: BODY_FONT, fontSize: opts.size || 15, color: opts.color || MUTED,
    lineSpacing: opts.lineSpacing || (opts.size || 15) * 1.5,
    align: "left", valign: "top", margin: 0,
    ...(opts.bold ? { bold: true } : {}),
  });
}

// ------------------------------------------------------------------ 1. title

{
  const s = slide(
    "Hi — this is the Platform Walkthrough Agent.\n\n" +
    "The one-line version: it gives the product demo for you. You upload a " +
    "product document, tell it what to show, and point it at one of your open " +
    "browser tabs. It plans the walkthrough against the page that's actually " +
    "on screen, drives your own signed-in Chrome, narrates as it goes — and " +
    "when someone interrupts with a question, it freezes mid-step, answers " +
    "from the doc and the live screen, and resumes exactly where it stopped.\n\n" +
    "I want to spend most of this on two things: the interruption handling, " +
    "which is the part that's actually hard, and the seven bugs that only " +
    "showed up when I pointed it at a real product."
  );

  s.addShape(pres.ShapeType.ellipse, {
    x: M, y: 1.95, w: 0.34, h: 0.34,
    fill: { color: BG }, line: { color: ACCENT, width: 3 },
  });

  s.addText("HACKATHON SUBMISSION", {
    x: M + 0.58, y: 1.98, w: 6, h: 0.3,
    fontFace: BODY_FONT, fontSize: 12, bold: true, color: ACCENT,
    charSpacing: 2.5, margin: 0,
  });

  s.addText("Platform\nWalkthrough Agent", {
    x: M, y: 2.5, w: 7.6, h: 2.0,
    fontFace: TITLE_FONT, fontSize: 52, bold: true, color: TEXT,
    lineSpacing: 58, margin: 0,
  });

  s.addText(
    "An agent that gives the product demo — in your own browser, on the real " +
    "product, and it stops when you ask it something.",
    {
      x: M, y: 4.65, w: 7.4, h: 0.95,
      fontFace: BODY_FONT, fontSize: 17, color: MUTED, lineSpacing: 26, margin: 0,
    }
  );

  const chips = [
    ["FastAPI", "Playwright / CDP"],
    ["Claude Opus 5", "Next.js 15"],
  ];
  let cy = 5.85;
  chips.forEach((row) => {
    let cx = M;
    row.forEach((label) => {
      const w = 0.16 * label.length + 0.5;
      s.addShape(pres.ShapeType.roundRect, {
        x: cx, y: cy, w, h: 0.36, rectRadius: 0.18,
        fill: { color: SURFACE }, line: { color: SURFACE_2, width: 1 },
      });
      s.addText(label, {
        x: cx, y: cy, w, h: 0.36,
        fontFace: BODY_FONT, fontSize: 12, color: MUTED,
        align: "center", valign: "middle", margin: 0,
      });
      cx += w + 0.16;
    });
    cy += 0.5;
  });

  // Right-hand proof panel: the thing itself, mid-interruption.
  card(s, 8.5, 2.3, 4.2, 4.05, SURFACE);
  s.addText("A LIVE RUN", {
    x: 8.8, y: 2.55, w: 3.6, h: 0.28,
    fontFace: BODY_FONT, fontSize: 10, bold: true, color: ACCENT,
    charSpacing: 2, margin: 0,
  });
  trace(s, 8.8, 2.95, 3.6, 3.1, [
    "2.7s  Chrome attached",
    "16.7s PLAN: 3 steps",
    "22.6s step 1 done",
    '      "Any questions?"',
    "26.6s >>> show me how",
    "      to filter",
    "33.0s re-planning...",
    "65.5s clicked",
    "      'Jet engines'",
    "156s  [complete]",
    "      errors: []",
  ], 11);
}

// ------------------------------------------------------------ 2. the problem

{
  const s = slide(
    "Here's the problem I actually cared about.\n\n" +
    "Anyone can script a browser. Recording a demo is solved, and clicking " +
    "through one yourself is solved. The engineering that matters is what " +
    "happens when the customer interrupts — because that is the entire " +
    "difference between a demo and a screen recording.\n\n" +
    "A recording can't answer a question. A scripted click-through loses its " +
    "place. So the design question I started from wasn't 'can it drive a " +
    "browser' — it was 'can it be interrupted and survive it'."
  );
  heading(s, "the problem", "Anyone can script a browser");

  body(s, M, 1.95, 6.0,  2.4,
    "Recording a demo is a solved problem. So is clicking through one yourself. " +
    "The engineering that matters here is what happens when the customer " +
    "interrupts — because that is the entire difference between a demo and a " +
    "screen recording.",
    { size: 17, color: TEXT, lineSpacing: 27 });

  const fails = [
    ["A recording", "Can't answer anything. The moment someone asks, you're pausing a video and talking over it."],
    ["A scripted click-through", "Answers, then loses its place — replays a step, or skips one nobody saw."],
    ["A generic browser agent", "Wanders. It has no plan, so there is nothing to return to."],
  ];
  let y = 4.35;
  fails.forEach(([t, d]) => {
    s.addText(t, {
      x: M, y, w: 5.6, h: 0.3,
      fontFace: BODY_FONT, fontSize: 14, bold: true, color: TEXT, margin: 0,
    });
    s.addText(d, {
      x: M, y: y + 0.3, w: 5.7, h: 0.5,
      fontFace: BODY_FONT, fontSize: 12.5, color: MUTED, lineSpacing: 17, margin: 0,
    });
    y += 0.92;
  });

  card(s, 7.1, 1.9, 5.62, 4.55, SURFACE);
  s.addText("THE HARD PART", {
    x: 7.5, y: 2.2, w: 4.8, h: 0.3,
    fontFace: BODY_FONT, fontSize: 11, bold: true, color: ACCENT,
    charSpacing: 2, margin: 0,
  });
  s.addText("Freeze. Answer. Resume — in the same step.", {
    x: 7.5, y: 2.55, w: 4.9, h: 0.75,
    fontFace: TITLE_FONT, fontSize: 22, bold: true, color: TEXT,
    lineSpacing: 28, margin: 0,
  });

  const steps = [
    ["Freeze", "The loop parks on an asyncio.Event, checked between actions — not just between steps."],
    ["Answer", "Claude gets the product doc as cached context plus the current screenshot."],
    ["Resume", "current_index only advances after a step fully completes. Never rewinds, never skips."],
  ];
  let sy = 3.5;
  steps.forEach(([t, d], i) => {
    bubble(s, 7.5, sy, i + 1, 0.4);
    s.addText(t, {
      x: 8.06, y: sy - 0.03, w: 4.2, h: 0.28,
      fontFace: BODY_FONT, fontSize: 14, bold: true, color: TEXT, margin: 0,
    });
    s.addText(d, {
      x: 8.06, y: sy + 0.25, w: 4.3, h: 0.6,
      fontFace: BODY_FONT, fontSize: 12, color: MUTED, lineSpacing: 16, margin: 0,
    });
    sy += 0.98;
  });
}

// ----------------------------------------------------------- 3. how it works

{
  const s = slide(
    "Here's the shape of a run, and the ordering matters more than it looks.\n\n" +
    "You upload the product document. You say what to demo, in plain English. " +
    "The agent attaches to your Chrome over the DevTools protocol — your " +
    "Chrome, the one you're already signed into — and picks the tab you named. " +
    "Then, and only then, it reads an accessibility outline of the page that's " +
    "actually open, and plans against those controls.\n\n" +
    "That ordering — attach, pick the tab, read the page, THEN plan — is the " +
    "whole reason one prompt works on a site the code has never seen. It isn't " +
    "planning from memory of what GitHub looks like. It's planning from what's " +
    "on the screen right now."
  );
  heading(s, "how it works", "Attach → pick the tab → read that page → plan");

  const steps = [
    ["1", "Upload the doc", "Markdown, PDF, docx, HTML. Content-addressed, so re-uploading is free."],
    ["2", "Say what to demo", "Plain English: “how a viewer saves a video for later.”"],
    ["3", "Attach & pick the tab", "CDP into your running Chrome. Names a tab, or refuses to guess."],
    ["4", "Read, then plan", "An a11y outline of the live page becomes the planner's vocabulary."],
  ];

  let x = M;
  const cw = 2.8;
  steps.forEach(([n, t, d]) => {
    card(s, x, 2.0, cw, 2.25, SURFACE);
    bubble(s, x + 0.28, 2.26, n, 0.42);
    s.addText(t, {
      x: x + 0.28, y: 2.85, w: cw - 0.56, h: 0.6,
      fontFace: BODY_FONT, fontSize: 15, bold: true, color: TEXT,
      lineSpacing: 20, margin: 0,
    });
    s.addText(d, {
      x: x + 0.28, y: 3.42, w: cw - 0.56, h: 0.75,
      fontFace: BODY_FONT, fontSize: 12, color: MUTED, lineSpacing: 16, margin: 0,
    });
    x += cw + 0.3;
  });

  card(s, M, 4.55, 12.1, 1.95, SURFACE_2);
  s.addText("Why that order?", {
    x: M + 0.35, y: 4.8, w: 3.4, h: 0.35,
    fontFace: BODY_FONT, fontSize: 15, bold: true, color: ACCENT, margin: 0,
  });
  s.addText(
    "Planning happens only after the agent can see the live DOM. Nothing about any site is compiled in — " +
    "no target URL, no repo, no stored session. The same build demos GitHub, YouTube, or an internal tool; " +
    "the only difference is the document you upload and the tab you name.",
    {
      x: M + 0.35, y: 5.2, w: 11.4, h: 1.1,
      fontFace: BODY_FONT, fontSize: 14.5, color: TEXT, lineSpacing: 22, margin: 0,
    }
  );
}

// ------------------------------------------------- 4. the interruption proof

{
  const s = slide(
    "This is the slide I'd like to be judged on.\n\n" +
    "Mid-demo, I asked it: 'show me how to filter the results.' Watch what it " +
    "does. It answers — grounded in the doc and the screenshot. Then it decides " +
    "that wasn't a question, it was a redirect, so it re-plans only the " +
    "remaining steps and actually goes and clicks the filter chip. It " +
    "demonstrates the thing instead of describing it.\n\n" +
    "Answering and deciding-whether-to-redirect are the same judgement, so " +
    "they're one API call — a second classifier round trip would double the " +
    "pause the customer sits through.\n\n" +
    "And getting here required fixing a real bug: the run loop held the " +
    "executing step in a local variable, so swapping the plan mid-step " +
    "finished the old step and advanced straight past the new one. The " +
    "customer got a tidy answer and watched the demo carry on as though they " +
    "hadn't spoken. There's a test pinning that now."
  );
  heading(s, "the differentiator", "An interruption redirects the browser,\nnot just the answer", { size: 29, h: 1.2 });

  trace(s, M, 2.35, 7.15, 3.6, [
    '>>> "show me how to filter the results"',
    "",
    " 33.0s [answer]  see the row of chips under",
    "                 the search box...",
    " 33.0s [status]  Re-planning around:",
    "                 filtering with the chips",
    " 65.5s [step]    clicked 'Jet engines'",
    "                 -> results reshape",
    " 88.4s [step]    typed a query, Enter,",
    "                 results landed",
    "156.6s [complete]   steps: [1,2,3] errors: []",
  ], 11.5);

  s.addText("Completed steps are preserved verbatim and never replayed.", {
    x: M, y: 6.05, w: 7.2, h: 0.3,
    fontFace: BODY_FONT, fontSize: 12, italic: true, color: MUTED, margin: 0,
  });

  const points = [
    ["One call, two jobs", "QAResponse returns the answer, whether the demo was redirected, and what to show — together."],
    ["“Show me” is an instruction", "“How do I X” and “can it do X” are requests to be shown X, not to be told."],
    ["The bug underneath", "The loop cached the step it was running, so a mid-step re-plan was skipped entirely. Fixed, and pinned by a test that fails against the old code."],
  ];
  let y = 2.35;
  points.forEach(([t, d]) => {
    card(s, 8.1, y, 4.62, 1.22, SURFACE);
    s.addText(t, {
      x: 8.4, y: y + 0.16, w: 4.1, h: 0.3,
      fontFace: BODY_FONT, fontSize: 14, bold: true, color: TEXT, margin: 0,
    });
    s.addText(d, {
      x: 8.4, y: y + 0.48, w: 4.05, h: 0.65,
      fontFace: BODY_FONT, fontSize: 11.5, color: MUTED, lineSpacing: 15, margin: 0,
    });
    y += 1.35;
  });
}

// -------------------------------------------------------- 5. site-agnostic

{
  const s = slide(
    "The claim is that nothing about any site is compiled in. Here's the " +
    "evidence rather than the assertion.\n\n" +
    "Two runs, same server, same code, real Claude, real Chrome. The only " +
    "difference between them is the document I uploaded, the sentence " +
    "describing the flow, and the tab I named. One demos YouTube. One demos " +
    "GitHub Explore — and takes an in-scope hop to github.com/trending on the " +
    "way.\n\n" +
    "Both handled a mid-demo interruption. On the YouTube one, someone asked " +
    "about cross-device sync — which isn't in the document. It said so, and " +
    "declined to guess. That's the behaviour you want in front of a customer."
  );
  heading(s, "site-agnostic", "Same build. Two products. Two documents.");

  const runs = [
    {
      tab: 'tab: "youtube"',
      doc: '"Watch Later — product flow"',
      lines: [
        "6 steps planned from the live page",
        "6/6 executed, 0 failed actions",
        "interrupt after step 2 ->",
        "  pausing -> answered -> resumed at 3",
        "",
        "asked about cross-device sync:",
        "not in the doc, so it said so",
        "and declined to guess",
      ],
    },
    {
      tab: 'tab: "github"',
      doc: '"Explore — product flow"',
      lines: [
        "6 steps planned from the live page",
        "in-scope hop to github.com/trending",
        "",
        'interrupt: "Can I filter Explore',
        '  by language?" -> answered',
        "  from what was on the page",
        "",
        "173 live frames, 18 stills",
      ],
    },
  ];

  let x = M;
  runs.forEach((r) => {
    card(s, x, 2.0, 5.9, 4.05, SURFACE);
    s.addText(r.doc, {
      x: x + 0.34, y: 2.28, w: 5.4, h: 0.32,
      fontFace: BODY_FONT, fontSize: 16, bold: true, color: TEXT, margin: 0,
    });
    s.addText(r.tab, {
      x: x + 0.34, y: 2.62, w: 5.4, h: 0.3,
      fontFace: MONO, fontSize: 12, color: ACCENT, margin: 0,
    });
    trace(s, x + 0.34, 3.05, 5.22, 2.75, r.lines, 11);
    x += 6.2;
  });

  s.addText(
    "No target URL. No repo. No stored session. The navigation allowlist is derived at run time from the tab you picked.",
    {
      x: M, y: 6.3, w: 12.1, h: 0.4,
      fontFace: BODY_FONT, fontSize: 14, color: MUTED, align: "left", margin: 0,
    }
  );
}

// -------------------------------------------------------- 6. architecture

{
  const s = slide(
    "Quickly, the architecture.\n\n" +
    "Next.js talks to FastAPI over a WebSocket for the demo itself, plus plain " +
    "REST for setup so the tab picker works before any session exists. The " +
    "StepExecutor owns the pause gate. Playwright attaches over CDP to your own " +
    "Chrome.\n\n" +
    "Two details worth calling out. First, the overlay: the OS mouse pointer " +
    "is not composited into screenshots, so without it the audience watches " +
    "buttons activate by themselves. The agent draws its own cursor, spotlight " +
    "and caption into the page — which also means the browser window is " +
    "self-explanatory when it's shared without the app.\n\n" +
    "Second, the action vocabulary is closed: six verbs, and elements are " +
    "addressed by ARIA role plus accessible name. Claude never emits a CSS " +
    "selector. Products rewrite their class names constantly; what a control " +
    "is and what it's called survive a deploy."
  );
  heading(s, "architecture", "Six verbs, semantic locators, one pause gate");

  const boxes = [
    ["Next.js UI", "narration · live view\nstep progress"],
    ["FastAPI", "WebSocket + REST\nsession state"],
    ["StepExecutor", "asyncio.Event\npause / resume gate"],
    ["Playwright", "CDP into your\nsigned-in Chrome"],
  ];
  let x = M;
  const bw = 2.72;
  boxes.forEach(([t, d], i) => {
    card(s, x, 2.05, bw, 1.5, i === 2 ? ACCENT_DEEP : SURFACE);
    s.addText(t, {
      x: x + 0.22, y: 2.25, w: bw - 0.44, h: 0.32,
      fontFace: BODY_FONT, fontSize: 15, bold: true,
      color: i === 2 ? ACCENT : TEXT, margin: 0,
    });
    s.addText(d, {
      x: x + 0.22, y: 2.62, w: bw - 0.44, h: 0.75,
      fontFace: BODY_FONT, fontSize: 11.5, color: MUTED, lineSpacing: 16, margin: 0,
    });
    if (i < 3) {
      s.addText("»", {
        x: x + bw + 0.02, y: 2.5, w: 0.36, h: 0.4,
        fontFace: BODY_FONT, fontSize: 20, bold: true, color: ACCENT,
        align: "center", margin: 0,
      });
    }
    x += bw + 0.36;
  });

  const notes = [
    ["The overlay is drawn into the page",
     "The OS pointer isn't captured in screenshots, so the agent injects its own cursor, glides it to each target, " +
     "spotlights the element and burns the narration in as a caption. The browser window explains itself even when " +
     "shared without the app."],
    ["The action vocabulary is closed",
     "navigate · click · fill · press · wait · highlight — and elements are addressed by ARIA role plus accessible " +
     "name, never CSS or XPath. Constraining the vocabulary is what makes an LLM-authored plan safely executable."],
  ];
  let y = 3.9;
  notes.forEach(([t, d]) => {
    card(s, M, y, 12.1, 1.22, SURFACE);
    s.addText(t, {
      x: M + 0.35, y: y + 0.16, w: 11.4, h: 0.3,
      fontFace: BODY_FONT, fontSize: 15, bold: true, color: ACCENT, margin: 0,
    });
    s.addText(d, {
      x: M + 0.35, y: y + 0.5, w: 11.4, h: 0.62,
      fontFace: BODY_FONT, fontSize: 12.5, color: MUTED, lineSpacing: 17, margin: 0,
    });
    y += 1.4;
  });
}

// ------------------------------------------------------------- 7. safety

{
  const s = slide(
    "Safety, briefly — because this is an LLM-authored plan driving a browser " +
    "signed into real accounts.\n\n" +
    "Credentials are never typed. There is no login-form code path at all. " +
    "Authentication comes from the browser profile you're already signed into, " +
    "which means the whole class of problem disappears rather than being " +
    "managed. The only secret in the repo is the Anthropic API key.\n\n" +
    "The navigation allowlist is derived from the tab you picked — its host " +
    "plus its registrable domain — and it's enforced twice in code: once when " +
    "sanitising the plan, and again immediately before the navigation happens. " +
    "With no tab chosen, the allowlist is empty and everything fails closed. " +
    "The prompt asks; the code enforces.\n\n" +
    "And it asks whether you want to sign in before it plans anything, because " +
    "signed-out and signed-in are different products."
  );
  heading(s, "safety", "The prompt asks. The code enforces.");

  const rows = [
    ["Credentials", "Never typed. No login-form code path, no stored cookie. Auth comes from the attached profile. The only secret in the repo is ANTHROPIC_API_KEY."],
    ["Navigation", "Allowlist derived from the chosen tab, checked in the plan sanitiser AND again immediately before page.goto. Empty allowlist = nothing is in scope."],
    ["Destructive actions", "The planner is told to prefer showing over changing: never delete, send, publish, pay, or alter account settings."],
    ["Signed-in state", "Detected before planning. Signed out, it points at where account features live instead of clicking things it cannot complete."],
    ["Your browser", "An attached browser is never closed on teardown — stop() disconnects. Auto-launch only ever fires for a CDP URL on this machine."],
  ];

  let y = 1.95;
  rows.forEach(([t, d], i) => {
    card(s, M, y, 12.1, 0.86, i % 2 === 0 ? SURFACE : SURFACE_2);
    s.addText(t, {
      x: M + 0.32, y: y + 0.16, w: 2.6, h: 0.55,
      fontFace: BODY_FONT, fontSize: 14, bold: true, color: ACCENT,
      valign: "middle", margin: 0,
    });
    s.addText(d, {
      x: M + 3.1, y: y + 0.13, w: 8.7, h: 0.62,
      fontFace: BODY_FONT, fontSize: 12.5, color: TEXT, lineSpacing: 17,
      valign: "middle", margin: 0,
    });
    y += 0.95;
  });
}

// -------------------------------------------------------------- 8. defects

{
  const s = slide(
    "This is my favourite slide, and it's the one I'd point a sceptical judge at.\n\n" +
    "Seven defects. Every one of them passed unit tests and failed in front of " +
    "a live page.\n\n" +
    "YouTube enforces a Trusted Types CSP, so building the cursor with " +
    "innerHTML threw — and took the whole overlay down with it, including the " +
    "captions. Single-page apps re-render document.body and took our injected " +
    "nodes with them, so the cursor silently vanished part-way through. " +
    "Substring name matching meant every click meant for the sidebar 'You' " +
    "entry landed on the YouTube logo, because a union locator returns matches " +
    "in DOM order — the page was choosing, not us. And the search step typed " +
    "into a button: YouTube's search field is a combobox, not a textbox, so the " +
    "role fallback chain reached the Search button. Typing into a button raises " +
    "nothing and does nothing, and the trace still said 'typed into Search'.\n\n" +
    "The point isn't that I wrote bugs. It's that none of these are findable " +
    "without pointing the thing at a real product, and all of them would have " +
    "been visible on stage."
  );
  heading(s, "what running it live taught me", "Seven defects that only a real product surfaced");

  const bugs = [
    ["Trusted Types killed the overlay", "YouTube's CSP made the cursor's innerHTML throw — taking captions down with it. Now built with createElementNS."],
    ["SPAs dropped the overlay", "Re-rendered document.body took our nodes. The builder trusted a boolean; it checks isConnected now."],
    ["A locator clicked the logo", 'name="You" also matched “YouTube Home”, earlier in the DOM. Exact names before substrings, visible matches only.'],
    ["A re-plan was skipped", "The loop cached the running step, finished it, and advanced past the new one. Pinned by a test."],
    ["The sign-in prompt deadlocked", "start() awaited the reply on the same socket that had to read it. Backgrounded now."],
    ["The search typed into a button", "YouTube's search box is a combobox. A fill now only considers editable roles — and verifies before typing."],
  ];

  let x = M, y = 2.0;
  bugs.forEach(([t, d], i) => {
    card(s, x, y, 3.9, 1.55, SURFACE);
    bubble(s, x + 0.26, y + 0.24, String(i + 1).padStart(2, "0"), 0.4);
    s.addText(t, {
      x: x + 0.76, y: y + 0.22, w: 2.9, h: 0.46,
      fontFace: BODY_FONT, fontSize: 13, bold: true, color: TEXT,
      lineSpacing: 16, margin: 0,
    });
    s.addText(d, {
      x: x + 0.26, y: y + 0.78, w: 3.4, h: 0.68,
      fontFace: BODY_FONT, fontSize: 11, color: MUTED, lineSpacing: 14.5, margin: 0,
    });
    x += 4.1;
    if ((i + 1) % 3 === 0) { x = M; y += 1.72; }
  });

  s.addText(
    "Seventh: Chrome 136+ refuses the debug port on the default profile, and Chrome 151 rejects the CDP handshake " +
    "without --enable-automation. Found by testing flags one at a time.",
    {
      x: M, y: 5.62, w: 12.1, h: 0.5,
      fontFace: BODY_FONT, fontSize: 12.5, italic: true, color: MUTED,
      lineSpacing: 17, margin: 0,
    }
  );
}

// -------------------------------------------------------------- 9. measured

{
  const s = slide(
    "Numbers, all from runs in this build — nothing estimated.\n\n" +
    "Cold start: 2.7 seconds from no browser at all to attached and sitting on " +
    "the product. If the debug port isn't open, the agent runs the launch " +
    "command itself.\n\n" +
    "Pause takes 1.52 seconds to actually park, and that's deliberate — an " +
    "action already in flight runs to completion, because cancelling mid-action " +
    "would leave a half-typed field on screen in front of the customer. Zero " +
    "actions start after it's parked. The UI is honest about the gap: it reads " +
    "PAUSING while the browser is still settling, and only flips to PAUSED once " +
    "it's actually stopped.\n\n" +
    "And 25 hermetic tests in 2.7 seconds — no network, no Claude calls, no " +
    "browser — so the pause/resume guarantee is verified on every commit rather " +
    "than rehearsed before every call."
  );
  heading(s, "measured, not estimated", "Every number here came out of a run");

  const stats = [
    ["2.7s", "no browser →\nattached, on the product"],
    ["1.52s", "pause request →\nbrowser truly parked"],
    ["0", "actions started\nafter parked"],
    ["25", "hermetic tests,\npassing in 2.7s"],
  ];
  let x = M;
  stats.forEach(([n, l]) => {
    card(s, x, 2.05, 2.95, 2.05, SURFACE);
    s.addText(n, {
      x: x + 0.25, y: 2.25, w: 2.45, h: 0.85,
      fontFace: TITLE_FONT, fontSize: 44, bold: true, color: ACCENT, margin: 0,
    });
    s.addText(l, {
      x: x + 0.25, y: 3.18, w: 2.5, h: 0.75,
      fontFace: BODY_FONT, fontSize: 12, color: MUTED, lineSpacing: 16, margin: 0,
    });
    x += 3.05;
  });

  card(s, M, 4.4, 5.95, 2.15, SURFACE_2);
  s.addText("Pause is slow on purpose", {
    x: M + 0.32, y: 4.62, w: 5.3, h: 0.32,
    fontFace: BODY_FONT, fontSize: 15, bold: true, color: TEXT, margin: 0,
  });
  s.addText(
    "An action already in flight runs to completion — cancelling mid-action would leave a half-typed field on " +
    "screen in front of the customer. The UI reads PAUSING while the browser settles, and only flips to PAUSED " +
    "once it has actually stopped.",
    {
      x: M + 0.32, y: 5.0, w: 5.35, h: 1.4,
      fontFace: BODY_FONT, fontSize: 12.5, color: MUTED, lineSpacing: 17, margin: 0,
    }
  );

  card(s, 6.85, 4.4, 5.85, 2.15, SURFACE_2);
  s.addText("The two-minute demo, timed", {
    x: 7.17, y: 4.62, w: 5.2, h: 0.32,
    fontFace: BODY_FONT, fontSize: 15, bold: true, color: TEXT, margin: 0,
  });
  trace(s, 7.17, 5.0, 5.2, 1.35, [
    "22.6s  step 1 done -> \"Any questions?\"",
    "27.6s  answered; window restarts",
    "67.0s  \"Any questions before we wrap up?\"",
    "87.1s  [complete]",
  ], 10.5);
}

// -------------------------------------------------------------- 10. harness

{
  const s = slide(
    "The Harness piece — this is what turns a demo script into shared " +
    "infrastructure.\n\n" +
    "The walkthrough is registered as a Worker Agent Skill: versioned, " +
    "RBAC-governed, callable from the catalog by any team. A solutions engineer " +
    "in another region invokes the same skill instead of rebuilding the demo. " +
    "Sessions pin to the skill version they started on, so a deploy can never " +
    "change the demo out from under a customer who's mid-call.\n\n" +
    "The pipeline's real gate is the pause/resume test suite. A walkthrough " +
    "that rewinds when someone asks a question is worse than no demo at all, so " +
    "that behaviour is verified on every commit rather than rehearsed before " +
    "every call.\n\n" +
    "And the rollback policy watches for the failure that actually hurts: " +
    "stuck-pause — a session that paused for a question and never resumed. " +
    "That's a browser frozen mid-sentence in front of a customer."
  );
  heading(s, "harness integration", "A demo script becomes shared infrastructure");

  const files = [
    ["walkthrough-agent-skill.yaml", "Worker Agent Skill: trigger phrases, four-phase instructions (targeting, planning, execution, interruption), RBAC, audit capture, derived allowlist, denied actions"],
    ["pipeline.yaml", "Build & Test → Register Skill → Deploy, with StageRollback on failure"],
    ["rollback-policy.yaml", "Rollback triggers, session version pinning, approval gates"],
  ];
  let y = 2.0;
  files.forEach(([f, d]) => {
    card(s, M, y, 12.1, 1.05, SURFACE);
    s.addText(f, {
      x: M + 0.32, y: y + 0.16, w: 4.3, h: 0.3,
      fontFace: MONO, fontSize: 12.5, bold: true, color: ACCENT, margin: 0,
    });
    s.addText(d, {
      x: M + 0.32, y: y + 0.5, w: 11.4, h: 0.5,
      fontFace: BODY_FONT, fontSize: 12.5, color: MUTED, lineSpacing: 17, margin: 0,
    });
    y += 1.18;
  });

  card(s, M, 5.6, 12.1, 1.15, ACCENT_DEEP);
  s.addText("The gate is the guarantee", {
    x: M + 0.32, y: 5.76, w: 4.5, h: 0.3,
    fontFace: BODY_FONT, fontSize: 14, bold: true, color: ACCENT, margin: 0,
  });
  s.addText(
    "CI blocks the deploy on the pause/resume suite, and the rollback policy watches for stuck-pause — a session " +
    "that paused for a question and never resumed. That is a browser frozen mid-sentence in front of a customer.",
    {
      x: M + 0.32, y: 6.08, w: 11.4, h: 0.55,
      fontFace: BODY_FONT, fontSize: 12.5, color: TEXT, lineSpacing: 17, margin: 0,
    }
  );
}

// --------------------------------------------------------------- 11. close

{
  const s = slide(
    "To close.\n\n" +
    "Three claims, and I've shown evidence for each: interruption handling is " +
    "the product and it's asserted by test; nothing about any site is compiled " +
    "in, demonstrated by running the same build against two products; and real " +
    "products break agents in ways unit tests don't catch.\n\n" +
    "Two things I want to be straight about. The 'yes, I'll sign in' branch has " +
    "unit coverage for its prompt mechanics but hasn't been through a real " +
    "interactive login — deliberately, because the agent has no way to do that " +
    "itself and shouldn't. And every live run so far has been driven by a " +
    "scripted WebSocket client; the UI is verified by screenshot and " +
    "type-check, not a full human click-through.\n\n" +
    "The bonus features are all in: voice narration that cancels the instant " +
    "someone interrupts, plan-changing interruptions, and workflow memory so " +
    "the second demo of the same product skips planning entirely.\n\n" +
    "Happy to run it live right now — it's locked to a two-minute YouTube demo, " +
    "one button, and it'll open Chrome itself. Thank you."
  );
  heading(s, "in closing", "Three claims, and what I can't yet claim");

  const claims = [
    ["Interruption is the product", "Gate checked between actions, not steps. Resume continues the same step — asserted by test, not by README."],
    ["Nothing is compiled in", "The plan is written against the page on screen. Same build: GitHub, YouTube, an internal tool."],
    ["Real products break agents", "Seven defects passed unit tests and failed live. All seven found by running it, not by reading it."],
  ];
  let x = M;
  claims.forEach(([t, d]) => {
    card(s, x, 1.95, 3.9, 1.85, SURFACE);
    s.addText(t, {
      x: x + 0.28, y: 2.18, w: 3.35, h: 0.62,
      fontFace: BODY_FONT, fontSize: 15, bold: true, color: ACCENT,
      lineSpacing: 20, margin: 0,
    });
    s.addText(d, {
      x: x + 0.28, y: 2.82, w: 3.35, h: 0.85,
      fontFace: BODY_FONT, fontSize: 12, color: MUTED, lineSpacing: 16, margin: 0,
    });
    x += 4.1;
  });

  card(s, M, 4.05, 5.95, 2.0, SURFACE_2);
  s.addText("What I can't claim yet", {
    x: M + 0.32, y: 4.25, w: 5.3, h: 0.3,
    fontFace: BODY_FONT, fontSize: 14, bold: true, color: TEXT, margin: 0,
  });
  s.addText(
    "The “yes, I'll sign in” branch has unit coverage but no real interactive login — by design, the agent " +
    "cannot do that itself. And live runs were driven by a scripted client; the UI is verified by screenshot " +
    "and type-check, not a full click-through.",
    {
      x: M + 0.32, y: 4.6, w: 5.35, h: 1.3,
      fontFace: BODY_FONT, fontSize: 12, color: MUTED, lineSpacing: 16, margin: 0,
    }
  );

  card(s, 6.85, 4.05, 5.85, 2.0, SURFACE_2);
  s.addText("Bonus features, delivered", {
    x: 7.17, y: 4.25, w: 5.2, h: 0.3,
    fontFace: BODY_FONT, fontSize: 14, bold: true, color: GREEN, margin: 0,
  });
  s.addText(
    "Voice narration (cancels the instant someone interrupts) · plan-changing interruptions (completed steps " +
    "preserved verbatim) · workflow memory (the second demo of the same product skips planning entirely).",
    {
      x: 7.17, y: 4.6, w: 5.25, h: 1.3,
      fontFace: BODY_FONT, fontSize: 12, color: MUTED, lineSpacing: 16, margin: 0,
    }
  );

  s.addText("Happy to run it live — one button, and it opens Chrome itself.", {
    x: M, y: 6.35, w: 12.1, h: 0.4,
    fontFace: TITLE_FONT, fontSize: 17, bold: true, color: TEXT, margin: 0,
  });
}

pres.writeFile({ fileName: OUT }).then(() => {
  console.log("wrote " + OUT);
});
