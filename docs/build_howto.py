"""Generates the engineering document: how the agent is built.

Companion to build_report.py. That one argues the design and shows evidence;
this one is the implementation walkthrough someone would read before changing
the code.

    python docs/build_howto.py
"""

from __future__ import annotations

import pathlib

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    XPreformatted,
)

OUT = pathlib.Path(__file__).resolve().parent / "how-we-built-it.pdf"

ACCENT = colors.HexColor("#E85D04")
INK = colors.HexColor("#14171F")
MUTED = colors.HexColor("#5C6473")
RULE = colors.HexColor("#D8DCE4")
CODE_BG = colors.HexColor("#F4F5F8")

PAGE_W, PAGE_H = A4
MARGIN = 20 * mm

styles = getSampleStyleSheet()


def _style(name: str, **kw) -> ParagraphStyle:
    kw.setdefault("parent", styles["Normal"])
    return ParagraphStyle(name, **kw)


BODY = _style("Body", fontName="Helvetica", fontSize=9.6, leading=14.6,
              textColor=INK, spaceAfter=7, alignment=TA_LEFT)
LEAD = _style("Lead", parent=BODY, fontSize=11, leading=16.6,
              textColor=colors.HexColor("#2B3040"), spaceAfter=10)
H1 = _style("H1", fontName="Helvetica-Bold", fontSize=17, leading=21,
            textColor=INK, spaceBefore=4, spaceAfter=3, keepWithNext=1)
H2 = _style("H2", fontName="Helvetica-Bold", fontSize=12.5, leading=16,
            textColor=INK, spaceBefore=13, spaceAfter=5, keepWithNext=1)
H3 = _style("H3", fontName="Helvetica-Bold", fontSize=10, leading=13.5,
            textColor=ACCENT, spaceBefore=9, spaceAfter=3, keepWithNext=1)
KICKER = _style("Kicker", fontName="Helvetica-Bold", fontSize=7.8, leading=11,
                textColor=ACCENT, spaceAfter=3)
CODE = _style("Code", fontName="Courier", fontSize=7.6, leading=10.4,
              textColor=colors.HexColor("#1E2430"), backColor=CODE_BG,
              borderPadding=(7, 8, 7, 8), spaceBefore=10, spaceAfter=9, leftIndent=1)
CAPTION = _style("Caption", fontName="Helvetica-Oblique", fontSize=8.2,
                 leading=11.6, textColor=MUTED, spaceAfter=9)
CELL = _style("Cell", parent=BODY, fontSize=8.5, leading=12, spaceAfter=0)
CELL_B = _style("CellB", parent=CELL, fontName="Helvetica-Bold")
CELL_M = _style("CellM", parent=CELL, fontName="Courier", fontSize=7.7)


def para(text, style=BODY):
    return Paragraph(text, style)


def code(text: str) -> XPreformatted:
    """Monospace, whitespace preserved. ASCII only — Courier has no arrows."""
    esc = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return XPreformatted(esc, CODE)


def table(rows, widths, header=True, mono_first=False):
    data = []
    for r, row in enumerate(rows):
        cells = []
        for c, cell in enumerate(row):
            if isinstance(cell, Paragraph):
                cells.append(cell)
                continue
            if header and r == 0:
                style = CELL_B
            elif c == 0 and mono_first:
                style = CELL_M
            elif c == 0 and not header:
                style = CELL_B
            else:
                style = CELL
            cells.append(Paragraph(str(cell), style))
        data.append(cells)

    t = Table(data, colWidths=widths, hAlign="LEFT")
    s = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, RULE),
    ]
    if header:
        s.append(("LINEBELOW", (0, 0), (-1, 0), 0.9, INK))
    t.setStyle(TableStyle(s))
    return t


def cover_page(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(ACCENT)
    canvas.rect(0, PAGE_H - 12 * mm, PAGE_W, 12 * mm, stroke=0, fill=1)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 7.6)
    canvas.drawString(MARGIN, 12 * mm, "Platform Walkthrough Agent  ·  how it is built")
    canvas.restoreState()


def body_page(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(ACCENT)
    canvas.rect(0, PAGE_H - 4 * mm, PAGE_W, 4 * mm, stroke=0, fill=1)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 7.4)
    canvas.drawString(MARGIN, PAGE_H - 11 * mm, "PLATFORM WALKTHROUGH AGENT")
    canvas.drawRightString(PAGE_W - MARGIN, PAGE_H - 11 * mm, "HOW IT IS BUILT")
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.4)
    canvas.line(MARGIN, PAGE_H - 13.5 * mm, PAGE_W - MARGIN, PAGE_H - 13.5 * mm)
    canvas.line(MARGIN, 14 * mm, PAGE_W - MARGIN, 14 * mm)
    canvas.setFont("Helvetica", 7.6)
    canvas.drawRightString(PAGE_W - MARGIN, 10 * mm, str(canvas.getPageNumber()))
    canvas.restoreState()


def build():
    doc = BaseDocTemplate(
        str(OUT), pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN, topMargin=MARGIN, bottomMargin=18 * mm,
        title="Platform Walkthrough Agent — how it is built",
        author="ShowRunner",
        subject="Implementation walkthrough: modules, protocol, and control flow",
    )
    doc.addPageTemplates([
        PageTemplate(id="cover",
                     frames=[Frame(MARGIN, 18 * mm, PAGE_W - 2 * MARGIN,
                                   PAGE_H - MARGIN - 18 * mm, id="c")],
                     onPage=cover_page),
        PageTemplate(id="body",
                     frames=[Frame(MARGIN, 18 * mm, PAGE_W - 2 * MARGIN,
                                   PAGE_H - 2 * MARGIN - 2 * mm, id="b")],
                     onPage=body_page),
    ])
    doc.build(story())


def story():
    s = []
    full = PAGE_W - 2 * MARGIN

    # ------------------------------------------------------------------ cover
    s.append(Spacer(1, 32 * mm))
    s.append(para("ENGINEERING DOCUMENT", KICKER))
    s.append(para("How we built it", _style(
        "Cover", fontName="Helvetica-Bold", fontSize=34, leading=40,
        textColor=INK, spaceAfter=10)))
    s.append(para(
        "An implementation walkthrough of the Platform Walkthrough Agent: the "
        "modules, the wire protocol, the control flow of a single run, and the "
        "reasoning behind each piece. Written for whoever has to change this "
        "code next.", LEAD))

    s.append(Spacer(1, 6 * mm))
    s.append(table([
        ["Backend", "Python 3.14 · FastAPI · Playwright 1.62 · Anthropic SDK · 2,150 lines"],
        ["Frontend", "Next.js 15 · React 19 · TypeScript · 1,320 lines"],
        ["Model", "claude-opus-5 — structured outputs for planning and Q&amp;A, prompt caching for the document"],
        ["Browser", "Chrome over the DevTools Protocol, attached rather than launched"],
        ["Tests", "25 hermetic (2.7 s) + 1 real-browser integration test"],
        ["Deploy", "Harness Agent Skill + pipeline, with the test suite as the gate"],
    ], [26 * mm, full - 26 * mm], header=False))

    s.append(Spacer(1, 10 * mm))
    s.append(para("HOW TO READ THIS", KICKER))
    s.append(para(
        "Sections 1-3 are the shape of the system: the run lifecycle, the module "
        "layout, and the wire protocol. Sections 4-8 go one level down into the "
        "four parts that carry the weight — the browser layer, the planner, the "
        "executor, and the overlay. Section 9 onwards covers configuration, "
        "testing, and where to extend it.", BODY))

    s.append(NextPageTemplate("body"))
    s.append(PageBreak())

    # ------------------------------------------------------- 1. the lifecycle
    s.append(para("1 · The lifecycle of one run", H1))
    s.append(para(
        "Everything else in this document is a detail of this sequence. The "
        "ordering is load-bearing: planning happens <i>after</i> the agent can "
        "see the page, which is what makes the same code work on a product it "
        "has never been pointed at before.", LEAD))

    s.append(code(
        "  presenter clicks Start\n"
        "        |\n"
        "        v\n"
        "  1. resolve the request      DEMO_LOCKED ? the preset : what the client sent\n"
        "  2. resolve the document     upload id -> disk, or the bundled sample\n"
        "  3. ensure a browser         attach over CDP; auto-launch Chrome if the\n"
        "                              debug port is closed  (~2.7s cold)\n"
        "  4. select the tab           score open tabs against the hint, or refuse\n"
        "  5. derive the scope         host + registrable domain of that tab\n"
        "  6. offer the sign-in gate   ask, wait, then verify by reading the page\n"
        "  7. read the page            OUTLINE_JS -> roles + accessible names\n"
        "  8. plan                     doc + outline + scope -> StepPlan  (structured)\n"
        "  9. narrate                  one call fills every step's spoken line\n"
        " 10. execute                  the pause-gated loop, streaming events\n"
        "        |\n"
        "        +-- question? -> freeze, answer, maybe re-plan, resume\n"
        "        +-- step done? -> ask the room, hold, continue\n"
        "        v\n"
        " 11. closing question window, then complete"))

    s.append(para("Why steps 3-7 are in that order", H2))
    s.append(para(
        "A planner that runs before the browser is attached has to invent the "
        "page. Every version of this that shipped a hardcoded site did exactly "
        "that, and broke the first time the product's markup moved. Attaching "
        "first, then reading, then planning means the plan can only reference "
        "controls that were on screen a second ago.", BODY))
    s.append(para(
        "The sign-in gate sits at 6 rather than later for the same reason: "
        "signed-out and signed-in are different products, and a plan written "
        "for one is wrong for the other. Asking after planning would mean "
        "throwing the plan away.", BODY))

    # --------------------------------------------------------- 2. the modules
    s.append(para("2 · Module layout", H1))
    s.append(para(
        "Backend modules, with the line count as a rough weight. Two of them — "
        "<font face='Courier' size='8.6'>tabs.py</font> and "
        "<font face='Courier' size='8.6'>docs.py</font> — deliberately import no "
        "Playwright and no Anthropic SDK, so their tests run in milliseconds.",
        BODY))

    s.append(table([
        ["Module (backend/)", "Lines", "What it owns"],
        ["browser.py", "904", "CDP attach and auto-launch, tab discovery and selection, "
                                    "semantic element lookup, the six action verbs, navigation "
                                    "scope enforcement, screenshots and the live frame source"],
        ["session.py", "471", "Per-connection orchestration: the locked preset, the "
                                    "sign-in gate, planning, interruption handling, teardown"],
        ["step_executor.py", "332", "The run loop, the pause gate, question breaks, and "
                                          "mid-step plan replacement"],
        ["doc_parser.py", "255", "Document + page outline -> StepPlan; re-planning; the "
                                       "plan sanitiser; the no-API-key fallback"],
        ["narrator.py", "201", "Pre-generated narration and the mid-demo Q&amp;A call"],
        ["overlay.py", "188", "The injected cursor, spotlight and caption (browser JS)"],
        ["models.py", "171", "Pydantic contracts shared by every layer"],
        ["config.py", "162", "36 environment-backed settings, all with defaults"],
        ["docs.py", "155", "Upload extraction (md/txt/html/PDF/docx) and storage"],
        ["tabs.py", "127", "Hint -&gt; tab scoring, and the refusal threshold"],
        ["memory.py", "88", "Workflow memory: recall a plan instead of re-planning"],
        ["main.py", "339", "REST surface, the WebSocket loop, health and readiness"],
    ], [28 * mm, 12 * mm, full - 40 * mm], mono_first=True))

    s.append(para("The contracts in models.py", H2))
    s.append(para(
        "Everything crossing a boundary is a Pydantic model, which means the "
        "WebSocket layer, the planner and the frontend all agree by "
        "construction. <font face='Courier' size='8.6'>StepPlan</font> is also "
        "the structured-output schema handed to Claude, so the planner cannot "
        "return a shape the executor can't run.", BODY))
    s.append(code(
        "ActionType   navigate | click | fill | press | wait | highlight\n"
        "Action       type, target (accessible name or URL), role, value\n"
        "Step         id, title, goal, doc_reference, actions[], narration\n"
        "StepPlan     workflow_name, summary, steps[]        <- Claude's output schema\n"
        "TabInfo      index, title, url, host, active\n"
        "DemoRequest  doc_id, doc, focus, tab, workflow\n"
        "QAResponse   answer, wants_plan_change, requested_focus\n"
        "ClientEvent  start | question | pause | resume | skip | stop | list_tabs | reply\n"
        "ServerEvent  plan | step_start | narration | screenshot | frame | step_done |\n"
        "             answer | status | error | complete | tabs | prompt"))

    # -------------------------------------------------------- 3. the protocol
    s.append(para("3 · The wire protocol", H1))
    s.append(para(
        "Setup is REST; the demo itself is one WebSocket. The split exists "
        "because the tab picker and the document upload have to work on page "
        "load — before any session exists.", LEAD))

    s.append(para("REST", H2))
    s.append(table([
        ["Endpoint", "Purpose"],
        ["GET /ping", "Cheapest possible liveness hit, for the keep-alive cron"],
        ["GET /health", "Readiness: Claude configured, Chrome reachable, auto-launch "
                        "possible, and the exact command to fix Chrome by hand"],
        ["GET /tabs", "The presenter's open tabs; on failure, a hint plus the launch command"],
        ["GET /demo", "What this build runs, and whether the presenter may change it"],
        ["POST /document", "Multipart upload, 8 MB cap, returns a content-addressed id"],
        ["POST /document/text", "The same, for a pasted document"],
        ["GET /document/{id}", "What grounds the answers, so the UI can show it"],
        ["GET /samples", "Bundled example documents, one per .md in the samples directory"],
        ["GET /sample-doc", "One sample's text, by name"],
        ["GET /workflows", "Everything the agent has learned, for the resume picker"],
    ], [38 * mm, full - 38 * mm], mono_first=True))

    s.append(para("WebSocket", H2))
    s.append(para(
        "Inbound events are small and imperative. Outbound events are the "
        "render stream — the frontend is a fold over them and holds no other "
        "source of truth.", BODY))
    s.append(table([
        ["Outbound event", "Carries"],
        ["plan", "The full StepPlan, once planning completes"],
        ["step_start / step_done", "Step id and title; drives the progress rail"],
        ["narration", "The spoken line, pre-generated at plan time"],
        ["frame", "Live JPEG at ~4 fps — image only, so captions don't flicker"],
        ["screenshot", "Post-action PNG plus the trace line and the current URL"],
        ["answer", "A reply to a mid-demo question"],
        ["prompt", "A question <i>for</i> the presenter, with buttons (the sign-in gate)"],
        ["status", "Free text plus payload: the chosen tab, the scope, question windows"],
        ["complete / error", "Terminal states"],
    ], [38 * mm, full - 38 * mm], mono_first=True))

    s.append(para(
        "Two events are backgrounded rather than awaited on the receive loop: "
        "<font face='Courier' size='8.6'>question</font>, because Claude takes "
        "seconds and a second question must not queue behind the first; and "
        "<font face='Courier' size='8.6'>start</font>, because it blocks on the "
        "presenter answering the sign-in prompt — and that answer arrives on the "
        "same socket.", BODY))

    # ---------------------------------------------------------- 4. the browser
    s.append(para("4 · The browser layer", H1))

    s.append(para("Attaching instead of launching", H3))
    s.append(para(
        "<font face='Courier' size='8.6'>connect_over_cdp</font> joins the "
        "Chrome the presenter already has open. That single choice removes the "
        "credential problem — the session already exists in the profile — and "
        "puts the real product, with the real account, on the screen share. "
        "Teardown disconnects; it never closes a browser it did not open.", BODY))
    s.append(para(
        "Chrome needs three flags, and each one is a separate afternoon if you "
        "don't know it: <font face='Courier' size='8.6'>--remote-debugging-port</font> "
        "opens the endpoint, <font face='Courier' size='8.6'>--user-data-dir</font> "
        "is mandatory since Chrome 136 (which refuses the port on the default "
        "profile), and <font face='Courier' size='8.6'>--enable-automation</font> "
        "is mandatory since Chrome 151 (which otherwise rejects the handshake). "
        "If the port is closed when a demo starts, the agent runs that command "
        "itself — but only when the CDP URL points at this machine and Chrome is "
        "installed here.", BODY))

    s.append(para("Choosing the tab", H3))
    s.append(para(
        "<font face='Courier' size='8.6'>tabs.py</font> scores each open tab "
        "against the presenter's hint: host equality is worth 100, a domain "
        "suffix 80, a token inside the host 40, a token in the title 12, in the "
        "path 6, and being foreground is worth 1 — a tiebreak and nothing more. "
        "Below a threshold of 10 it returns nothing and the UI shows the tab "
        "list. Opening the wrong customer's tab on a screen share is far worse "
        "than one extra question.", BODY))

    s.append(para("Finding elements", H3))
    s.append(para(
        "Lookup is by ARIA role plus accessible name, never CSS. Two passes: "
        "exact names first, then substrings — because short labels are common in "
        "navigation and substring matching on them is actively wrong. Within "
        "each pass the requested role is tried first, then the roles that look "
        "identical to a human, then label, placeholder and text. Only visible "
        "matches count, since apps keep duplicate markup for responsive layouts. "
        "A <font face='Courier' size='8.6'>fill</font> narrows the candidates to "
        "editable roles only and verifies the element is editable before typing.",
        BODY))

    s.append(para("Scope enforcement", H3))
    s.append(code(
        "def _scope_for(url):            # derived when a tab is adopted\n"
        "    host = urlparse(url).hostname\n"
        "    base = registrable_domain(host)\n"
        "    return {host, base, *config.EXTRA_ALLOWED_HOSTS}\n"
        "\n"
        "# checked twice: once when sanitising the plan, and again here\n"
        "if not self.host_allowed(action.target):\n"
        "    return f\"skipped {action.target} - outside this demo's scope\""))
    s.append(para(
        "With no tab chosen the allowlist is empty and every navigation fails "
        "closed. The prompt asks for good behaviour; the code enforces it.",
        CAPTION))

    # ---------------------------------------------------------- 5. the planner
    s.append(para("5 · The planner", H1))
    s.append(para(
        "Three Claude calls per run, and each one is shaped by what it costs the "
        "audience.", LEAD))

    s.append(table([
        ["Call", "When", "Shape"],
        ["Plan", "Once, before execution", "messages.parse with StepPlan as the output "
                                           "format. Input: the document, the flow in plain "
                                           "English, the live page outline, the allowed hosts, "
                                           "and whether the browser is signed in"],
        ["Narrate", "Once, straight after planning", "One call fills every step's spoken line. "
                                                     "Calling per step would stall every "
                                                     "transition on a round trip"],
        ["Answer", "Per interruption, live", "messages.parse with QAResponse, the current "
                                             "screenshot attached as an image block"],
    ], [22 * mm, 34 * mm, full - 56 * mm]))

    s.append(para("Answering and re-planning are one call", H3))
    s.append(para(
        "\"Can one issue live on two boards?\" is a question. \"Skip to the "
        "board\" is a redirect. Deciding which is the same judgement as "
        "answering, so <font face='Courier' size='8.6'>QAResponse</font> carries "
        "the answer, a boolean, and the new focus together. A separate "
        "classifier call would double the pause the customer sits through.", BODY))

    s.append(para("The document is cached, not re-sent", H3))
    s.append(para(
        "The product document is identical across the planning, narration and "
        "every Q&amp;A call, so it goes in a system block marked "
        "<font face='Courier' size='8.6'>cache_control: ephemeral</font>. "
        "Subsequent calls read it from cache instead of paying for the tokens "
        "again.", BODY))

    s.append(para("The sanitiser, and the fallback", H3))
    s.append(para(
        "Whatever the model returns passes through "
        "<font face='Courier' size='8.6'>_sanitise()</font>, which drops any "
        "navigation outside the derived scope before the plan reaches the "
        "executor. And with no API key — or a 500, or no network — "
        "<font face='Courier' size='8.6'>_fallback_plan()</font> builds steps "
        "from the document's own headings with wait-only actions. It never "
        "invents navigation. A live demo must not open with a stack trace.", BODY))

    # --------------------------------------------------------- 6. the executor
    s.append(para("6 · The executor", H1))
    s.append(para(
        "The smallest module that carries the most weight. It owns one "
        "<font face='Courier' size='8.6'>asyncio.Event</font> and the rule that "
        "makes interruption safe.", LEAD))

    s.append(code(
        "while self.current_index < len(self.plan.steps):\n"
        "    if not await self._checkpoint():      # parks on the gate\n"
        "        break\n"
        "    step = self.plan.steps[self.current_index]\n"
        "\n"
        "    emit(step_start); emit(narration); browser.set_caption(...)\n"
        "\n"
        "    for action in step.actions:\n"
        "        if not await self._checkpoint(): break   # gate between ACTIONS\n"
        "        if self._plan_replaced:          break   # redirected mid-step\n"
        "        if self._skip_requested:         break\n"
        "        trace = await browser.run_action(action)\n"
        "        emit(screenshot with trace)\n"
        "\n"
        "    if self._plan_replaced:\n"
        "        continue          # re-read this index; do NOT advance past it\n"
        "\n"
        "    emit(step_done)\n"
        "    self.current_index += 1        # only after the step fully completes\n"
        "    await question_break(...)      # ask the room, hold, maybe re-plan"))

    s.append(para("The three rules", H2))
    s.append(table([
        ["The gate is an Event, not a flag", "A flag forces the loop to poll — which either "
                                             "burns CPU or adds latency to every resume. The "
                                             "Event lets the coroutine park and wake the instant "
                                             "an answer lands."],
        ["It is checked between actions", "Not just between steps. That is why an interruption "
                                          "freezes the browser where it stands rather than at "
                                          "the next step boundary."],
        ["The index advances last", "<font face='Courier' size='8.6'>current_index</font> moves "
                                    "only after a step fully completes, so resuming continues "
                                    "the same step — it never rewinds and never skips."],
    ], [40 * mm, full - 40 * mm], header=False))

    s.append(para("Question breaks", H3))
    s.append(para(
        "After each step the executor asks the room and holds for "
        "<font face='Courier' size='8.6'>QUESTION_BREAK_SECONDS</font>; at the "
        "end it holds for a full minute. The window <i>restarts</i> whenever "
        "someone actually asks, because one question usually has a follow-up. "
        "Skip ends it early. A question asked in the closing window can still "
        "extend the demo: the outer loop re-enters if re-planning added steps, "
        "so the agent performs the new thing rather than ending on an answer "
        "nobody saw.", BODY))

    s.append(para("Pause is not instantaneous, deliberately", H3))
    s.append(para(
        "An action already in flight runs to completion before the loop parks — "
        "cancelling mid-action would leave a half-typed field on screen in front "
        "of the customer. Measured worst case is 1.52 s. The UI is honest about "
        "the gap: the client's request emits "
        "<font face='Courier' size='8.6'>pausing</font>, and only the executor "
        "emits the authoritative <font face='Courier' size='8.6'>paused</font>.",
        BODY))

    # ---------------------------------------------------------- 7. the overlay
    s.append(para("7 · The on-page overlay", H1))
    s.append(para(
        "The OS mouse pointer is not composited into screenshots or into most "
        "screen-share capture paths. Without an overlay the audience watches "
        "buttons activate by themselves, which reads as a glitch rather than as "
        "a demo. So the agent draws its own.", LEAD))

    s.append(table([
        ["Cursor", "An SVG arrow injected into the page, moved with a CSS transform so it "
                   "glides to each target over ~0.6 s rather than teleporting"],
        ["Click pulse", "A ring that expands and fades on click, so activation has a cause"],
        ["Spotlight", "A box around the target with a large outer box-shadow that dims the "
                      "rest of the page. Kept light — heavier and the product looks washed out"],
        ["Caption", "The current narration as a subtitle bar, which makes the browser window "
                    "self-explanatory when it is shared without the app's chat panel"],
    ], [26 * mm, full - 26 * mm], header=False))

    s.append(para("Two constraints it has to survive", H2))
    s.append(para(
        "Real products are hostile to injected DOM in two specific ways, and the "
        "overlay is built around both. <b>Trusted Types:</b> sites with that CSP "
        "throw on any HTML-string assignment, so every node is created with "
        "<font face='Courier' size='8.6'>createElementNS</font> and "
        "<font face='Courier' size='8.6'>textContent</font>, never "
        "<font face='Courier' size='8.6'>innerHTML</font>, and the whole builder "
        "is wrapped so a refusal degrades the overlay instead of killing a step. "
        "<b>Single-page re-renders:</b> the builder checks "
        "<font face='Courier' size='8.6'>isConnected</font> rather than a "
        "boolean, and restores the caption text and cursor position when it "
        "rebuilds — so an in-app navigation mid-narration is invisible.", BODY))

    # ------------------------------------------------------- 8. the frontend
    s.append(para("8 · The frontend", H1))
    s.append(para(
        "One hook owns the socket and folds the event stream into render state. "
        "Components are presentational — no component opens a connection, and "
        "there is no second source of truth to drift.", LEAD))

    s.append(table([
        ["lib/websocket.ts", "389", "The socket, the event fold, and every action the UI can "
                                    "take (start, ask, pause, resume, skip, stop, reply)"],
        ["components/SetupPanel.tsx", "280", "Document upload/paste, the flow description, the "
                                             "tab picker — or, in locked mode, one card and one "
                                             "button"],
        ["app/page.tsx", "170", "Layout, the question-window countdown, and the prompt bar"],
        ["components/ChatPanel.tsx", "110", "Narration and answers as they arrive, plus the "
                                            "interrupt box"],
        ["lib/types.ts", "102", "Mirrors models.py — kept in sync by hand, deliberately small"],
        ["components/BrowserPanel.tsx", "70", "The live view: JPEG frames, then a full-quality "
                                              "PNG after each action"],
        ["lib/voice.ts", "49", "Web Speech API narration; cancels the instant someone interrupts"],
    ], [40 * mm, 12 * mm, full - 52 * mm], header=False, mono_first=True))

    s.append(para(
        "The live view is two streams on purpose. Continuous JPEG frames at ~4 "
        "fps make page loads, scrolls and hovers visible — without them the "
        "panel is a slideshow of end states. The post-action PNG is "
        "full-quality and carries the trace line and URL. The frame handler "
        "deliberately touches only the image: folding the caption in there would "
        "make it flicker several times a second.", BODY))

    # --------------------------------------------------------------- 9. config
    s.append(para("9 · Configuration", H1))
    s.append(para(
        "36 settings, every one with a working default, so a clean checkout runs "
        "with only <font face='Courier' size='8.6'>ANTHROPIC_API_KEY</font> set. "
        "The ones that change behaviour rather than taste:", BODY))

    s.append(table([
        ["Setting", "Default", "Effect"],
        ["DEMO_LOCKED", "true", "Runs one fixed preset and ignores what the client sends. "
                                "false restores the site-agnostic agent"],
        ["ATTACH_TO_CHROME", "true", "Join the presenter's Chrome rather than launching a "
                                     "clean profile"],
        ["AUTO_LAUNCH_CHROME", "true", "Start Chrome with the debug flags when the port is "
                                       "closed — local machine only"],
        ["ASK_TO_SIGN_IN", "true", "Offer to wait for a sign-in before planning"],
        ["EXTRA_ALLOWED_HOSTS", "(empty)", "Standing additions to the derived navigation scope"],
        ["QUESTION_BREAK_SECONDS", "12", "Hold after each step. 0 runs straight through"],
        ["CLOSING_QUESTION_SECONDS", "60", "The hold at the end, where questions actually arrive"],
        ["STEP_DWELL_SECONDS", "3", "Pacing between steps so narration can be read"],
        ["LIVE_FPS / FRAME_QUALITY", "4 / 62", "~39 KB per frame — continuous without "
                                               "saturating a conference-room connection"],
        ["SHOW_CURSOR / SHOW_CAPTIONS", "true", "The on-page overlay"],
    ], [40 * mm, 18 * mm, full - 58 * mm], mono_first=True))

    # -------------------------------------------------------------- 10. tests
    s.append(para("10 · How it is tested", H1))
    s.append(para(
        "25 hermetic tests in 2.7 seconds: no network, no Claude calls, no "
        "browser. A <font face='Courier' size='8.6'>FakeBrowser</font> records "
        "actions instead of performing them, and an autouse fixture zeroes the "
        "pacing — in a meeting the dwell and question windows are the feature, "
        "in CI they would be a minute of dead air per test.", BODY))

    s.append(table([
        ["The pause guarantee", "Asserts that across a pause no action is replayed and none "
                                "is dropped, and that the index lands on the same step"],
        ["Mid-step re-planning", "Asserts that a plan swapped in mid-step runs the new step "
                                 "rather than advancing past it"],
        ["Question breaks", "Counts the prompts, checks the closing one holds, and that a "
                            "question at the end can extend the demo"],
        ["Scope enforcement", "The sanitiser drops out-of-scope navigation, and an empty "
                              "allowlist allows nothing"],
        ["Tab matching", "Names the right product, defaults sensibly, and refuses below "
                         "the threshold"],
        ["Fill targeting", "A fill never resolves to a non-editable element"],
        ["Document handling", "html/docx/text extraction, and content-addressed storage "
                              "surviving a restart"],
        ["Integration (marked)", "Real browser: opens a page, derives scope, blocks an "
                                 "out-of-scope navigation, reads the outline, screenshots"],
    ], [36 * mm, full - 36 * mm], header=False))

    s.append(para(
        "The integration test switches attaching <i>off</i> and runs headless on "
        "purpose — a test must never open tabs in the developer's own Chrome.",
        CAPTION))

    # ------------------------------------------------------------- 11. harness
    s.append(para("11 · Deployment", H1))
    s.append(table([
        ["walkthrough-agent-skill.yaml", "Worker Agent Skill: trigger phrases, four-phase "
                                         "instructions (targeting, planning, execution, "
                                         "interruption), RBAC, audit capture, a derived domain "
                                         "allowlist, and denied actions. One secret: the API key"],
        ["pipeline.yaml", "Build &amp; Test -&gt; Register Skill -&gt; Deploy, with StageRollback "
                          "on failure. The browser smoke test reports but does not block"],
        ["rollback-policy.yaml", "Rollback triggers, session version pinning, approval gates"],
        [".github/workflows/keep-alive.yml", "Pings /ping every two minutes so a free-tier host "
                                             "does not sleep between demos"],
    ], [44 * mm, full - 44 * mm], header=False, mono_first=True))

    s.append(para(
        "Sessions pin to the skill version they started on, so a deploy cannot "
        "change the demo out from under a customer who is mid-call. The "
        "pipeline's real gate is the pause/resume suite, and the rollback policy "
        "watches for <font face='Courier' size='8.6'>stuck-pause</font> — a "
        "session that paused for a question and never resumed.", BODY))

    # ------------------------------------------------------------ 12. extending
    s.append(para("12 · Where to extend it", H1))
    s.append(table([
        ["A new action verb", "Add it to <font face='Courier' size='8.6'>ActionType</font>, "
                              "handle it in <font face='Courier' size='8.6'>run_action</font>, "
                              "and describe it in the planner preamble's vocabulary list. The "
                              "enum is the contract — the model can only pick from it"],
        ["A new document format", "One branch in <font face='Courier' size='8.6'>docs.extract_text</font>. "
                                  "Anything unrecognised already falls back to text"],
        ["A different browser", "<font face='Courier' size='8.6'>BROWSER_CHANNEL</font> covers "
                                "Edge and bundled Chromium for the launch path; the attach path "
                                "needs any CDP endpoint"],
        ["Another sample demo", "Drop a .md in <font face='Courier' size='8.6'>backend/data/samples/</font>. "
                                "It becomes a button, titled from its H1. A doc that states a "
                                "length or step count overrides the planner's default"],
        ["A different Q&amp;A policy", "<font face='Courier' size='8.6'>QA_PREAMBLE</font> in "
                                       "narrator.py decides what counts as a question versus a "
                                       "redirect — that boundary is prompt, not code"],
    ], [34 * mm, full - 34 * mm], header=False))

    s.append(para("Running it", H2))
    s.append(code(
        "cd backend && python3 -m venv .venv \\\n"
        "  && .venv/bin/pip install -r requirements.txt \\\n"
        "  && .venv/bin/playwright install chromium\n"
        "cp backend/.env.example backend/.env         # fill in ANTHROPIC_API_KEY\n"
        "cd backend  && .venv/bin/uvicorn main:app --reload --port 8000\n"
        "cd frontend && npm install && npm run dev\n"
        "\n"
        "cd backend && .venv/bin/python -m pytest -q -m \"not integration\""))
    s.append(para(
        "Starting a walkthrough opens a debug-enabled Chrome on a dedicated "
        "profile if one is not already running. Sign into that window once; the "
        "profile persists, so later demos skip straight past it.", BODY))

    return s


if __name__ == "__main__":
    build()
    print(f"wrote {OUT} ({OUT.stat().st_size / 1024:.0f} KB)")
