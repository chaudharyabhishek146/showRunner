# Presenter's script — Platform Walkthrough Agent

Written to be **spoken**, not read. Short sentences on purpose.

- `[ ]` = stage direction, don't say it out loud
- **Bold** = land this phrase, slow down
- Measured at 140 words/minute: **~10 minutes** end to end, with the live demo
  running underneath section 4. Cut lists at the end for 5 and 3 minutes.

---

## Before you walk up — 3-minute pre-flight

Run these. Do not skip them; two of them have bitten this build already.

```bash
curl -s localhost:8000/health
```

`claude_configured` and `chrome_reachable` must both be `true`.

- **If `chrome_reachable` is false** — quit the demo Chrome window (the one on the
  `chrome-demo-profile`, not your personal Chrome) and let the agent relaunch it
  when you hit Start. A Chrome that's been open for hours can go stale after a
  Chrome auto-update and start refusing the debug connection.
- **The app is on `http://localhost:3001`**, not 3000. Port 3000 is your other
  project. Open the right tab *before* you present and leave it on screen.
- Sign into YouTube in the demo Chrome window once, beforehand. Then the agent
  skips the sign-in prompt and you save 20 seconds on stage.
- Volume up if you want the voice narration. Volume **off** if the room is small —
  it competes with you.

---

## 1 · Title slide — 50 seconds

> Hi. This is the **Platform Walkthrough Agent**.
>
> The one-line version: **it gives the product demo for you.**
>
> You upload a product document, you tell it what to show, and you point it at
> one of your open browser tabs. It plans the walkthrough against the page
> that's actually on screen, it drives **your own signed-in Chrome**, and it
> narrates while it goes.
>
> And when someone interrupts with a question — it freezes mid-step, answers
> from the document and the live screen, and then **resumes exactly where it
> stopped.**
>
> I'm going to show you that working, and then I want to talk about the part
> that's actually hard.

---

## 2 · The problem — 50 seconds

> Let me be honest about what isn't hard.
>
> **Anyone can script a browser.** Recording a demo is solved. Clicking through
> one yourself is solved.
>
> The engineering that matters is what happens **when the customer interrupts** —
> because that is the entire difference between a demo and a screen recording.
>
> A recording can't answer anything. A scripted click-through answers and then
> loses its place — it replays a step, or it skips one nobody saw. A generic
> browser agent just wanders, because it has no plan to return to.
>
> So the question I started from wasn't "can it drive a browser."
> It was **"can it be interrupted and survive it."**

---

## 3 · How it works — 55 seconds

> Here's the shape of a run. The **ordering** matters more than it looks.
>
> Upload the document. Say what to demo, in plain English. The agent attaches
> to your Chrome over the DevTools protocol — your Chrome, the one you're
> already signed into — and picks the tab you named.
>
> And *then* it reads an accessibility outline of the page that's actually open,
> and plans against those controls.
>
> [point at the bottom card]
>
> That ordering — **attach, pick the tab, read the page, then plan** — is the
> whole reason one prompt works on a site the code has never seen. It isn't
> planning from a memory of what GitHub looks like. It's planning from what's on
> the screen right now.
>
> There's no target URL in this codebase. No repo. No stored session.

---

## 4 · LIVE DEMO — 2 minutes

> Rather than talk about it, let me just run it.

**[Switch to the app on :3001. One card, one button.]**

> This build is locked to a two-minute YouTube demo, on purpose — it's a
> hackathon, and I'd rather it be the same every time than be configurable on
> stage.

**[Click Start walkthrough.]**

> It's opening Chrome now with the debug port — about three seconds — and
> attaching to the YouTube tab.

**[~16 seconds of planning. This is your dead-air gap. Fill it:]**

> While it plans: what it's doing right now is reading every control on that
> page — the roles and the accessible names — and handing them to Claude along
> with my product document. So the plan it writes can only use controls that
> genuinely exist on that screen. It can't hallucinate a button.

**[Plan appears, steps start running. Let it run one step. Then interrupt.]**

> Now — the important bit. Let me interrupt it like a customer would.

**[Type into the question box: `show me how to filter the results` — press Ask.]**

> Notice it stopped. The browser is frozen exactly where it was.

**[~7s to answer, then it says "Re-planning around…". This is the second dead-air
gap — up to ~20 seconds. Fill it:]**

> It's answering from the document and from a screenshot of what's on screen
> right now — not from what the plan *said* would be there.
>
> And it just decided something else: that wasn't a question, that was a
> **redirect**. So it's re-planning the remaining steps around filtering. The
> steps I've already shown you are preserved exactly as they were — they never
> get replayed.

**[It clicks the filter chip.]**

> And there it goes. It **did** the thing rather than describing it. That's the
> difference I care about — most agents would have written me a paragraph about
> where the filter button is.

**[When it says "Any questions before we wrap up?" — hit "Carry on" rather than
waiting out the 60-second window.]**

> It also stops and asks the room after every step, and holds a full minute at
> the end. I'll skip that here.

---

## 5 · Same build, two products — 40 seconds

> Quick evidence for the claim that nothing about any site is compiled in.
>
> Two runs. Same server, same code, real Claude, real Chrome. The **only**
> difference between them is the document I uploaded, the sentence describing
> the flow, and the tab I named.
>
> One demos YouTube. One demos GitHub Explore, and takes an in-scope hop to
> the trending page on the way.
>
> On the YouTube run, someone asked about cross-device sync — which isn't in the
> document. **It said so, and declined to guess.** That's the behaviour you want
> in front of a customer.

---

## 6 · Architecture and safety — 80 seconds

> A minute on how it's built.
>
> Next.js talks to FastAPI over a WebSocket. The executor owns the pause gate —
> that's an asyncio Event, checked **between actions**, not just between steps,
> which is why an interruption freezes the browser where it stands.
>
> Two details I'd defend.
>
> **The overlay is drawn into the page.** The OS mouse pointer isn't captured in
> screenshots — so without this, the audience watches buttons activate by
> themselves. The agent injects its own cursor, glides it to each target,
> spotlights the element, and burns the narration in as a caption.
>
> **The action vocabulary is closed.** Six verbs. Elements are addressed by ARIA
> role and accessible name — never a CSS selector. Products rewrite their class
> names constantly; what a control *is* and what it's *called* survive a deploy.
>
> On safety: **credentials are never typed.** There's no login-form code path at
> all. Authentication comes from the browser you're already signed into — so
> that whole class of problem disappears rather than getting managed. And the
> navigation allowlist is derived from the tab you picked and enforced twice in
> code. **The prompt asks; the code enforces.**

---

## 7 · The bugs slide — 80 seconds *(this is your credibility slide)*

> This is the slide I'd point a sceptical judge at.
>
> Seven defects. Every one of them **passed unit tests and failed in front of a
> live page.**
>
> YouTube enforces a Trusted Types policy, so building the cursor with innerHTML
> threw — and took the entire overlay down with it, captions and all.
>
> Single-page apps re-render the document body and took our injected nodes with
> them, so the cursor silently vanished part-way through a demo.
>
> Substring name matching meant every click meant for the sidebar "You" entry
> landed on the **YouTube logo** — because a union locator returns matches in DOM
> order, so the page was choosing, not us.
>
> And my favourite: the search step **typed into a button.** YouTube's search
> field is a combobox, not a textbox, so the fallback chain reached the Search
> button. Typing into a button raises nothing and does nothing — and the trace
> still said "typed into Search."
>
> The point isn't that I wrote bugs. It's that **none of these are findable
> without pointing the thing at a real product** — and every one of them would
> have been visible on stage.

---

## 8 · Numbers and Harness — 60 seconds

> Numbers, all from real runs — nothing estimated.
>
> Two point seven seconds from no browser at all to attached and sitting on the
> product. Pause takes one and a half seconds to actually park — and that's
> deliberate, an action already in flight runs to completion, because cancelling
> mid-action would leave a half-typed field on screen in front of the customer.
> Zero actions start after it's parked.
>
> Twenty-five tests, passing in under three seconds, so the pause-and-resume
> guarantee is checked on every commit rather than rehearsed before every call.
>
> And it's registered as a Harness Worker Agent Skill — versioned, RBAC'd,
> callable from the catalog. The pipeline's real gate is that test suite. The
> rollback policy watches for **stuck-pause**: a session that paused for a
> question and never resumed. That's a browser frozen mid-sentence in front of a
> customer.

---

## 9 · Close — 65 seconds

> Three claims, and I've shown evidence for each one.
>
> **Interruption handling is the product**, and it's asserted by a test rather
> than by a README.
>
> **Nothing about any site is compiled in** — same build, two products, proven
> by running it.
>
> And **real products break agents** in ways unit tests don't catch.
>
> Two things I'll be straight about: the "yes, I'll sign in" path has unit
> coverage but hasn't been through a real interactive login — deliberately,
> because the agent has no way to do that itself and shouldn't. And my live runs
> were driven by a scripted client; the UI is verified by screenshot and
> type-check, not a full click-through.
>
> Bonus features are all in — voice narration, plan-changing interruptions, and
> workflow memory, so the second demo of the same product skips planning
> entirely.
>
> **Thank you.** Happy to take questions — or run it again on something you pick.

---

## If something goes wrong on stage

Say the recovery line, keep moving. Never debug in front of the room.

| What happens | Say this | Then |
|---|---|---|
| Chrome won't attach | "It's telling me Chrome isn't listening on the debug port — which is exactly the check I built for this." | Quit the demo Chrome window, hit Start again. It relaunches in ~3s. |
| A step fails to click | "That's the honest failure mode — it reports 'couldn't click' and carries on rather than pretending." | Let it continue. Don't restart. |
| The plan looks thin | "It planned three steps because the document asked for a two-minute version — length comes from the doc, not from me." | Move on. |
| Claude is slow / no key | "It's falling back to a plan built from the document's own headings — a demo should never open with a stack trace." | Keep narrating over it. |
| Total failure | "Let me show you the run I recorded earlier instead." | Go to the evidence slides. **Have the PDF open in another tab.** |

---

## Likely questions, and short answers

**"Isn't this just a Playwright script?"**
> A Playwright script can't be interrupted. Ask this one a question mid-demo and
> it freezes between actions, answers from the doc plus the current screenshot,
> and resumes into the same step. And it isn't written against any site — it
> plans against the page that's on screen.

**"How is it not hallucinating buttons?"**
> The action vocabulary is a closed enum of six verbs, and every element is
> addressed by role plus accessible name — taken from an outline read off the
> live page. If the control isn't on screen, it isn't in the plan. And when a
> lookup does fail, the trace says so rather than claiming success.

**"What stops it doing something destructive?"**
> Three things. The navigation allowlist is derived from the tab you picked and
> checked twice in code — the prompt asks, the code enforces. The planner is
> told to prefer showing over changing: never delete, send, publish, or pay. And
> it never types a credential, because it doesn't have any.

**"Does it only work on YouTube?"**
> No — that's just what this build is locked to for the hackathon. One
> environment variable gives you the general agent back. I ran the same build
> against GitHub Explore with a different document; the only thing that changed
> was the upload and the tab name.

**"What would you do with another week?"**
> Drive the UI end-to-end in CI rather than a scripted WebSocket client, finish
> the interactive sign-in path, and teach the planner to recover when a control
> it planned for isn't on the page any more — right now it reports the failure
> and continues, which is honest but not clever.

---

## Cut list

**If you have 5 minutes:** keep 1, 2, the live demo, 7 (bugs), 9 (close). Drop
3, 5, 6, 8 — and say "architecture and numbers are in the PDF."

**If you have 3 minutes:** title, one sentence of the problem, the live demo,
and the bugs slide. The demo *is* the pitch.

**If the demo dies:** slides 5 and 8 carry the evidence on their own.
