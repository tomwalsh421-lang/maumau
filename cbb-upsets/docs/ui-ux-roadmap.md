# UI/UX Improvement Roadmap

Canonical links:

- [Repository README](../README.md)
- [Model Documentation](model.md)
- [System Architecture](architecture.md)
- [Current Best-Model Report](results/best-model-3y-backtest.md)

Updated: `2026-03-12`

## Goal

Improve clarity, usability, and operator efficiency for setup, ingest,
training, backtesting, reporting, dashboard inspection, and live prediction.

## Working Agreement

- `ux_researcher` maintains this document.
- `implementer` only executes items explicitly approved by the parent task or
  clearly marked approved here.
- Prefer small, measurable workflow improvements before larger UI work.

## Current Audit

Files reviewed for this refresh:

- [src/cbb/modeling/report.py](../src/cbb/modeling/report.py)
- [docs/results/best-model-3y-backtest.md](results/best-model-3y-backtest.md)
- [src/cbb/cli.py](../src/cbb/cli.py)
- [src/cbb/ui/service.py](../src/cbb/ui/service.py)
- [src/cbb/ui/templates/dashboard.html](../src/cbb/ui/templates/dashboard.html)

Repo-specific findings:

- The canonical report already exposes the right metrics, but the highest-
  signal decisions are still buried below scope metadata and long tables.
- The report does not currently quantify closing-market coverage near the
  decision summary, even though close EV and price CLV are core repo evidence.
- The dashboard landing page is already intentionally curated, so a larger UI
  rewrite is not the next best use of time.
- The CLI command surface is broad, but the biggest immediate usability win is
  still better report interpretation rather than renaming commands.

## Ranked Improvements

### UX-1: Improve report readability and decision context

Status: approved
Implementation: completed `2026-03-12`

Problem:
The canonical report is information-dense, but it is still easy to lose the
highest-signal conclusions, caveats, and next action inside the detail.

User impact:
Operators have to translate the report into a decision manually before they
can judge promotion, rejection, or follow-up work.

Evidence:
- [src/cbb/modeling/report.py](../src/cbb/modeling/report.py) renders the
  report as one long Markdown flow with the first interpretive bullets landing
  only after the scope section.
- [docs/results/best-model-3y-backtest.md](results/best-model-3y-backtest.md)
  shows strong CLV detail, but no dedicated decision snapshot or close-quality
  coverage callout near the top.

Implementation sketch:
- add a small decision snapshot section near the top of the report
- summarize current verdict, strongest evidence, main risk, and next action in
  repo language
- add a compact close-quality coverage table so the report shows how much of
  the settled bet set has tracked close diagnostics

Acceptance criteria:
- a reader can identify the baseline verdict, main risk, and next action in
  under a minute
- close-quality coverage is visible without hunting through later sections
- dense tables remain available for deeper review

Delivered:
- the generated report now calls out close-market coverage near the assessment
- a dedicated close-market coverage table now appears before the detailed CLV
  section

### UX-2: Clarify CLI command discoverability and defaults

Status: approved
Implementation: completed `2026-03-12`

Problem:
The repo exposes many high-value CLI flows, but the relationship among
training, backtesting, reporting, prediction, and dashboard commands is still
easy to miss on first read.

User impact:
Operators can use research-oriented commands without realizing which path is
canonical for deployable review.

Evidence:
- [src/cbb/cli.py](../src/cbb/cli.py) has accurate command help, but the
  deployable path is spread across `model predict`, `model report`, and
  `dashboard`.
- [README.md](../README.md) explains the path well once read end to end, and
  the help surface is now narrow enough for a bounded wording pass.

Implementation sketch:
- inspect top-level `--help` output and README command examples together
- tighten help text only where the deployable `best` path is genuinely unclear
- avoid command renames or option churn

Acceptance criteria:
- operators can distinguish deployable-path commands from research commands
- help text gets shorter or clearer without growing the surface area

Delivered:
- top-level CLI help now calls out setup, ingest, deployable reporting,
  prediction, and dashboard workflows
- `model` and `model report` help now describe the deployable best-path more
  explicitly

### UX-3: Make dashboard inspection faster for model and bet review

Status: approved
Implementation: completed `2026-03-12`

Problem:
The dashboard is intended to be the fast inspection surface, but the next
useful changes depend on real operator usage rather than guesswork.

User impact:
There may still be friction in navigation or drill-down, but the current repo
already ships a coherent landing page, performance view, picks history, and
team detail surface.

Evidence:
- [src/cbb/ui/service.py](../src/cbb/ui/service.py) already builds focused
  overview cards, recent-performance summaries, and upcoming pick tables.
- [src/cbb/ui/templates/dashboard.html](../src/cbb/ui/templates/dashboard.html)
  already gives direct entry points into model, performance, picks, and board
  views.

Implementation sketch:
- keep the current dashboard structure intact
- tighten landing-page navigation around the most common operator tasks
- prefer copy and navigation adjustments over new pages

Acceptance criteria:
- any future dashboard change is tied to one specific workflow bottleneck
- no broad visual rewrite happens without evidence

Delivered:
- dashboard navigation now uses operator-task labels instead of generic page
  names
- the landing page now includes direct jump links to live board, recent form,
  and pick history

### UX-4: Reduce first-run setup friction

Status: approved
Implementation: completed `2026-03-12`

Problem:
The first-run path is still long, but meaningful setup improvements require a
broader pass across cluster, Helm, env, and database failure handling.

User impact:
New sessions still have a multi-step onboarding path with several external
dependencies.

Evidence:
- [README.md](../README.md) already documents a linear setup path
- the remaining friction is real, but it is not the highest-value local UI/UX
  improvement relative to report clarity

Implementation sketch:
- revisit only when the current report and deployable-path guidance are
  clearer
- prefer preflight checks and better recovery text over new wrappers

Acceptance criteria:
- any setup improvement reduces real error-prone steps rather than moving them

Delivered:
- the README quick start now separates onboarding from the deployable `best`
  workflow
- the canonical `cbb model report` path is now called out directly

## Research Log

- date: `2026-03-12`
- area reviewed: report output, CLI help surface, dashboard landing workflow
- findings:
  - report interpretation is the clearest immediate usability gap
  - dashboard scope is already coherent enough to defer larger UI work
  - CLI discoverability needs another focused pass before broad wording edits
- proposed next step: keep future UX backlog entries this concrete so the
  implementer can work from the roadmap directly
- status: completed
