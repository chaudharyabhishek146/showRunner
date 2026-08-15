# GitHub Issues & Project Boards — Product Guide

## What this product does

GitHub Issues and Project Boards are the planning layer that sits directly on top of
your code. Instead of tracking work in a separate tool that drifts out of sync with
the repository, every unit of work lives beside the branch, commit, and pull request
that resolves it.

## Core concepts

### Issues

An **Issue** is a single unit of trackable work — a bug, a feature request, a chore,
or a question. Every issue has:

- **Title** — a short, action-oriented summary. Good titles read like commands
  ("Fix crash on empty payload"), not like symptoms ("It's broken").
- **Body** — Markdown-formatted detail: reproduction steps, acceptance criteria,
  screenshots, links.
- **Labels** — free-form categorical tags (`bug`, `enhancement`, `p0`, `frontend`).
  Labels drive filtering, automation, and board routing.
- **Assignee** — the person accountable for the issue moving forward.
- **Milestone** — a dated bucket that groups issues into a release.

Issues are permanent, addressable records. They can be referenced from commit
messages (`Fixes #42`), which auto-closes them when the commit merges.

### Project Boards

A **Project Board** is a live view over a set of issues. The board does not own the
issues — it renders them. The same issue can appear on several boards at once.

Boards are organized into **columns** (in the classic view) or grouped by a
**single-select field** such as `Status` (in Projects v2). The default lifecycle is:

1. **Todo** — accepted, not started.
2. **In Progress** — someone is actively working it.
3. **Done** — merged, verified, closed.

Dragging a card between columns updates the underlying field on the issue, and that
change is visible to everyone instantly. There is no separate "sync" step.

### Automation

Boards support built-in workflows that remove manual card-shuffling:

- **Item added to project** → set `Status` to `Todo`
- **Pull request merged** → set `Status` to `Done`
- **Issue closed** → set `Status` to `Done`
- **Auto-archive** items that have been `Done` for more than two weeks

Because automation reads real repository events, the board reflects engineering
reality rather than someone's recollection of it.

## The everyday workflow

1. **File the issue.** Anyone — engineer, PM, support — opens an issue describing the
   work. It lands in the repository's issue list immediately.
2. **Triage it.** Add labels and an assignee. Labels are how you separate a `p0`
   outage from a `good-first-issue`.
3. **Put it on the board.** Add the issue to the team's project board so it becomes
   visible in planning. New items land in `Todo`.
4. **Start work.** Move the card to `In Progress`. Create a branch from the issue —
   GitHub links the branch to the issue automatically.
5. **Close the loop.** Open a PR that references the issue. When the PR merges, board
   automation moves the card to `Done` and the issue closes itself.

## Why teams choose this

- **One source of truth.** Planning data and code live in the same system, so the
  board can never silently drift from the repository.
- **Zero context switching.** Engineers never leave GitHub to update status.
- **Traceability by default.** Every closed issue links to the exact commit and PR
  that resolved it — an audit trail you get for free.
- **Flexible views.** The same issue set renders as a board, a table, or a roadmap
  depending on who is looking and what question they are asking.

## Common questions

**Can one issue live on multiple boards?**
Yes. Issues are owned by the repository; boards are views. A platform issue can
appear on both the platform team's board and the release board simultaneously.

**What happens to the board if we close an issue outside of it?**
Automation catches it. Closing the issue from the issue page, from a commit message,
or via the API all trigger the same `Status → Done` transition.

**Do labels and board columns do the same thing?**
No. Labels describe *what the issue is* (a bug, frontend work, high priority).
Columns describe *where it is in the lifecycle*. An issue keeps its labels forever;
it moves through columns once.

**How do we handle work that isn't in a repository?**
Projects v2 supports draft items — cards with no backing issue. They're useful for
placeholders, and you can convert a draft into a real issue at any time.
