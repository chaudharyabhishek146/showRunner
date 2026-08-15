"""Generates the build report PDF for the Platform Walkthrough Agent.

Kept in the repo rather than a scratch directory so the document can be
regenerated when the project changes — a report you can't rebuild goes stale
the first time someone edits the code.

    python docs/build_report.py
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

OUT = pathlib.Path(__file__).resolve().parent / "platform-walkthrough-agent.pdf"

ACCENT = colors.HexColor("#E85D04")
INK = colors.HexColor("#14171F")
MUTED = colors.HexColor("#5C6473")
RULE = colors.HexColor("#D8DCE4")
CODE_BG = colors.HexColor("#F4F5F8")
GOOD = colors.HexColor("#1B7F4C")

PAGE_W, PAGE_H = A4
MARGIN = 20 * mm

styles = getSampleStyleSheet()


def _style(name: str, **kw) -> ParagraphStyle:
    kw.setdefault("parent", styles["Normal"])
    return ParagraphStyle(name, **kw)


BODY = _style(
    "Body", fontName="Helvetica", fontSize=9.6, leading=14.6,
    textColor=INK, spaceAfter=7, alignment=TA_LEFT,
)
LEAD = _style(
    "Lead", parent=BODY, fontSize=11, leading=16.6, textColor=colors.HexColor("#2B3040"),
    spaceAfter=10,
)
H1 = _style(
    "H1", fontName="Helvetica-Bold", fontSize=17, leading=21,
    textColor=INK, spaceBefore=2, spaceAfter=3,
)
H2 = _style(
    "H2", fontName="Helvetica-Bold", fontSize=12.5, leading=16,
    textColor=INK, spaceBefore=13, spaceAfter=5,
)
H3 = _style(
    "H3", fontName="Helvetica-Bold", fontSize=10, leading=13.5,
    textColor=ACCENT, spaceBefore=9, spaceAfter=3,
)
KICKER = _style(
    "Kicker", fontName="Helvetica-Bold", fontSize=7.8, leading=11,
    textColor=ACCENT, spaceAfter=3,
)
CODE = _style(
    "Code", fontName="Courier", fontSize=7.7, leading=10.6,
    textColor=colors.HexColor("#1E2430"), backColor=CODE_BG,
    # spaceBefore has to clear the descenders of the heading above: the tinted
    # background is drawn as a filled box and will otherwise sit on top of them.
    borderPadding=(7, 8, 7, 8), spaceBefore=10, spaceAfter=9, leftIndent=1,
)
CAPTION = _style(
    "Caption", fontName="Helvetica-Oblique", fontSize=8.2, leading=11.6,
    textColor=MUTED, spaceAfter=9,
)
CELL = _style("Cell", parent=BODY, fontSize=8.6, leading=12.2, spaceAfter=0)
CELL_B = _style("CellB", parent=CELL, fontName="Helvetica-Bold")
CELL_C = _style("CellC", parent=CELL, fontName="Courier", fontSize=7.8)


def para(text: str, style: ParagraphStyle = BODY) -> Paragraph:
    return Paragraph(text, style)


def code(text: str) -> XPreformatted:
    """A monospace block that keeps its indentation.

    XPreformatted rather than Paragraph: HTML collapses runs of spaces, which
    turns every aligned trace into a ragged one. Stick to ASCII in here — the
    built-in Courier has no box-drawing or arrow glyphs and renders them as
    solid black rectangles.
    """
    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return XPreformatted(escaped, CODE)


def bullets(items: list[str]) -> list:
    out = []
    for item in items:
        out.append(
            Paragraph(
                f'<bullet><font color="#E85D04">▪</font></bullet>&nbsp;{item}',
                ParagraphStyle("B", parent=BODY, leftIndent=11, bulletIndent=1,
                               spaceAfter=4.5),
            )
        )
    return out


def table(rows: list[list], widths: list[float], header: bool = True) -> Table:
    data = []
    for r, row in enumerate(rows):
        cells = []
        for c, cell in enumerate(row):
            if isinstance(cell, Paragraph):
                cells.append(cell)
            else:
                style = CELL_B if (header and r == 0) else CELL
                if not header and c == 0:
                    style = CELL_B
                cells.append(Paragraph(str(cell), style))
        data.append(cells)

    t = Table(data, colWidths=widths, hAlign="LEFT")
    style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, RULE),
    ]
    if header:
        style += [
            ("LINEBELOW", (0, 0), (-1, 0), 0.9, INK),
            ("TEXTCOLOR", (0, 0), (-1, 0), INK),
        ]
    t.setStyle(TableStyle(style))
    return t


# --------------------------------------------------------------- page frames


def cover_page(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(ACCENT)
    canvas.rect(0, PAGE_H - 12 * mm, PAGE_W, 12 * mm, stroke=0, fill=1)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 7.6)
    canvas.drawString(MARGIN, 12 * mm, "Platform Walkthrough Agent  ·  build report")
    canvas.restoreState()


def body_page(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(ACCENT)
    canvas.rect(0, PAGE_H - 4 * mm, PAGE_W, 4 * mm, stroke=0, fill=1)

    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 7.4)
    canvas.drawString(MARGIN, PAGE_H - 11 * mm, "PLATFORM WALKTHROUGH AGENT")
    canvas.drawRightString(PAGE_W - MARGIN, PAGE_H - 11 * mm, "BUILD REPORT")

    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.4)
    canvas.line(MARGIN, PAGE_H - 13.5 * mm, PAGE_W - MARGIN, PAGE_H - 13.5 * mm)
    canvas.line(MARGIN, 14 * mm, PAGE_W - MARGIN, 14 * mm)

    canvas.setFont("Helvetica", 7.6)
    canvas.drawRightString(PAGE_W - MARGIN, 10 * mm, str(canvas.getPageNumber()))
    canvas.restoreState()


def build() -> None:
    doc = BaseDocTemplate(
        str(OUT), pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN, bottomMargin=18 * mm,
        title="Platform Walkthrough Agent — build report",
        author="ShowRunner",
        subject="Design decisions, architecture, and verification evidence",
    )
    frame_cover = Frame(MARGIN, 18 * mm, PAGE_W - 2 * MARGIN,
                        PAGE_H - MARGIN - 18 * mm, id="cover")
    frame_body = Frame(MARGIN, 18 * mm, PAGE_W - 2 * MARGIN,
                       PAGE_H - 2 * MARGIN - 2 * mm, id="body")
    doc.addPageTemplates([
        PageTemplate(id="cover", frames=[frame_cover], onPage=cover_page),
        PageTemplate(id="body", frames=[frame_body], onPage=body_page),
    ])
    doc.build(story())


# -------------------------------------------------------------------- content


def story() -> list:
    s: list = []
    full = PAGE_W - 2 * MARGIN

    # ------------------------------------------------------------- cover
    s.append(Spacer(1, 30 * mm))
    s.append(para("HACKATHON BUILD REPORT", KICKER))
    s.append(para("Platform Walkthrough<br/>Agent", _style(
        "Cover", fontName="Helvetica-Bold", fontSize=31, leading=36, textColor=INK,
        spaceAfter=10)))
    s.append(para(
        "An agent that gives the product demo. It reads a product document, plans a "
        "walkthrough against the page that is actually on screen, drives the "
        "presenter's own signed-in Chrome while narrating, and — when someone "
        "interrupts — freezes mid-step, answers from the doc and the live screen, "
        "then resumes exactly where it stopped.", LEAD))
    s.append(Spacer(1, 5 * mm))

    s.append(table([
        ["Stack", "FastAPI · Playwright (CDP) · Claude Opus 5 · Next.js 15 / React 19"],
        ["Interface", "WebSocket event stream + REST setup surface"],
        ["Browser", "Attaches to the presenter's running Chrome — no credentials handled"],
        ["Tests", "25 hermetic (2.7s) + 1 real-browser integration test"],
        ["Verified", "Four full live runs against YouTube and GitHub with a real API key"],
    ], [30 * mm, full - 30 * mm], header=False))

    s.append(Spacer(1, 8 * mm))
    s.append(para("WHAT THIS DOCUMENT IS", KICKER))
    s.append(para(
        "The reasoning, not just the result. It records the three pivots the design "
        "went through, why each one was right, and the seven defects that only "
        "appeared when the thing was pointed at a real product. The verification "
        "section is deliberately specific: every claim in it comes from a run whose "
        "output is quoted.", BODY))

    # Bottom of the cover: the one-line version of each argument, so the page
    # carries the thesis on its own rather than trailing off into white space.
    s.append(Spacer(1, 26 * mm))
    s.append(para("THE THREE CLAIMS", KICKER))
    s.append(table([
        [para("Interruption is the product", CELL_B),
         para("The gate is checked between <i>actions</i>, not steps. Resume "
              "continues the same step — never rewinds, never skips. Asserted by "
              "test, not asserted by README.", CELL)],
        [para("Nothing about any site is compiled in", CELL_B),
         para("The plan is written against an accessibility outline of the page "
              "that is on screen. Same build, different document: GitHub, YouTube, "
              "or an internal tool.", CELL)],
        [para("Real products break agents", CELL_B),
         para("Seven defects passed unit tests and failed live — a CSP that "
              "killed the cursor, a locator that clicked a logo, a re-plan the "
              "loop skipped. Section 6 is the interesting part.", CELL)],
    ], [46 * mm, full - 46 * mm], header=False))

    s.append(NextPageTemplate("body"))
    s.append(PageBreak())

    # -------------------------------------------------------- 1. the problem
    s.append(para("1 · The problem, and the part that is actually hard", H1))
    s.append(para(
        "Anyone can script a browser. Recording a demo is a solved problem, and so is "
        "clicking through one yourself. The engineering that matters is what happens "
        "when a customer interrupts — because that is the entire difference between a "
        "demo and a screen recording.", LEAD))

    s.append(para("The interruption guarantee", H2))
    s.append(para("When a question arrives mid-step:", BODY))
    s.extend(bullets([
        "<b>The executor clears an <font face='Courier' size='8.6'>asyncio.Event</font>.</b> "
        "The loop parks at <font face='Courier' size='8.6'>await self._gate.wait()</font> — "
        "no polling, no busy-wait — and the gate is checked between <i>actions</i>, not "
        "just between steps, so the browser stops where it stands.",
        "<b>Claude answers</b> with the product document as cached context and the "
        "<i>current screenshot</i> attached, so the answer is grounded in what the "
        "customer is looking at rather than in what the plan said would be there.",
        "<b>The Event is set.</b> Execution continues at the same "
        "<font face='Courier' size='8.6'>current_index</font> — the pointer only advances "
        "after a step <i>fully</i> completes, so resume never rewinds and never skips.",
    ]))
    s.append(para(
        "That guarantee is a test, not a claim. "
        "<font face='Courier' size='8.6'>test_pause_freezes_and_resume_continues_same_step</font> "
        "asserts that across a pause no action is replayed and none is dropped.", BODY))

    s.append(para("Pause is not instantaneous, on purpose", H2))
    s.append(para(
        "A Playwright action already in flight runs to completion before the loop "
        "parks. Cancelling mid-action would leave a half-typed field on screen in "
        "front of the customer. Measured worst case is ~1.5s, and the UI is honest "
        "about it: the badge reads <b>PAUSING…</b> while the browser is still settling "
        "and only flips to <b>PAUSED</b> once it has actually stopped. The status the "
        "client requests and the status the executor reports are deliberately "
        "different events.", BODY))

    # ------------------------------------------------------- 2. three pivots
    s.append(para("2 · The thinking: three pivots", H1))
    s.append(para(
        "The design changed shape twice after the first working version. Both changes "
        "were driven by the same question — <i>what does this have to know in advance?</i> "
        "— and the answer kept being <i>less than it currently does</i>.", LEAD))

    s.append(para("Pivot 1 — from a scripted GitHub demo to a site-agnostic agent", H3))
    s.append(para(
        "The first build knew about GitHub. It had a <font face='Courier' size='8.6'>TARGET_URL</font>, "
        "a <font face='Courier' size='8.6'>DEMO_REPO</font>, and a session cookie pasted "
        "into the environment. It worked, and it was the wrong shape: every new product "
        "meant a code change, and the cookie meant the repo held a live credential.", BODY))
    s.append(para(
        "The replacement inverts the flow. The presenter uploads the product document "
        "at run time, says what to demo in plain English, and names one of their open "
        "browser tabs. The agent attaches to that tab, reads an accessibility outline "
        "of the page, and plans against <i>those</i> controls. Nothing about any site "
        "is compiled in — the same binary demos GitHub, YouTube, or an internal tool.", BODY))
    s.append(para(
        "The credential problem dissolved rather than being solved. Attaching to a "
        "browser the presenter is already signed into means there is no login code "
        "path to write, no cookie to store, and nothing for the agent to type.", BODY))

    s.append(para("Pivot 2 — the browser is the presenter's, not ours", H3))
    s.append(para(
        "Launching a clean automation window is easier and worse. It is signed out, it "
        "looks nothing like the product the audience uses, and the sterile "
        "\"Chrome is being controlled by automated software\" frame is the first thing "
        "on screen. Attaching over the DevTools protocol to a real, logged-in Chrome "
        "fixes all three at once — the audience watches the actual product, in the "
        "actual browser, with the presenter's actual account.", BODY))

    s.append(para("Pivot 3 — locking it down for the hackathon", H3))
    s.append(para(
        "For a judged run, choice is a liability: every input is something to "
        "fat-finger on stage. <font face='Courier' size='8.6'>DEMO_LOCKED=true</font> "
        "reduces the UI to one card and one button, and the <i>server</i> discards "
        "whatever the client posts and substitutes the preset — a stale browser tab "
        "cannot run something else.", BODY))
    s.append(para(
        "This was implemented as a preset over the general engine rather than by "
        "deleting the general path. <font face='Courier' size='8.6'>DEMO_LOCKED=false</font> "
        "restores the site-agnostic agent with no other change, so the answer to "
        "\"does this only do YouTube?\" is a live demonstration rather than an "
        "assurance.", BODY))


    # ------------------------------------------------------- 3. architecture
    s.append(para("3 · Architecture", H1))
    s.append(code(
        "  Next.js UI  ==WebSocket==>  FastAPI  ===>  StepExecutor  ===>  Playwright\n"
        "      |          + REST          |               |                   | CDP\n"
        "  setup panel               session state   asyncio.Event            v\n"
        "  chat + Q&A                                pause/resume     your own Chrome\n"
        "  live screenshot                 |                        (already signed in)\n"
        "  step progress             Claude (Opus 5)\n"
        "                    plan / narrate / answer / re-plan"))
    s.append(para(
        "The ordering is the design: <b>attach → pick the tab → read that page → "
        "plan</b>. Planning happens only after the agent can see the live DOM, which "
        "is what lets one prompt work on a site the code has never seen.", CAPTION))

    s.append(para("Modules", H2))
    s.append(table([
        ["File", "Responsibility"],
        ["agent/browser.py", "CDP attach, auto-launch, tab selection, semantic locators, "
                             "navigation scope enforcement"],
        ["agent/tabs.py", "Turns “the youtube one” into one specific open tab — or refuses. "
                          "Playwright-free so it is unit-testable in milliseconds"],
        ["agent/docs.py", "Uploaded md / txt / html / PDF / docx → text, content-addressed on disk"],
        ["agent/doc_parser.py", "Document + live page outline → executable StepPlan via structured outputs"],
        ["agent/narrator.py", "Pre-generates narration; answers live questions; classifies "
                              "question vs. redirect"],
        ["agent/step_executor.py", "The pause/resume loop, question breaks, mid-step re-planning"],
        ["agent/session.py", "Per-viewer orchestration: preset, sign-in gate, planning, interruptions"],
        ["agent/overlay.py", "On-page cursor, spotlight and caption drawn into the DOM"],
        ["agent/memory.py", "Workflow memory — recall a plan instead of re-planning"],
    ], [42 * mm, full - 42 * mm]))

    s.append(para("Why the overlay is drawn into the page", H2))
    s.append(para(
        "The OS mouse pointer is <i>not</i> composited into screenshots or into most "
        "screen-share capture paths. Without an overlay the audience watches buttons "
        "activate by themselves. So the agent injects its own cursor, glides it to each "
        "target, pulses on click, spotlights the element, and burns the current "
        "narration into the page as a caption bar — which also means the browser window "
        "is self-explanatory when it is shared <i>without</i> the app's chat panel.", BODY))

    s.append(para("The action vocabulary is closed", H2))
    s.append(para(
        "Claude chooses from six verbs — navigate, click, fill, press, wait, highlight — "
        "and addresses elements by ARIA role plus accessible name. It never emits a CSS "
        "selector or an XPath. Constraining the vocabulary is what makes an LLM-authored "
        "plan safely executable; products rewrite their class names constantly, but what "
        "a control <i>is</i> and what it is <i>called</i> survive a deploy.", BODY))


    # ----------------------------------------------------------- 4. decisions
    s.append(para("4 · Decisions worth defending", H1))

    s.append(para("Narration is pre-generated; answers are live", H3))
    s.append(para(
        "Every narration line comes back in one Claude call at plan time. Calling "
        "Claude between steps would make every transition visibly stall on a round "
        "trip. Only Q&A — where the customer is already waiting — happens live.", BODY))

    s.append(para("Answering and re-planning share one API call", H3))
    s.append(para(
        "“Can one issue live on two boards?” is a question. “Skip to the board” is a "
        "redirect. Deciding which is the same judgement as answering, so "
        "<font face='Courier' size='8.6'>QAResponse</font> returns "
        "<font face='Courier' size='8.6'>answer</font>, "
        "<font face='Courier' size='8.6'>wants_plan_change</font> and "
        "<font face='Courier' size='8.6'>requested_focus</font> together. A second "
        "classifier call would double the pause the customer sits through.", BODY))

    s.append(para("Scope is derived at run time and enforced in code", H3))
    s.append(para(
        "The navigation allowlist is the chosen tab's host plus its registrable domain "
        "— nothing broader. It is checked twice: once when sanitising the plan, and "
        "again immediately before <font face='Courier' size='8.6'>page.goto</font>. With "
        "no tab chosen the allowlist is empty and <i>everything</i> fails closed. The "
        "prompt asks; the code enforces. An LLM-authored plan is driving a browser "
        "signed into real accounts, so that check does not get to live in a prompt.", BODY))

    s.append(para("It refuses to guess which tab", H3))
    s.append(para(
        "Tab matching scores host equality, domain suffix, and title/path tokens, and "
        "returns nothing below a threshold — the UI then shows the tab list. Opening "
        "the wrong customer's tab on a screen share is far worse than one extra "
        "question. The one place guessing <i>is</i> allowed is a freshly launched empty "
        "browser, where there are no tabs to confuse and the alternative is a blank "
        "window.", BODY))

    s.append(para("It stops and asks", H3))
    s.append(para(
        "After every step the agent asks the room for questions and holds; at the end "
        "it holds a full minute. The window <i>restarts</i> whenever someone actually "
        "asks, because one question almost always has a follow-up. A question asked in "
        "the closing window can still extend the demo — the agent re-plans and performs "
        "the new thing rather than ending on an answer nobody saw.", BODY))

    s.append(para("There is always a plan", H3))
    s.append(para(
        "No API key, no network, a 500 from Claude — the agent falls back to a plan "
        "built from the document's own headings, with wait-only steps. It never invents "
        "navigation it cannot justify. A live demo must never open with a stack trace.", BODY))

    s.append(para("Length comes from the document", H3))
    s.append(para(
        "A document that says “about two minutes, plan exactly three steps” overrides "
        "the planner's default of four to six. The presenter who wrote down how long "
        "they have has already made that decision.", BODY))

    # --------------------------------------------------------- 5. safety
    s.append(para("5 · Safety model", H1))
    s.append(table([
        ["Concern", "How it is handled"],
        ["Credentials", "Never typed. Authentication comes from the attached browser "
                        "profile; there is no login-form code path and no stored cookie. "
                        "The only secret in the repo is ANTHROPIC_API_KEY."],
        ["Navigation", "Allowlist derived from the selected tab, enforced twice in code, "
                       "fails closed when empty."],
        ["Destructive actions", "The planner is instructed to prefer showing over "
                                "changing, and never to delete, send, publish, pay, or "
                                "alter account settings."],
        ["Signed-in state", "Detected before planning. A signed-out browser gets a plan "
                            "that points at where account features live instead of "
                            "clicking things it cannot complete."],
        ["The presenter's browser", "An attached browser is never closed on teardown — "
                                    "stop() disconnects. Auto-launch only ever fires for "
                                    "a CDP URL on this machine."],
    ], [34 * mm, full - 34 * mm]))


    # ------------------------------------------------------------- 6. bugs
    s.append(para("6 · Seven defects that only a real product surfaced", H1))
    s.append(para(
        "Every one of these passed unit tests and failed in front of a live page. They "
        "are the strongest argument in this report for testing an agent against the "
        "actual thing it will be pointed at.", LEAD))

    def bug(n: str, title: str, symptom: str, cause: str, fix: str) -> KeepTogether:
        return KeepTogether([
            para(f"{n} · {title}", H3),
            table([
                ["Symptom", symptom],
                ["Root cause", cause],
                ["Fix", fix],
            ], [24 * mm, full - 24 * mm], header=False),
            Spacer(1, 3.5 * mm),
        ])

    s.append(bug(
        "01", "Trusted Types killed the entire overlay",
        "On YouTube the cursor and caption never appeared. Spotlights worked, so it "
        "looked cosmetic and random.",
        "YouTube enforces a Trusted Types CSP. The cursor was built with "
        "<font face='Courier' size='8.6'>innerHTML</font>, which throws under that "
        "policy — taking the whole build function down with it, including the caption. "
        "Spotlights survived only because they are created per call.",
        "Build the SVG with <font face='Courier' size='8.6'>createElementNS</font> and "
        "wrap the builder in a try/catch, so a hostile page degrades the overlay "
        "instead of killing a step."))

    s.append(bug(
        "02", "Single-page apps silently dropped the overlay",
        "The cursor and captions vanished part-way through a demo and never returned.",
        "SPAs re-render <font face='Courier' size='8.6'>document.body</font> and take "
        "injected nodes with them. The builder trusted a boolean and refused to rebuild.",
        "Check <font face='Courier' size='8.6'>isConnected</font> instead, and restore "
        "the caption text and cursor position on rebuild so a mid-narration navigation "
        "is invisible."))

    s.append(bug(
        "03", "Substring name matching clicked the wrong element",
        "Every click meant for the sidebar “You” entry landed on the YouTube logo.",
        "Locators used substring matching, so <font face='Courier' size='8.6'>name=\"You\"</font> "
        "also matched “YouTube Home”, which sits earlier in the DOM. A union locator "
        "returns matches in <i>DOM order</i>, so the page chose, not us.",
        "Try exact names before substrings, in explicit passes, and only consider "
        "visible matches — apps keep duplicate markup for responsive layouts."))

    s.append(bug(
        "04", "A re-plan mid-step was skipped entirely",
        "“Show me how to filter the data” produced a tidy answer and no change on "
        "screen — the demo carried on as though nobody had spoken.",
        "The run loop holds the executing step in a local variable. Swapping the plan "
        "mid-step finished the <i>old</i> step and then advanced past the new one.",
        "A flag set by <font face='Courier' size='8.6'>replace_plan</font> breaks the "
        "action loop and re-enters <i>without advancing</i>, so the step now at that "
        "index runs. Pinned by a test that fails against the old code."))

    s.append(bug(
        "05", "The sign-in prompt deadlocked the WebSocket",
        "The connection died on its own keepalive the first time the agent asked a "
        "question with buttons.",
        "<font face='Courier' size='8.6'>start()</font> awaited the presenter's reply "
        "inline on the receive loop — the same loop that had to read that reply.",
        "Run it as a background task, with failures reported to the client rather than "
        "swallowed by the event loop."))

    s.append(bug(
        "06", "The search step typed into a button",
        "The search never ran. The trace still said <font face='Courier' size='8.6'>typed "
        "into 'Search'</font>, and the failure surfaced one step later as a missing "
        "filter control.",
        "YouTube's search field is <font face='Courier' size='8.6'>role=\"combobox\"</font>, "
        "not <font face='Courier' size='8.6'>textbox</font>. The role fallback chain "
        "reached the <i>Search button</i>; typing into a button raises nothing and does "
        "nothing.",
        "A fill now only ever considers editable roles, and verifies the resolved "
        "element is editable before typing — otherwise it reports the failure instead "
        "of claiming success."))

    s.append(bug(
        "07", "Chrome 136+ and 151+ both refuse the debug port",
        "<font face='Courier' size='8.6'>connect_over_cdp</font> failed against the "
        "presenter's stable Chrome with “Browser context management is not supported”.",
        "Chrome 136 refuses the debug port on the default profile; Chrome 151 rejects "
        "the CDP handshake without <font face='Courier' size='8.6'>--enable-automation</font>. "
        "Determined empirically by testing flags one at a time.",
        "All three flags are in the launch command the agent runs itself, and the app "
        "surfaces that exact command wherever attaching can fail."))


    # ----------------------------------------------------------- 7. evidence
    s.append(para("7 · Verification", H1))
    s.append(para(
        "Four full runs with a real API key against live products, plus the hermetic "
        "suite. Everything below is quoted from run output.", LEAD))

    s.append(para("Same build, two products, two documents", H2))
    s.append(code(
        "doc: \"Watch Later - product flow\"     tab: \"youtube\"   -> www.youtube.com\n"
        "  6 steps planned from the live page  6/6 executed, 0 failed actions\n"
        "  interrupt after step 2 -> pausing -> paused -> answered -> resumed at step 3\n"
        "  the answer: cross-device sync isn't in the doc, so it declined to guess\n"
        "\n"
        "doc: \"Explore - product flow\"         tab: \"github\"    -> github.com/explore\n"
        "  6 steps planned from the live page  in-scope hop to github.com/trending\n"
        "  interrupt: \"Can I filter Explore by language?\" -> answered from the page"))
    s.append(para(
        "The only difference between the two runs is the uploaded document, the "
        "sentence describing the flow, and the tab named.", CAPTION))

    s.append(para("An interruption redirecting the browser, not just the answer", H2))
    s.append(code(
        ">>> \"show me how to filter the results\"\n"
        " 33.0s [answer]  see the row of chips under the search box...\n"
        " 33.0s [status]  Re-planning around: filtering with the category chips\n"
        " 65.5s [step]    clicked 'Jet engines'   -> results reshape\n"
        " 88.4s [step]    typed a query, pressed Enter, results landed\n"
        "156.6s [complete]                          steps: [1,2,3] | errors: []"))

    s.append(para("The locked demo, ignoring hostile input", H2))
    s.append(code(
        "client posted:  doc_id=\"bogus\"  focus=\"something else entirely\"  tab=\"salesforce\"\n"
        "  0.9s  Demoing in: YouTube          <- the preset, not what the client sent\n"
        "  0.9s  [PROMPT] You're not signed in. Do you want to sign in first...?\n"
        "        -> \"No, continue signed out\"\n"
        " 18.2s  PLAN: 3. Open the sidebar and point at You :: click Guide,\n"
        "                    highlight You, highlight 'Sign in'\n"
        " 55.6s  [complete]"))
    s.append(para(
        "That last step is the signed-out constraint working: told the browser has no "
        "account, the planner pointed at where the saved queue lives and at the sign-in "
        "control, rather than planning a click it could not complete.", CAPTION))

    s.append(para("Attach, targeting, and scope", H2))
    s.append(code(
        "attached to 3 tabs\n"
        "match(\"the iana tab\") -> www.iana.org      match(\"salesforce\") -> None (refused)\n"
        "selected www.iana.org  scope: ['iana.org', 'www.iana.org']\n"
        "page_outline           31 controls read from a site the code has never seen\n"
        "navigation to https://evil.example/ -> \"skipped - outside this demo's scope\"\n"
        "Chrome still running after stop(): True    (attach disconnects, never closes)"))

    s.append(para("Pacing, measured", H2))
    s.append(table([
        ["Measurement", "Result"],
        ["Cold start: no browser → attached, on the product", "2.7 s"],
        ["Pause request → browser truly parked", "1.52 s (in-flight action finishing)"],
        ["Actions started after parked", "0"],
        ["Live frame stream", "3.4 fps sustained, ~39 KB per frame"],
        ["Two-minute demo, three steps with question breaks", "~87 s to complete"],
        ["Hermetic test suite", "25 passed in 2.7 s"],
    ], [78 * mm, full - 78 * mm]))

    s.append(para("What is not proven", H2))
    s.append(para(
        "Two things, stated plainly. The <i>yes, I'll sign in</i> branch of the sign-in "
        "gate has unit coverage for its prompt mechanics but has not been exercised "
        "through a real interactive login — the agent deliberately has no way to do "
        "that itself. And every live run so far has been driven by a scripted "
        "WebSocket client rather than a human clicking the UI; the UI has been verified "
        "by screenshot and type-check, not by a full click-through.", BODY))

    # ---------------------------------------------------------- 8. harness
    s.append(para("8 · Harness integration", H1))
    s.append(table([
        ["File", "What it does"],
        ["walkthrough-agent-skill.yaml", "Worker Agent Skill: trigger phrases, four-phase "
                                         "instructions (targeting, planning, execution, "
                                         "interruption), RBAC, audit capture, derived "
                                         "domain allowlist, denied actions"],
        ["pipeline.yaml", "Build &amp; Test → Register Skill → Deploy, with StageRollback "
                          "on failure"],
        ["rollback-policy.yaml", "Rollback triggers, session version pinning, approval gates"],
    ], [44 * mm, full - 44 * mm]))
    s.append(para(
        "Registering the walkthrough as an Agent Skill is what turns a demo script into "
        "shared infrastructure — versioned, governed, and callable from the catalog by "
        "any team. Sessions pin to the skill version they started on, so a deploy can "
        "never change the demo out from under a customer who is mid-call.", BODY))
    s.append(para(
        "The pipeline's real gate is the pause/resume suite. A walkthrough that rewinds "
        "when someone asks a question is worse than no demo at all, so that behaviour is "
        "verified on every commit rather than rehearsed before every call. The rollback "
        "policy watches for the failure that actually hurts — "
        "<font face='Courier' size='8.6'>stuck-pause</font>, a session that paused for a "
        "question and never resumed. That is a browser frozen mid-sentence in front of a "
        "customer.", BODY))

    # ------------------------------------------------------------ 9. running
    s.append(para("9 · Running it", H1))
    s.append(code(
        "cd backend && python3 -m venv .venv \\\n"
        "  && .venv/bin/pip install -r requirements.txt \\\n"
        "  && .venv/bin/playwright install chromium\n"
        "cp backend/.env.example backend/.env      # fill in ANTHROPIC_API_KEY\n"
        "cd backend && .venv/bin/uvicorn main:app --reload --port 8000\n"
        "cd frontend && npm install && npm run dev"))
    s.append(para(
        "Starting a walkthrough opens a debug-enabled Chrome on a dedicated profile if "
        "one is not already running — roughly three seconds, on the product named. Sign "
        "into that window once; the profile persists. Health check before a call: "
        "<font face='Courier' size='8.6'>claude_configured</font> and "
        "<font face='Courier' size='8.6'>chrome_reachable</font> must both be true, and "
        "<font face='Courier' size='8.6'>chrome_command</font> is the exact command to "
        "fix the second one by hand.", BODY))

    s.append(Spacer(1, 6 * mm))
    s.append(para(
        "<font color='#1B7F4C'><b>Bonus features delivered:</b></font> voice narration "
        "(Web Speech API, cancels the instant someone interrupts) · plan-changing "
        "interruptions (completed steps preserved verbatim, never replayed) · workflow "
        "memory (successful plans persist; the second demo of the same product skips "
        "planning entirely).", BODY))

    return s


if __name__ == "__main__":
    build()
    print(f"wrote {OUT} ({OUT.stat().st_size / 1024:.0f} KB)")
