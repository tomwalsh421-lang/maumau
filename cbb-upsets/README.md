# CBB Upsets

## Project Overview

CBB Upsets is a Python CLI for building and operating a college basketball
betting workflow against a local PostgreSQL database. It ingests NCAA men's
basketball results from ESPN, ingests current and historical odds from The Odds
API, stores both in Postgres, trains deployable moneyline and spread models,
backtests them walk-forward, and produces a live bet slip from the current
slate.

The supported production scope remains one sport: NCAA men's basketball. Model,
execution, and evaluation behavior are intentionally sport-specific rather than
generalized across leagues.

The major components are:

- a Typer-based CLI for database, ingest, and modeling workflows
- a local dashboard UI launched from the CLI, with classic server-rendered
  pages plus React migration routes fed by the same middleware JSON surface
- a PostgreSQL schema for teams, games, odds snapshots, ingest checkpoints, and
  shadow-only official availability reports
- a modeling pipeline for feature generation, training, backtesting, and
  prediction
- a local Helm chart used to run PostgreSQL and supporting cluster services in
  Kubernetes

## Quick Start

This is the shortest realistic end-to-end path to first success for a new
engineer. It uses the moneyline market because that only requires one
historical odds backfill. The current deployable path is spread-only when a
spread artifact is available, but moneyline is still the fastest onboarding
path.

Two workflows matter here:

- onboarding path: the shortest route to a first successful train and predict
- deployable path: the current spread-first `best` workflow used for the
  canonical report, dashboard, and live board

The commands below assume `source .venv/bin/activate`. If you do not want to
activate the environment, replace `cbb ...` with
`.venv/bin/python -m cbb.cli ...`.

Before you start, install the dependencies listed in
[Required Dependencies](#required-dependencies).

1. Create the virtualenv and local config.

```bash
make install
cp .env.example .env
source .venv/bin/activate
```

2. Create the local Kubernetes cluster.

```bash
make k8s-up
kubectl cluster-info
```

3. Deploy the Helm chart.

```bash
helm upgrade --install cbb-upsets chart/cbb-upsets \
  -f chart/cbb-upsets/values.yaml \
  -f chart/cbb-upsets/values-local.yaml

kubectl get pods
```

4. Forward PostgreSQL from the cluster.

```bash
kubectl port-forward svc/cbb-upsets-postgresql 5432:5432 -n default
```

5. Initialize the schema and verify the CLI can talk to the database.

```bash
cbb db init
cbb db summary
```

6. Load the minimum data needed for a first end-to-end model run.

These commands spend Odds API credits:

```bash
cbb ingest data --years-back 1
cbb ingest closing-odds --years-back 1 --market h2h
cbb ingest odds
```

When you want the strongest historical market context rather than the cheapest
first run, widen the historical close pull to all supported featured-market
regions:

```bash
cbb ingest closing-odds --years-back 5 --market h2h,spreads,totals --bookmakers draftkings,fanduel,betmgm,pinnacle
```

7. Train a model artifact.

```bash
cbb model train --market moneyline --artifact-name quickstart
```

8. Run a prediction command.

```bash
cbb model predict --market moneyline --artifact-name quickstart
```

If the prediction command prints `No bets qualified under the current policy.`,
that still counts as a successful first run. It means the pipeline worked and
the current slate did not clear the betting thresholds.

Deployable path:

To move from onboarding to the current spread-first `best` workflow, add
historical spread odds and then use `best`:

```bash
cbb ingest closing-odds --years-back 5 --market spreads
cbb model train --market spread --artifact-name latest
cbb model predict --market best --artifact-name latest
cbb model predict --market best --artifact-name latest --output-format json
cbb dashboard --open
```

That default `best` path now uses the fixed deployable spread policy. The older
spread auto-tuning path is still available with `--auto-tune-spread-policy` for
research comparisons. The fixed deployable spread path also includes a small
rest-gap quality guard, so unusual schedule spots are filtered before staking,
and it now caps the number of same-day spread bets at five so the heaviest
slates stay focused on the top-ranked opportunities. The current fixed spread
baseline is intentionally tighter than the earlier version: it now requires
more established teams, broader cross-book support, and larger
model-vs-market agreement before a bet qualifies.
`model predict` now returns one deterministic decision per upcoming game in the
live path: `bet`, `wait`, or `pass`. Text output remains human-readable, while
`--output-format json` emits the canonical `predict.v1` payload with sportsbook,
cross-book survivability, freshness, min-acceptable execution bounds, and
optional shadow-only availability metadata when stored official reports exist
for that matchup, including per-game context plus a slate-level summary of how
many upcoming rows currently have stored coverage and how fresh that stored
coverage is.
For cross-book execution research, `model backtest`, `model predict`, and
`model report` now also support survivability controls such as
`--min-positive-ev-books` and `--min-median-expected-value`. Those controls are
intended for research comparisons, not the default deployable path.
The opt-in auto-tuned path now ranks spread policies by walk-forward profit
first, but only promotes them when their out-of-sample spread closing EV stays
non-negative.
For spread research, `--use-timing-layer` adds an opt-in closing-line filter:
it only keeps early spread bets when the auxiliary timing model expects the
market to move in your favor, and otherwise surfaces them as a wait list.

If you only need the canonical deployable summary, run `cbb model report`.
That command refreshes the tracked latest report, writes the untracked history
copy, and updates the dashboard snapshot used by `cbb dashboard`.
The default report and live bet-slip scale now use a notional
`+$3,750.00` bankroll, which makes the typical qualified stake render around
one `$25` unit by default. Override with `--starting-bankroll` or `--bankroll`
if you want a different dollar scale.
For bracket use, the repo also has a bounded tournament wrapper around the
moneyline model. Run `cbb model tournament --artifact-name latest` to score the
tracked `data/tournaments/ncaa_men_2026.json` bracket, print deterministic
picks for every remaining game, and estimate advancement odds from Monte Carlo
simulation. Real tournament rows still use stored market data when present, but
later-round and other marketless bracket matchups now fall back to a separate
common-feature logistic model trained from the same completed-game window so
synthetic picks do not depend on zero-filled market features. That path is
meant for bracket guidance, not the deployable betting-policy surface.
For completed years, `cbb model tournament-backtest --seasons 3 --max-season 2025`
replays the tracked `2023-2025` men's bracket specs, trains each evaluation
season only on data available through that tournament's first play-in tip, and
reports round-by-round bracket accuracy against the actual results.

The new data-acquisition lane is shadow-only for now. Use
`cbb ingest availability PATH...` to import captured official NCAA
availability JSON files and wrapped free-source conference / NCAA archive
capture JSON files into Postgres. Those rows feed the canonical report and
dashboard snapshot for coverage review, and the recommendations page can now
show row-level availability context when the prediction contract already has a
stored official report for that game, but they do not affect live
predictions, backtests, or staking yet.

For lightweight live operations, the CLI also exposes `cbb agent`. That
long-running local loop refreshes a recent ESPN scoreboard window plus current
Odds API odds and scores, then scans the current upcoming board for deployable
best-path bets before sleeping until the next run. The ESPN leg also catches
up from the last successful stored ingest checkpoint before applying its
normal recent-window refresh, and it reuses the stored canonical team catalog
first when the local database is already seeded.
That product-facing loop is separate from the repo's manual roadmap work, which
now happens in dedicated git worktrees rather than through a background
supervisor.

## Documentation

- Model documentation: [docs/model.md](docs/model.md)
- System architecture: [docs/architecture.md](docs/architecture.md)
- Current deployable results: [docs/results/best-model-5y-backtest.md](docs/results/best-model-5y-backtest.md)

The README, [docs/model.md](docs/model.md), and
[docs/architecture.md](docs/architecture.md) describe the durable system. The
generated report in `docs/results/` is where current tuned performance and
season-by-season results belong.
That canonical report now opens with a compact decision snapshot and
close-market coverage section so promotion calls can be made before reading the
full tables.

One durable modeling detail worth knowing up front: the deployable spread path
is no longer trained as a raw cover/no-cover classifier. The default
`--model-family logistic` spread path now predicts expected margin relative to
the market spread, converts that estimate into cover probability, and then
calibrates it against held-out priced examples.

## Local Development Setup

This repository assumes local development happens against Kubernetes running on
your machine. The normal path is:

1. create a local `k3d` cluster
2. deploy the Helm chart, which includes PostgreSQL
3. port-forward PostgreSQL to `127.0.0.1:5432`
4. run the CLI locally from a Python virtualenv

The supported manual helper targets for those cluster steps are:

- `make k8s-up`
- `make cli-image-build`
- `make cli-image-load`
- `make helm-deps`
- `make helm-check`
- `make helm-template`
- `make helm-up`
- `make helm-status`
- `make db-port-forward`

The CLI is the primary application interface. Most workflows, including ingest,
training, backtesting, prediction, audit, and backup, run from your shell
against the forwarded local Postgres instance.
For local inspection, the same CLI can also launch a lightweight dashboard UI
without introducing a separate frontend service.
The primary `/` dashboard route and `/upcoming` recommendations route now run
through the React client against the existing dashboard JSON surfaces. The old
server-rendered overview and recommendations pages remain available at
`/classic` and `/classic/upcoming` as explicit migration fallbacks, while `/app`
still exists as the React overview alias.
When you change the React client, run
`cd frontend && npm install` once and then `npm run build` to refresh the
checked-in bundle under `src/cbb/ui/static/react/`.
The repo now also has one supported container build path for the CLI runtime
foundation: `make cli-image-build` builds a non-root image that keeps the repo
source tree rooted at `/app`, so existing repo-relative runtime paths such as
`sql/schema.sql`, `data/team_home_locations.csv`, and `docs/results/` still
work inside the image. That image is groundwork for later chart-managed job
slices, not a replacement for the current local virtualenv workflow.
For local cluster validation of the runtime chart paths, run
`make cli-image-load` after the build step to import the tagged CLI image into
the configured `k3d` cluster before enabling `runtime` or `runtime.schedule`.
The chart now also exposes two disabled-by-default CLI runtime paths: a
singleton `runtime` Deployment for the looping agent and a `runtime.schedule`
CronJob for `cbb agent --run-once`. Keep both off until you set
`runtime.image.tag` and any secret-backed env needed for those pods. The chart
derives `DATABASE_URL` from the chart-managed PostgreSQL release unless you
override `runtime.databaseUrl`, and it fails fast if you try to enable both
runtime modes at the same time.
The same local-first pattern still applies to live refresh automation in the
current supported path: run `cbb agent --delay-mins 15` in a long-lived shell,
`tmux`, or another local process manager rather than treating the new image
foundation as a finished in-cluster service rollout.
For chart-managed scheduled runtime jobs, the CronJob path now defaults to
`cbb agent --run-once`, which runs one bounded refresh-and-scan iteration and
exits without sleeping.

Copy `.env.example` to `.env` before running the CLI. The required settings are:

- `DATABASE_URL`: SQLAlchemy Postgres URL for the forwarded local database
- `ODDS_API_KEY`: required for current and historical odds ingest
- `ODDS_API_BASE_URL`: defaults to The Odds API v4 base URL

## Local Agent Loop

`cbb agent` is a long-running local loop. Each iteration does three things by
default:

1. catches up from the last successful stored ESPN ingest date, then re-fetches
   a small recent ESPN window with `force_refresh=True`
2. refreshes current odds and optional scores from The Odds API
3. scores the current `best` path against upcoming games and prints any
   currently qualified bets or wait-list entries, plus a compact scoreboard
   section for in-progress games and finals updated within the last 12 hours

Qualified bets in agent mode also print one separate FanDuel college-
basketball team-page link per recommendation for quick manual lookup. These
are team-page links, not prefilled betslip deep links.

Run it manually:

```bash
cbb agent --delay-mins 15
```

For one scheduled-job-style iteration:

```bash
cbb agent --run-once
```

Useful options:

- `--espn-refresh-days`: how many recent calendar days, including today, to
  re-fetch from ESPN
- `--espn/--no-espn`: enable or disable the ESPN leg
- `--odds/--no-odds`: enable or disable the current-odds leg
- `--regions`, `--markets`, `--bookmakers`: scope controls for current odds
- `--include-scores/--no-include-scores`, `--scores-days-from`: score refresh
  controls for the Odds API leg
- `--scan-bets/--no-scan-bets`: enable or disable the post-refresh best-path
  scan
- `--run-once`: do exactly one refresh-and-scan iteration, then exit without
  sleeping
- `--artifact-name`, `--bankroll`, `--limit`: control which artifact and stake
  scale the post-refresh bet scan uses
- `--delay-mins`: minutes to sleep between loop iterations

Stop the loop with `Ctrl-C`. If the repo has no ESPN checkpoint yet, the agent
falls back to the latest completed stored game date and then to the configured
recent refresh window.

## Manual Roadmap Worktrees

The repo no longer ships a background supervisor for infra, model, or UX agent
work. Run each lane manually in its own terminal and git worktree instead.

Suggested worktree layout:

```bash
git worktree add ../cbb-upsets-infra -b codex/infra main
git worktree add ../cbb-upsets-model -b codex/model main
git worktree add ../cbb-upsets-ux -b codex/ux main
```

Recommended operating pattern:

1. open one terminal per active lane
2. `cd` into that lane's dedicated worktree
3. use the matching roadmap markdown plus role prompt files under `agents/`
4. run verification commands yourself
5. review, commit, and merge back manually

Lane guides:

- infra: `docs/infra-roadmap.md` plus `agents/infra-researcher.toml`,
  `agents/infra-implementer.toml`, and `agents/infra-verifier.toml`
- model: `docs/model-improvement-roadmap.md` plus
  `agents/roadmap-researcher.toml`, `agents/implementer.toml`, and
  `agents/model-verifier.toml`
- ux: `docs/ui-ux-roadmap.md` plus `agents/ux-researcher.toml`,
  `agents/implementer.toml`, and `agents/ux-verifier.toml`

Keep one bounded task per worktree. Nothing in the repo auto-commits,
auto-pushes, or schedules the next lane for you anymore.

## Required Dependencies

- Docker: container runtime used by `k3d` to run the local Kubernetes cluster.
  Recommended install: Docker Desktop on macOS or Windows, Docker Engine on
  Linux.
- `k3d`: local Kubernetes cluster manager used by `make k8s-up`. Recommended
  install: `brew install k3d` or the official `k3d` release binary.
- `kubectl`: used to inspect the cluster and port-forward PostgreSQL.
  Recommended install: `brew install kubectl`.
- Helm 3: used to deploy `chart/cbb-upsets`. Recommended install:
  `brew install helm`.
- Python 3.11+: used for the CLI, ingest code, and modeling pipeline.
  Recommended install: `pyenv` or `brew install python@3.11`.
- Make: used for local workflow shortcuts such as `make install`,
  `make k8s-up`, `make helm-deps`, `make helm-check`, `make helm-up`,
  `make db-port-forward`, and `make check`.
  Recommended install: Xcode Command Line Tools on macOS or your system
  package manager on Linux.
- PostgreSQL client tools: used by `cbb db backup` and `cbb db import`.
  Recommended install: `brew install libpq` or `brew install postgresql@16`.
- An Odds API account and API key: used by `cbb ingest odds` and
  `cbb ingest closing-odds`.

## Running the System Locally

1. Create the Python environment and local config.

```bash
make install
cp .env.example .env
source .venv/bin/activate
```

2. Start the local Kubernetes cluster.

```bash
make k8s-up
kubectl cluster-info
```

3. Validate and deploy the local services. This starts PostgreSQL in the
   cluster and applies the chart's supporting resources.

```bash
make helm-check
make helm-up
make helm-status
kubectl get pods
```

If you are validating the chart-managed runtime Deployment or CronJob locally,
build and load the CLI image into the `k3d` cluster first:

```bash
make cli-image-build
make cli-image-load
```

`make helm-check` and `make helm-up` now bootstrap the locked chart
dependencies automatically in a fresh worktree. Use `make helm-deps` if you
want to rebuild those dependency tarballs explicitly before validating or
deploying. `make helm-check` now keeps the render verification concise, while
`make helm-template` remains the explicit full-manifest helper when you want to
inspect the rendered YAML directly. The supported `make helm-up` path now runs
that same validation preflight before it reaches `helm upgrade --install`, and
`make helm-status` gives the supported release-level inspection view after
deploy.

4. Forward PostgreSQL from the cluster to your local shell and point
   `DATABASE_URL` at it. The default local chart values use database
   `cbb_upsets`, user `cbb`, and password `cbbpass`.

```bash
make db-port-forward
```

Example `.env` value:

```bash
DATABASE_URL=postgresql+psycopg2://cbb:cbbpass@127.0.0.1:5432/cbb_upsets
```

5. Initialize the schema and seed the canonical Division I team catalog.

```bash
cbb db init
```

6. Run the application workflows from the CLI.

```bash
cbb db summary
cbb ingest data --years-back 5
cbb ingest closing-odds --years-back 5 --market h2h
cbb ingest closing-odds --years-back 5 --market spreads
cbb ingest odds
cbb model train --market spread --artifact-name latest
cbb model backtest --market best
cbb model report
cbb model report recent --days 7
cbb model predict --market best --artifact-name latest
cbb dashboard --window-days 14 --no-open
```

The two Odds API commands above spend credits. The generated five-season
performance summary is tracked separately in
`docs/results/best-model-5y-backtest.md`, and the dashboard's canonical
historical payload is tracked in
`docs/results/best-model-dashboard-snapshot.json`. The report now includes aggregate
spread segment attribution for the qualified-bet set so expected-value tails,
probability-edge tails, season phase, line bucket, book depth, conference
context, and tip-window effects can be audited from the canonical workflow.

Use `make check` for the standard local verification path:

```bash
make check
```

## CLI Overview

- `cbb db init`: initialize `sql/schema.sql` and seed the canonical D1 team
  catalog.

```bash
cbb db init
```

- `cbb db summary`: show counts, date range, and stored sample rows from the
  current database.

```bash
cbb db summary
```

- `cbb db audit`: verify stored games against ESPN coverage, final scores, and
  stored venue / neutral-site / postseason context. For reproducible
  historical validation, prefer an `--end-date` before the current live slate
  so same-day ESPN schedule/status churn does not show up as a transient
  mismatch.

```bash
cbb db audit --years-back 3
```

- `cbb db backup`: create a repo-local SQL dump under `backups/`.

```bash
cbb db backup --name audited_snapshot.sql
```

- `cbb db import`: replace the configured database with a saved SQL dump.

```bash
cbb db import audited_snapshot.sql
```

- `cbb dashboard`: launch the local server-rendered dashboard UI. The UI reads
  the canonical dashboard snapshot for heavy historical views, keeps upcoming
  picks and team views on lighter live/database paths, adds short-lived
  in-process caching, supports alias-aware team search, and keeps the current
  strategy interpretation explicit: price/no-vig/close-EV quality matters more
  than raw spread line CLV. The presentation layer now talks to a dedicated
  in-repo dashboard middleware package rather than reaching straight into UI-
  local model/database helpers. On startup, the command validates
  `docs/results/best-model-dashboard-snapshot.json` against the active best-path
  artifacts and canonical report settings; if the snapshot is missing or stale,
  it automatically refreshes the canonical `cbb model report` workflow before
  serving. Upcoming pages still show their snapshot timestamps so freshness
  stays visible. The performance view now pairs recent windows with a full-
  window cumulative chart and a zero-baseline season overlay so late-season
  runs stay in multi-season context, breaks out min/max settled bet size for
  each time frame, and those time-series charts now support point inspection
  plus season-isolation toggles without leaving the page. The live board now
  keeps recent finals and in-progress games visible alongside
  upcoming games, including whether each game was a bet, watch-only angle, or
  pass plus the live/final score when the database has it. The upcoming page
  also summarizes how many current upcoming rows have stored official
  availability coverage, how fresh that coverage is, and whether any covered
  rows still have unmatched availability records or reported
  `out`/`questionable` statuses, plus which source labels contribute to the
  covered slate, before you scan the row-level details. Use the dashboard for
  live board inspection, pick
  history, and team pages; the older
  `cbb db view ...` commands were removed. Use
  `--open/--no-open`, `--host`, `--port`, and `--window-days` to control the
  local session.

```bash
cbb dashboard --host 127.0.0.1 --port 8765 --open
```

- `cbb ingest data`: backfill historical ESPN game results plus stored
  neutral-site, postseason, and venue metadata from the ESPN scoreboard feed.

```bash
cbb ingest data --years-back 3
```

The repo now also carries a tracked home-location catalog at
`data/team_home_locations.csv`. It is generated from each team's dominant
stored non-neutral home venue and geocoded into an auditable city/state
location, timezone, and elevation record. The current promoted baseline uses
that catalog for report diagnostics and future travel research, but not as a
promoted live model input.

- `cbb ingest odds`: ingest current odds and optional recent scores from The
  Odds API.

```bash
cbb ingest odds --sport basketball_ncaab
```

- `cbb ingest closing-odds`: backfill historical closing odds from The Odds
  API. The default path only requests snapshot times for games still missing a
  closing line and skips snapshot times already checkpointed. Use
  `--ignore-checkpoints` for recent repair windows when you want to revisit
  checkpointed missing-close slots without widening to every completed game in
  the date range. Use `--regions` to widen bookmaker coverage for historical
  featured markets, or `--bookmakers` when you want a specific curated book
  set. The historical repair path now also retries the provider's immediately
  previous historical snapshot once when the exact tip-time request returns no
  match, caches repeated request times within the same run, and tolerates
  provider home/away reversals when linking historical events back to stored
  games.

```bash
cbb ingest closing-odds --years-back 5 --market h2h,spreads,totals --bookmakers draftkings,fanduel,betmgm,pinnacle
cbb ingest closing-odds --years-back 5 --market spreads --regions us,us2,uk,eu,au
cbb ingest closing-odds --years-back 5 --market spreads --bookmakers draftkings,fanduel,betmgm,pinnacle
```

- `cbb model train`: train a moneyline or spread artifact from the loaded
  seasons. The default deployable spread artifact uses the `logistic` family
  flag for a margin-versus-market residual model. Use
  `--model-family hist_gradient_boosting` for the research-only spread
  challenger.

```bash
cbb model train --market spread --artifact-name audited_backfill_v5
```

- `cbb model backtest`: run a walk-forward bankroll backtest. The default
  deployable `best` and `spread` paths now use the fixed searched spread
  policy; use `--auto-tune-spread-policy` only when you want the research
  walk-forward tuner. Use `--spread-model-family hist_gradient_boosting` to
  compare the tree-based spread challenger against the deployable default
  `logistic` spread path.

```bash
cbb model backtest --market best --evaluation-season 2026
```

- `cbb model report`: backtest the current deployable `best` model over the
  last loaded seasons, refresh the tracked latest report under `docs/results/`,
  write a timestamped history copy under `docs/results/history/`, and refresh
  the dashboard snapshot at
  `docs/results/best-model-dashboard-snapshot.json` when the command is run
  with the canonical best-workflow settings. The default report uses the fixed
  deployable spread policy; use
  `--auto-tune-spread-policy` when you want the research auto-tuned version.
  Use `--spread-model-family ...` when you want a non-default spread-family
  report. Non-canonical report runs still write the Markdown output but do not
  replace the dashboard snapshot. The report now also tracks closing-line
  value, including spread line movement, spread price/no-vig close deltas, and
  spread closing EV, plus capital-deployment diagnostics such as requested
  stake capture and active-day exposure usage, so strategies that win short-run
  ROI but do not beat the close or do not actually use the intended bankroll
  are visible before promotion.

```bash
cbb model report
```

- `cbb model report recent`: run the current walk-forward backtest settings and
  print the most recent simulated settled bets, anchored to the latest bet in
  the evaluation window. This is the quickest way to inspect what the model
  would recently have bet without rewriting the canonical Markdown report.
  Default text output uses the same compact slip style as `model predict`;
  add `--verbose` for the full field-level diagnostics.

```bash
cbb model report recent --days 7
```

- `cbb model predict`: load trained artifacts, score the current slate, and
  emit one deterministic decision per upcoming game. The default text output
  prints the summary header, applied policy, risk guardrails, bet slip, wait
  list, and optional upcoming-game table. Add `--output-format json` for the
  canonical machine interface, and `--show-upcoming-games` to render one best
  angle per game in text mode. The default deployable spread path requires
  positive EV to survive at multiple books before it will take the best
  executable quote, and live output includes sportsbook, coverage, freshness,
  uncertainty-disclosure context, a high-level availability shadow summary
  with coverage, freshness, matching-quality counts, and per-slate status-mix
  counts plus contributing source labels, and optional shadow-only per-game
  availability metadata in `predict.v1`. Bet-slip rows also begin with an
  explicit `bet=...` instruction so the action to place is obvious before the
  metrics.

```bash
cbb model predict --market best --artifact-name audited_backfill_v5
```

- `cbb model tournament`: generate a full NCAA tournament bracket from the
  tracked local bracket spec plus the trained moneyline artifact. Live First
  Four and round-of-64 matchups use stored current market rows when present;
  marketless bracket rows use a tournament-only common-feature fallback so the
  CLI can fill the whole bracket and report advancement odds without relying on
  zeroed market inputs.
- `cbb model tournament-backtest`: replay completed men's tournament bracket
  specs for bounded prior-years evaluation. Each season trains on the trailing
  pre-tournament data available at the time, then compares deterministic picks
  to the actual bracket path.

```bash
cbb model tournament --artifact-name latest --simulations 5000
cbb model tournament-backtest --seasons 3 --max-season 2025
```
