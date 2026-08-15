# Platform Walkthrough Agent

An agent that gives the product demo. You upload the product document, say what
to demo, and point it at one of your open Chrome tabs. It reads the live page,
plans a walkthrough, drives **your own signed-in browser** through the real
product while narrating in natural language — and when the customer interrupts
with a question, it freezes mid-step, answers using the doc and the current
screen, then resumes from exactly where it stopped.

Nothing about the target is configured ahead of time. There is no target URL, no
repo, and no stored session in this codebase: GitHub, YouTube, or an internal
tool are the same run with different inputs.

Built for FlytBase GTM Hackathon — Problem #4.

---

## The hard part

Anyone can script a browser. The engineering that matters here is the
**interruption handler**, because that is the difference between a demo and a
screen recording.

When a question arrives:

1. `StepExecutor` clears an `asyncio.Event`. The loop parks at
   `await self._gate.wait()` — no polling, no busy-wait, and the browser stops
   between *actions*, not just between steps.
2. Claude answers with the product doc as cached context and the **current
   screenshot** attached, so the answer is grounded in what the customer is
   actually looking at.
3. The Event is set. Execution continues at the same `current_index` — the
   pointer only advances after a step *fully completes*, so resume never
   rewinds and never skips.

That guarantee is a test, not a claim: `test_pause_freezes_and_resume_continues_same_step`
asserts that no action is replayed and none is dropped across a pause.

---

## Architecture

```
Next.js UI  ──WebSocket──▶  FastAPI  ──▶  StepExecutor  ──▶  Playwright
   │            + REST          │              │                  │ CDP
 setup panel              session state   asyncio.Event            ▼
 chat + Q&A                                pause/resume     your own Chrome
 live screenshot                                │           (already signed in)
 step progress                            Claude (Opus 5)
                                    plan · narrate · answer · re-plan
```

The order is the design: **attach → pick the tab → read that page → plan.**
Planning happens after the agent can see the live DOM, which is what lets one
prompt work on a site the code has never seen.

| Module | Responsibility |
| --- | --- |
| [`agent/tabs.py`](backend/agent/tabs.py) | "the youtube one" → one specific open tab (or an honest refusal) |
| [`agent/docs.py`](backend/agent/docs.py) | Uploaded md/txt/html/PDF/docx → text, content-addressed |
| [`agent/doc_parser.py`](backend/agent/doc_parser.py) | Product doc + live page outline → executable `StepPlan` |
| [`agent/narrator.py`](backend/agent/narrator.py) | Pre-generates narration; answers live questions |
| [`agent/browser.py`](backend/agent/browser.py) | CDP attach, tab selection, semantic (`getByRole`) selectors |
| [`agent/step_executor.py`](backend/agent/step_executor.py) | The pause/resume loop |
| [`agent/session.py`](backend/agent/session.py) | Ties it together per viewer |
| [`agent/memory.py`](backend/agent/memory.py) | Workflow memory — recall a plan instead of re-planning |

---

## Design decisions worth defending

**Narration is pre-generated, answers are live.** All five narration lines come
back in one Claude call at plan time. If we called Claude between steps, every
transition would visibly stall on a round trip. Only Q&A — where the customer
is already waiting — happens live.

**Answering and re-planning share one API call.** "Can one issue live on two
boards?" is a question; "skip to the board" is a redirect. Deciding which is the
same judgement as answering, so `QAResponse` returns `answer`,
`wants_plan_change`, and `requested_focus` together. A second classifier call
would double the pause the customer sits through.

**Semantic selectors, with a fallback chain.** Products rewrite their CSS
constantly; ARIA roles and visible names survive. The action vocabulary is a
closed enum, so Claude picks from a fixed set and never invents a selector. And
because a plausible-but-wrong role is the common LLM slip — "New issue" is an
`<a>`, not a `<button>` — `_locate()` `.or_()`s across button/link/menuitem/tab
before falling back to label, placeholder, and text.

**The allowlist is derived at run time, and enforced in code.** Scope is the
chosen tab's host plus its registrable domain — nothing broader. It is checked
twice: `_sanitise()` strips out-of-scope navigation from the plan, and
`run_action` checks again immediately before `page.goto`. With no tab chosen the
allowlist is empty and every navigation fails closed. The prompt asks; the code
enforces. An LLM-authored plan is driving a browser that is signed into real
accounts, so that check does not get to live in a prompt.

**It refuses to guess the tab.** `match_tab` scores host equality, domain
suffix, and title/path tokens, and returns nothing below the threshold — the UI
then shows the tab list. Opening the wrong customer's tab on a screen share is
far worse than one extra question.

**Locked for the hackathon, general underneath.** `DEMO_LOCKED=true` (the
default) means the UI has no document, no flow and no tab to choose: one Start
button, the same YouTube demo every time, and nothing to fat-finger on stage.
The server ignores whatever the client posts and substitutes the preset, so a
stale browser tab can't run something else. `DEMO_LOCKED=false` gives the
site-agnostic agent back — the engine is identical either way.

**It offers to wait while you sign in.** Signed-out and signed-in YouTube are
different products, so before *anything is planned* the agent asks. Say yes and
it holds until you click "I'm signed in", then checks the page rather than
taking your word for it. Say no and it says so out loud and plans only what a
visitor can do. The agent never types a credential — it waits, and looks.

**It stops and asks.** After every step the agent asks the room for questions
and holds for `QUESTION_BREAK_SECONDS`, then holds a full minute at the end. The
window *restarts* every time someone actually asks, because one question almost
always has a follow-up and cutting that off is worse than being slow — and a
question asked in the closing window can still extend the demo, re-planning and
performing the new thing rather than ending on an answer nobody saw. Skip ends a
window early when the room is quiet, and the button relabels itself to
**Carry on** so it's clear that's what it does.

**Length comes from the document.** A doc that says "about two minutes, plan
exactly three steps" overrides the planner's default of 4-6. The presenter who
wrote down how long they have has already made that call —
[`youtube-2-minute.md`](backend/data/samples/youtube-2-minute.md) is the sample
that does it.

**There is always a plan.** No API key, no network, a 500 from Claude — the
agent falls back to a plan built from the document's own headings, with
wait-only steps. It never invents navigation it cannot justify. A live demo must
never open with a stack trace.

**Credentials are never typed.** Authentication comes from the Chrome you are
already signed into. There is no login-form code path, no stored cookie, and no
product secret anywhere in this repo — the only secret is `ANTHROPIC_API_KEY`.

---

## Running it

```bash
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/playwright install chromium
```

```bash
cp backend/.env.example backend/.env
```

Fill in `ANTHROPIC_API_KEY`. That is the only required value — there is nothing
to configure about the product you are demoing.

The agent needs a Chrome with the debug port open, and **starting a walkthrough
opens one for you** if there isn't one already — it launches on a dedicated
profile, on the product you named, and attaches in about three seconds. Sign
into that window once; the profile persists, so later demos skip straight past
it.

To start it yourself instead (or if the agent can't find Chrome):

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --remote-debugging-port=9222 --user-data-dir="$HOME/chrome-demo-profile" --enable-automation
```

All three flags are load-bearing: Chrome 136+ refuses the debug port on the
default profile, and Chrome 151+ rejects the CDP handshake without
`--enable-automation`. Because the profile is a separate one, this runs happily
alongside the Chrome you already have open — no need to quit it.

Auto-launch is deliberately narrow. It only fires on the *start a demo* action,
never on a page load or a health check, and only when the CDP URL points at this
machine and Chrome is installed on it — a deployed backend has no business
opening a browser on the server, and `can_auto_launch()` says so out loud.

```bash
cd backend && .venv/bin/uvicorn main:app --reload --port 8000
```

```bash
cd frontend && npm install && npm run dev
```

Open http://localhost:3000. Upload the product document, type what to demo
("how a viewer builds a playlist"), pick the tab, and hit **Start walkthrough**.

### Tests

```bash
cd backend && .venv/bin/python -m pytest -q -m "not integration"
```

15 hermetic tests — no network, no Claude calls, no browser. The `integration`
marker runs the real-browser smoke test, which launches its own clean profile
rather than touching your Chrome.

---

## Running it in a live meeting

The agent navigates itself — nobody clicks anything. You have two ways to share:

- **Share the app's own window.** The right-hand panel is a live 4 fps stream of
  the browser, so page loads, scrolls, and hovers are visible, not just the
  state after each action — and the narration sits next to it.
- **Share the Chrome window directly.** Because the agent draws its own cursor,
  spotlight, and caption bar *into the page*, the browser view is
  self-explanatory on its own. (The OS pointer is not composited into
  screenshots, which is exactly why the overlay is drawn in the DOM.)

Before the call:

```bash
curl -s localhost:8000/health
```

On a free-tier host the backend sleeps after ~15 minutes idle, and the cold
start is 30-60 seconds — in a live call, that is the customer watching a blank
panel. [`keep-alive.yml`](.github/workflows/keep-alive.yml) pings `/ping` every
two minutes to prevent it; set the repo variable `BACKEND_URL` to the deployed
URL (Settings → Secrets and variables → Actions → Variables) and it starts
working. The open app pings the same endpoint, so the tab you already have open
keeps the service warm too.

`claude_configured` and `chrome_reachable` must both be `true`. If
`chrome_reachable` is false, `chrome_command` is the exact command to restart
Chrome with. If `claude_configured` is false the demo still runs, but on the
document-derived fallback plan with placeholder narration and no live Q&A.

**Pause is not instantaneous, by design.** A Playwright action already in flight
runs to completion before the loop parks at the gate — cancelling mid-action
would leave a half-typed field on screen in front of the customer. Measured
worst case is ~1.5s. The UI is honest about it: the badge reads **PAUSING…**
while the browser is still settling and only flips to **PAUSED** once it has
actually stopped.

## Verified end to end

**Attach and targeting**, against a real stable Chrome 151 (throwaway profile on
port 9223, three tabs open, none of them ever seen by this code):

```
attached to 3 tabs
match("the iana tab")  -> www.iana.org        match("salesforce") -> None  (refused)
selected www.iana.org  scope: ['iana.org', 'www.iana.org']
page_outline           31 controls read from a site the code has never seen
highlight w/ wrong role 'button' on a link -> found via the .or_() chain
navigation to https://evil.example/ -> "skipped — outside this demo's scope"
Chrome still running after stop(): True      (attach disconnects, never closes)
```

The rendered screenshot was checked visually: drawn cursor on the target, the
spotlight ring, and the caption bar all composited into the page.

**Two full demos, one build, two products.** Same server, same code, real
Claude, driving a real Chrome over CDP. The only difference between the runs is
the uploaded document, the sentence describing the flow, and the tab named:

```
doc: "Watch Later — product flow"     tab: "youtube"   -> www.youtube.com
  6 steps planned from the live page  6/6 executed, 0 failed actions
  interrupt after step 2 -> pausing -> paused -> answered -> resumed at step 3
  the answer: cross-device sync isn't in the doc, so it declined to guess
  117 live frames, 16 stills, [complete]

doc: "Explore — product flow"         tab: "github"    -> github.com/explore
  6 steps planned from the live page  in-scope hop to github.com/trending
  interrupt: "Can I filter Explore by language?" -> answered from the page
  173 live frames, 18 stills, [complete]
```

**The locked demo, signed out**, from a client that deliberately posted junk
(`doc_id: "bogus"`, `focus: "something else entirely"`, `tab: "salesforce"`):

```
  0.9s  Demoing in: YouTube            <- the preset, not what the client sent
  0.9s  [PROMPT] You're not signed in. Do you want to sign in first…?
        -> "No, continue signed out"
 18.2s  PLAN: YouTube in two minutes: feed, search, and the saved queue
        3. Open the sidebar and point at You :: click Guide, highlight You,
                                                highlight 'Sign in'
 55.6s  [complete]
```

That last step is the constraint working: told the browser is signed out, the
planner pointed at where the saved queue lives and at the Sign in control,
instead of planning a click it could not complete.

Finding it also surfaced a deadlock worth naming: `start()` now blocks on the
presenter's answer, and that answer arrives on the same WebSocket — awaited
inline, the socket stopped reading and died on its own keepalive. It runs as a
background task now, with failures reported to the client rather than swallowed.

**The two-minute doc, with question breaks**, timed from the live run
(`CLOSING_QUESTION_SECONDS=20` for the rehearsal; the default is 60):

```
 14.7s  step 1 — home feed                          (3 steps, as the doc asked)
 19.6s  step 1 done -> "Any questions on that before I move on?"
 21.1s  taking questions
 27.6s  answered "why is the search box on every page?"
 27.6s  taking questions          <- window restarts after the answer
 39.7s  step 2 — search a topic
 47.3s  "Anything there you'd like me to go over again?"
 59.4s  step 3 — sidebar, saved list
 67.0s  "That's the walkthrough. Any questions before we wrap up?"
 87.1s  [complete]
```

**An interruption can redirect the browser, not just the answer.** Same live
run, asked mid-demo:

```
>>> "show me how to filter the search results"
[answer]  the filter chips are along the top, plus the fuller Filters panel…
[status]  Re-planning around: filtering the search results
          plan grows 6 -> 7 steps, completed steps preserved verbatim
[step]    clicked 'Unwatched'      -> results reshape
[step]    clicked 'Search filters' -> panel opens
[step]    pressed Escape, clicked 'All' -> full result set restored
```

Getting there took fixing the failure the phrasing exposes: the run loop holds
the step it is executing in a local, so a plan swapped in mid-step used to
finish the old step and advance *past* the new one. The customer got a tidy
answer and watched the demo carry on as though they hadn't spoken.
`test_replan_mid_step_runs_the_new_step` pins it, and fails against the old
code.

Three more bugs that only a real product surfaces were found and fixed the same
way:
YouTube's Trusted Types CSP made the cursor's `innerHTML` throw and took the
whole overlay down with it (now built with `createElementNS`); SPA re-renders
silently dropped the overlay for the rest of the demo (`build()` now checks
`isConnected` and restores the caption and cursor position); and substring name
matching sent every click on "You" to the *YouTube Home* logo, which sits
earlier in the DOM (`_locate` now tries exact names before substrings, and only
visible matches).

**Execution and interruption** (measured on the earlier fixed-target build; the
executor is unchanged), real browser, no API key (fallback plan),
one mid-demo interruption:

```
[step_start] 1..5   all five started and completed, in order
>>> interrupt at step 2  →  pausing  →  answered  →  resumed at step 3
[complete] steps_completed: 5                                      PASS
```

Live frame streaming, measured:

```
141 frames over 41.8s          -> 3.4 fps sustained
avg frame 39 KB b64            (peak 147 KB)
10 full-quality PNG stills     (one per completed action)
```

Pause behaviour, measured:

```
pause request -> browser truly parked : 1.52s   (in-flight action finishing)
actions started after parked          : 0
live frames delivered across freeze   : 39      (panel stays live, page frozen)
```

---

## Harness integration

| File | What it does |
| --- | --- |
| [`walkthrough-agent-skill.yaml`](harness/walkthrough-agent-skill.yaml) | Worker Agent Skill: trigger phrases, 3-phase instructions, RBAC, audit, domain allowlist, denied actions |
| [`pipeline.yaml`](harness/pipeline.yaml) | Build & Test → Register Skill → Deploy, with `StageRollback` on failure |
| [`rollback-policy.yaml`](harness/rollback-policy.yaml) | Rollback triggers, session pinning, approval gates |

Registering the walkthrough as an Agent Skill is what turns a demo script into
shared infrastructure — versioned, governed, and callable from the catalog by
any team. Sessions pin to the skill version they started on, so a deploy can
never change the demo out from under a customer who is mid-call.

The pipeline's real gate is the pause/resume test suite. A walkthrough that
rewinds when someone asks a question is worse than no demo at all, so that
behaviour is verified on every commit rather than rehearsed before every call.

The rollback policy watches for the failure that actually hurts: `stuck-pause` —
a session that paused for a question and never resumed. That is a browser frozen
mid-sentence in front of a customer, and it triggers an automatic rollback.

---

## Bonus features

- **Voice narration** — Web Speech API, browser-native so speech starts the same
  frame the text arrives. Cancels the instant someone interrupts.
- **Plan-changing interruptions** — "show me labels instead" re-plans only the
  remaining steps; completed steps are preserved verbatim and never replayed.
- **Workflow memory** — successful plans persist to JSON. The second demo of the
  same product skips planning entirely.
