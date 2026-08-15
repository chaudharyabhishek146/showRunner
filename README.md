# Platform Walkthrough Agent

An agent that gives the product demo. It reads a product document, plans a
walkthrough, drives a **real browser** through the real product while narrating
in natural language — and when the customer interrupts with a question, it
freezes mid-step, answers using the doc and the current screen, then resumes
from exactly where it stopped.

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
Next.js UI  ──WebSocket──▶  FastAPI  ──▶  StepExecutor  ──▶  Playwright/Chromium
   │                            │              │                     │
 chat + Q&A              session state    asyncio.Event         real GitHub
 live screenshot                          pause/resume gate
 step progress                                 │
                                          Claude (Opus 5)
                                    plan · narrate · answer · re-plan
```

| Module | Responsibility |
| --- | --- |
| [`agent/doc_parser.py`](backend/agent/doc_parser.py) | Product doc → executable `StepPlan` via structured outputs |
| [`agent/narrator.py`](backend/agent/narrator.py) | Pre-generates narration; answers live questions |
| [`agent/browser.py`](backend/agent/browser.py) | Playwright wrapper, semantic (`getByRole`) selectors |
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

**Semantic selectors only.** GitHub rewrites its CSS classes constantly; its
ARIA roles are stable. The action vocabulary is a closed enum, so Claude picks
from a fixed set — it never invents a selector.

**The domain allowlist is enforced in code.** `_sanitise()` drops any
navigation off `github.com` before it reaches the browser. The prompt asks; the
code enforces. An LLM-authored plan is driving a real browser, so that check
does not get to live in a prompt.

**There is always a plan.** No API key, no network, a 500 from Claude — the
agent falls back to a hand-verified 5-step plan. A live demo must never open
with a stack trace.

**Credentials are never typed.** Auth is supplied out-of-band as a session
cookie from the environment. The agent has no login-form code path at all.

---

## Running it

```bash
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/playwright install chromium
```

```bash
cp backend/.env.example backend/.env
```

Fill in `ANTHROPIC_API_KEY` and `DEMO_REPO`. For steps that need a signed-in
account, paste the `user_session` cookie from an already-authenticated browser
into `GITHUB_SESSION_COOKIE`.

```bash
cd backend && .venv/bin/uvicorn main:app --reload --port 8000
```

```bash
cd frontend && npm install && npm run dev
```

Open http://localhost:3000 and hit **Start walkthrough**.

### Tests

```bash
cd backend && .venv/bin/python -m pytest -q -m "not integration"
```

8 hermetic tests — no network, no Claude calls, fake browser. The `integration`
marker runs the real-Chromium smoke test.

---

## Verified end to end

Real Chromium against live GitHub, no API key (fallback plan), one mid-demo
interruption:

```
[step_start] 1..5   all five started and completed, in order
[screenshot] 10 frames, up to 255KB base64
>>> interrupt at step 2  →  paused  →  answered  →  resumed at step 3
[complete] steps_completed: 5
PASS
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
