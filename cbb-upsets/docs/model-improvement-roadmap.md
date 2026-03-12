# Model Improvement Roadmap

Canonical links:

- [Repository README](../README.md)
- [Model Documentation](model.md)
- [System Architecture](architecture.md)
- [Current Best-Model Report](results/best-model-3y-backtest.md)

Updated: `2026-03-12`

## Goal

This document is the current research view of how to improve the NCAA men's
basketball spread model.

The optimization target is unchanged:

- long-run ROI
- stability across seasons
- realistic betting activity
- no material drawdown increase

The strategic view changed again after a full repo review, the latest
canonical report refresh, recent local data-quality diagnostics, and a fresh
outside-literature pass:

- the current edge still looks primarily execution- and calibration-driven,
  not raw spread-line-driven
- further tuning of the same stored signal set is now demoted after another
  adaptive recalibration failure
- the first neutral-site / postseason model experiment improved `2026` and
  reduced drawdown, but did not survive the full three-season window
- close-based evaluation remains central, but it is important enough that
  closing-line matching quality itself should now be treated as roadmap work
- the LLM / news lane stays in scope only as archived retrieval plus
  structured event extraction, not as generic sentiment or free-form summaries

## Current Baseline

The current deployable path is still a spread-first `best` strategy.

Code path summary:

1. build sequential pregame features from stored NCAA game and odds history
2. fit a linear spread residual model that predicts expected margin relative to
   the market line
3. convert that residual estimate into a cover probability
4. calibrate with Platt scaling plus market-relative shrinkage
5. widen or tighten spread uncertainty by line size, season phase, and book
   depth
6. reprice the model at each executable bookmaker quote
7. gate bets with a conservative quote-level probability buffer and fixed risk
   controls
8. select the best surviving quote across books and apply bankroll limits

Primary code paths:

- training: [src/cbb/modeling/train.py](../src/cbb/modeling/train.py)
- features: [src/cbb/modeling/features.py](../src/cbb/modeling/features.py)
- quote execution: [src/cbb/modeling/execution.py](../src/cbb/modeling/execution.py)
- backtesting: [src/cbb/modeling/backtest.py](../src/cbb/modeling/backtest.py)
- policy: [src/cbb/modeling/policy.py](../src/cbb/modeling/policy.py)
- prediction: [src/cbb/modeling/infer.py](../src/cbb/modeling/infer.py)

Current tracked baseline from
[docs/results/best-model-3y-backtest.md](results/best-model-3y-backtest.md):

- aggregate: `+$268.02` on `536` bets, ROI `+7.20%`
- seasons: `2024=-6.66%`, `2025=+13.49%`, `2026=+10.06%`
- profitable seasons: `2/3`
- max drawdown: `8.78%`
- aggregate spread close EV: `+0.086`
- aggregate spread line CLV: `-0.47 pts`
- aggregate spread price CLV: `+1.91 pp`
- aggregate spread no-vig close delta: `+1.61 pp`

Current interpretation:

- the system still is not proving a durable raw spread-line edge
- it is proving a modest, repeatable price/execution edge against executable
  quotes
- the promoted gains still come from calibration, uncertainty control, and now
  one explicit same-slate risk cap rather than richer model structure
- the canonical dashboard now reads the structured snapshot generated alongside
  `cbb model report`, so the current report output is the fast-path source of
  truth for heavy historical views

## What Has Actually Worked

The promoted changes in this repo all improved how the existing market-anchored
model qualifies, calibrates, or explains bets.

| Iteration | Change | Before | After | Result |
| --- | --- | --- | --- | --- |
| 1 | Season-phase spread calibration | `+3.66%` ROI, `14.22%` DD, `689` bets | `+5.80%` ROI, `13.38%` DD, `633` bets | promoted |
| 2 | Uncertainty-aware edge threshold / lower-bound quote gating | `+5.80%` ROI, `13.38%` DD, `633` bets | `+7.05%` ROI, `11.73%` DD, `575` bets | promoted |
| 3 | Heteroskedastic spread residual uncertainty | `+7.05%` ROI, `11.73%` DD, `575` bets | `+7.34%` ROI, `10.49%` DD, `569` bets | promoted |
| 10 | Segment attribution for qualified spread bets | no bankroll change | added segment diagnostics only | promoted as evaluation |
| 13 | Tail diagnostics for qualified spread bets | no bankroll change | added EV / edge tail diagnostics only | promoted as evaluation |
| 14 | Venue / neutral-site / postseason data foundation | no bankroll change | added stored NCAA site / venue / season-type context | promoted as data foundation |
| 16 | Same-day spread exposure cap (`max_bets_per_day=6`) | `+7.18%` ROI, `10.49%` DD, `570` bets | `+7.20%` ROI, `8.78%` DD, `536` bets | promoted |

Local lesson:

- the remaining edge responds to better calibration, better uncertainty
  handling, and better execution-aware evaluation
- it has not responded to attempts to make the core predictive model more
  expressive on the same information set
- the first promoted non-model step after that pattern emerged was new NCAA
  context acquisition, not more model family complexity

## Recent Failed Experiments

The recent failures are now consistent enough to support a harder pivot.

| Iteration | Change | Gate / Full Result | Failure Mode | Decision |
| --- | --- | --- | --- | --- |
| 4 | Score-only opponent-adjusted efficiency and schedule strength | `2026 ROI: 10.11% -> 5.56%`, DD `6.79% -> 9.13%` | worse ROI and worse drawdown before a full-window test | reverted |
| 5 | Microstructure features as direct model inputs | `2026` improved, full-window ROI `7.34% -> 6.14%` | improved latest season but broke `2025` | reverted |
| 6 | Coverage-rate survivability gate | `2026 ROI: 10.11% -> 8.14-8.63%` | cut good activity immediately | reverted |
| 7 | Phase-specific betting thresholds | full-window ROI `7.34% -> 3.83%`, DD `10.49% -> 20.88%` | reopened too much weak activity, especially `2025` | reverted |
| 8 | Nonlinear residual ensemble | `2026` gate did not finish in reasonable runtime | runtime cost failed before quality was proven | reverted |
| 9 | Conformal abstention band | `2026` gate collapsed from `232` candidates to `0` bets | reject-option design was far too conservative | reverted |
| 11 | Prior-window selective abstention / kill-switch | no promotable result; activation evidence weak | small bad slices still had positive close EV | reverted |
| 12 | Book-depth adaptive recalibration | `2026 ROI: 10.11% -> 8.06%`, DD `6.79% -> 7.43%` | same-signal recalibration regressed at the gate | reverted |
| 15 | Neutral-site / postseason features on stored ESPN context | `2026 ROI: 9.68% -> 10.91%`, DD `6.79% -> 5.23%`; full-window ROI `7.18% -> 6.54%` | improved latest season but lost aggregate ROI and activity, with too few neutral/postseason qualified bets | reverted |

## Failure Pattern Diagnosis

The failure pattern is now specific enough that the next roadmap should stop
hedging.

### 1. Structural model experiments are failing on information, not only on tuning

The repo still does not model:

- player availability outside market proxies
- lineup continuity
- transfer shocks
- coaching changes
- reproducible team home location, travel, altitude, and timezone context
- neutral-site and postseason context inside the model itself

That is enough information to support a market-anchored residual model. It has
not been enough to justify more expressive model classes.

### 2. `2025` remains the stability canary

Most failed experiments looked acceptable in `2026` and then broke on the full
window because `2025` degraded.

That means:

- latest-season improvement should not drive roadmap priorities
- new experiments need to survive the `2025` regime to be credible
- stability matters more than squeezing out more activity in `2026`

### 3. The remaining edge still looks execution-driven more than line-prediction-driven

The current baseline has:

- negative spread line CLV
- positive spread price CLV
- positive spread no-vig close delta
- positive spread close EV

That combination fits a system whose signal comes from:

- market-relative repricing
- best-quote selection
- cross-book dispersion
- conservative uncertainty control

It does not fit a system that is reliably beating the raw spread number.

### 4. The current segment and tail tables still do not justify a kill-switch

The report now includes both segment attribution and accepted-bet tail tables.
They still do not show a clean bad region that is both negative on realized ROI
and negative on spread close EV.

Examples from the current report:

- `Mid Depth`: `16` bets, ROI `-12.15%`, close EV `+0.091`
- `Non-Conference`: `50` bets, ROI `-0.76%`, close EV `+0.064`
- `Unknown` conference group: `8` bets, ROI `-21.22%`, close EV `+0.043`
- expected value `8% to 10%`: `81` bets, ROI `-0.48%`, close EV `+0.142`

Those slices are either:

- too small to support a stable block rule
- or still positive on close EV, which suggests noise or timing/execution
  mismatch rather than a cleanly bad segment

Inference from local evidence:

- segment attribution and tail views are useful as evaluation
- segment abstention is not currently justified as the next live experiment

### 5. Same-slate concentration is now the clearest remaining repo-local policy lane

The refreshed dashboard snapshot exposes a pattern that was only implicit in
the season summaries:

- the current baseline has `57` days with `5+` qualified bets
- those heavier slates are still positive in aggregate, but only at `+3.44%`
  ROI versus `+27.14%` on one-bet days
- the weakest season, `2024`, was materially worse on those heavy slates:
  `111` bets on `17` days at `-13.02%` ROI
- the worst `2024` drawdown clusters were concentrated in those January and
  February multi-bet slates rather than in isolated one-off picks

Bounded local replay from the current snapshot suggests a simple same-day
top-of-board cap is worth a real walk-forward test:

- keeping the top `6` bets per day by current board rank would have reduced the
  historical bet count from `570` to roughly `536`
- that rough replay improved aggregate ROI from `+7.18%` to roughly `+7.34%`
  while also improving the weak `2024` season from roughly `-8.76%` to
  `-6.68%`

That replay is not a promotion result because it reuses settled rows rather
than rerunning the walk-forward engine, but it is strong enough to justify one
explicit repo-local policy experiment.

### 5. Phase and timing policy work has low leverage under the current baseline

The current qualified spread bets are all:

- `Established` season phase
- `0 to 6h` tip window

That means a lot of the older roadmap surface area is functionally inactive
under the promoted baseline. More phase-threshold work is not a high-value use
of time until the system actually reopens earlier-window activity.

### 6. Close-based evaluation quality is now important enough to become roadmap work

The current report interpretation relies heavily on price CLV, no-vig close
delta, and close EV. That remains correct, but recent bounded local diagnostics
also found a material number of unmatched recent historical close candidates in
the database repair workflow.

Local implication:

- this does not invalidate the current report
- it does mean close-based evaluation quality should be treated as explicit
  supporting infrastructure, not an invisible assumption
- if close EV is the main evidence of edge, then close matching and coverage
  quality deserve real roadmap priority

## Fresh External Research

The refreshed outside evidence reinforces the shift away from generic
structural complexity and toward calibration quality, robust evaluation, and
new information.

### Calibration, Tails, and Distribution Shift

- [Machine learning for sports betting: Should model selection be based on accuracy or calibration?](https://doi.org/10.1016/j.mlwa.2024.100539)
  shows calibration matters more than raw accuracy for sports betting
  profitability.
- [Tail Calibration of Probabilistic Forecasts](https://www.tandfonline.com/doi/full/10.1080/01621459.2025.2506194)
  argues that ordinary calibration diagnostics miss important reliability
  failures in the extremes. That matters here because accepted bets live in the
  tail of model-versus-market disagreement.
- [Regression Recalibration by Learning PIT Map Values](https://www.tandfonline.com/doi/full/10.1080/00401706.2025.2464004)
  reinforces that recalibration is a distinct modeling layer and can improve
  reliability without changing the base model family.
- [Multiaccuracy for Subpopulation Calibration Over Distribution Shift in Medical Prediction Models](https://proceedings.mlr.press/v287/kapash25a.html)
  is outside sports, but it is relevant evidence that post-processing
  calibration can remain useful across shifted subpopulations when those
  subpopulations are stable and well-defined.
- [Evaluating calibration of deep fault diagnostic models under distribution shift](https://www.sciencedirect.com/science/article/abs/pii/S0166361525000995)
  supports the broader point that calibration under shift is a separate problem
  from raw accuracy and should be evaluated explicitly on shifted data.

Implication for this repo:

- calibration still matters more than accuracy
- but the next high-value lane is no longer another same-signal recalibration
  variant unless it has a stronger target than the ones already tried
- tail evaluation remains important as a diagnostic layer even when it does not
  justify a live abstention rule

### Market Efficiency and Execution

- [Comparing two methods for testing the efficiency of sports betting markets](https://www.sciencedirect.com/science/article/pii/S2773161824000193)
  argues efficiency tests should use normalized no-vig probabilities rather
  than naive inverse-odds transforms.
- [Efficiency of online football betting markets](https://www.sciencedirect.com/science/article/pii/S0169207018301134)
  remains one of the clearest pieces of evidence that best-odds selection
  across bookmakers is where residual bettor edge is most plausible.
- [Are Betting Markets Inefficient? Evidence From Simulations and Real Data](https://econpapers.repec.org/article/saejospec/v_3a25_3ay_3a2024_3ai_3a1_3ap_3a54-97.htm)
  is a strong warning that isolated seasonal inefficiencies often do not
  persist and can appear even in efficient markets.

Implication for this repo:

- keep price/no-vig/close-EV diagnostics first-class
- keep treating raw line CLV as incomplete for this system
- do not promote changes that mainly improve one season or one apparent slice

### News, Event Extraction, and Real-Time Forecasting

- [A Systematic Review of Machine Learning in Sports Betting: Techniques, Challenges, and Future Directions](https://arxiv.org/abs/2410.21484)
  points toward multimodal and real-time information as the next major gain
  area, with data quality and reproducibility as the key bottlenecks.
- [From News to Forecast: Integrating Event Analysis in LLM-Based Time Series Forecasting with Reflection](https://doi.org/10.48550/arXiv.2409.17515)
  supports structured event analysis rather than naive use of raw news text.
- [ForestCast: Open-Ended Event Forecasting with Semantic News Forest](https://aclanthology.org/2025.findings-emnlp.678/)
  also points toward extracted event structure, not generic sentiment, as the
  stronger way to use news.

Implication for this repo:

- if the project explores news, it should prioritize retrieval plus structured
  event extraction
- generic sentiment is the wrong first design
- new information should be explicit and verifiable: player availability,
  suspensions, coaching changes, and venue/travel disruption context

### OpenAI Product / API Guidance for a News Pipeline

Official OpenAI documentation makes a bounded news-extraction workflow
technically feasible, but it does not remove the historical reproducibility
problem.

- [Web search guide](https://developers.openai.com/api/docs/guides/tools-web-search)
  supports cited web retrieval inside the Responses API.
- [Function calling guide](https://developers.openai.com/api/docs/guides/function-calling)
  supports tool-using workflows that connect models to external data and strict
  schemas.
- [Structured outputs guide](https://platform.openai.com/docs/guides/structured-outputs)
  supports schema-constrained extraction and recommends strict schema
  adherence.

Implication for this repo:

- a bounded LLM pipeline is feasible as an engineering workflow
- feasibility does not make it a near-term backtestable alpha source
- historical reproducibility is still the hardest problem

### NCAA-Specific Market Structure and Data Availability

- [NCAA releases penalty and process details for March Madness player availability reports](https://www.ncaa.org/news/2026/3/4/media-center-ncaa-releases-penalty-and-process-details-for-march-madness-player-availability-reports.aspx)
  makes official tournament availability data real, public, and bounded for
  2026 championships.
- [NCAA asks states to ban player props and first-half under betting on college sports](https://www.ncaa.org/news/2026/1/15/media-center-ncaa-asks-states-to-ban-player-props-and-first-half-under-betting-on-college-sports.aspx)
  reinforces that college basketball integrity issues are concentrated in
  exactly the kinds of granular markets and information asymmetries this repo
  should avoid overfitting to.

Implication for this repo:

- official NCAA availability reporting is the best immediate public-information
  lane
- this strengthens the case for bounded, official, verifiable NCAA-specific
  data acquisition before a broad live news pipeline

## Adaptive Recalibration vs New NCAA Information

This is now the key strategic choice.

| Lane | Assessment | Why |
| --- | --- | --- |
| Another same-signal adaptive recalibration experiment on the current stored features | `Conditional only` | the first post-refresh recalibration attempt already failed the gate |
| Segment attribution and tail diagnostics as evaluation | `GO` | useful evaluation layer, already promoted |
| Segment abstention / kill-switch as the next live experiment | `NO-GO for now` | current bad slices are too small and still positive on close EV |
| Neutral-site / postseason feature experiment on newly stored ESPN context | `GO` | new, reproducible information with low runtime risk is now the strongest next lane |
| Closing-line matching and close-based evaluation hardening | `GO` | close EV is too central to leave its data quality implicit |
| Official NCAA tournament availability integration | `GO` | bounded, public, and directly relevant missing information |

Current decision:

- adaptive recalibration is demoted from "next experiment" to a later revisit
- segment abstention remains demoted
- the roadmap should now prioritize new NCAA information and evaluation quality
  over more tuning of the same probability pipeline

Condition for revisiting adaptive recalibration later:

- only after either:
  - new NCAA information creates stable, better-separated prediction regions, or
  - improved evaluation shows a persistent, adequately sampled region with both
    weak ROI and weak close EV

## LLM / News Pipeline Feasibility

The news idea remains promising enough to keep, but only in a narrow form.

### Could a ChatGPT / OpenAI API news pipeline create useful NCAA signals?

Yes, but only if it is framed as structured public-information extraction, not
as generic sentiment or free-form summaries.

The strongest candidate signal classes are:

- player availability and late scratches
- suspensions and disciplinary news
- coaching changes or absences
- venue, travel, or weather disruption context
- bounded postseason news where official or archived sources exist

The weakest candidate lane is:

- generic pregame sentiment

Inference from the outside literature and the repo's failure pattern:

- structured event extraction is more plausible than sentiment because this
  repo needs explicit missing information, not another noisy soft signal

### Best Positioning

| Design | Assessment | Why |
| --- | --- | --- |
| Official NCAA tournament availability feed | `GO` | verifiable, bounded, high-value, backtestable once stored |
| LLM-assisted retrieval plus structured extraction from public news | `Research-only GO` | feasible to build, but historical reproducibility is weak today |
| Tournament-only overlay using archived sources | `Conditional GO` | bounded scope and easier verification |
| Whole-season live dependency on broad web news | `NO-GO for now` | hard to reproduce historically and easy to contaminate with leakage |
| Generic sentiment feature | `NO-GO` | weak causal mapping, high noise, poor auditability |

### Recommended Design if This Lane Is Pursued

1. retrieve relevant public articles with preserved source URLs, titles,
   timestamps, and provider metadata
2. use function calling or structured outputs to extract a strict event schema
3. keep only verifiable fields such as team, player, event type, expected game
   impact window, and source count
4. store the raw retrieval record so later backtests can replay exactly what
   was seen pre-tip
5. treat the first version as shadow logging or a bounded tournament overlay,
   not as a production feature

### Key Risks

- leakage:
  article and extraction timestamps must be strictly pre-tip and archived
- latency:
  same-day slates make manual or multi-hop extraction risky
- cost:
  web search and model calls are real recurring cost, not free metadata
- instability:
  source coverage changes over time
- hallucinated signals:
  unverifiable free-text summaries are not acceptable inputs
- historical reproducibility:
  this is the biggest blocker for promotion into walk-forward testing

Bottom line on this lane:

- `in` as a research-only data-acquisition path
- `out` as the immediate next promoted model experiment
- `out` for generic sentiment

## Revised Ranked Ideas

The ranking below is now based on both the repo evidence and the refreshed
outside research.

| Rank | Idea | Category | Status | Why it moved |
| --- | --- | --- | --- | --- |
| 1 | Closing-line matching and close-based evaluation-quality hardening | Evaluation / Data | approved | after the neutral/postseason model failure, this is the highest-value remaining repo-local lane and it can be advanced with repo-local code changes |
| 2 | Official NCAA player-availability integration, starting with March Madness reporting | Data | needs follow-up | still the best plausible baseline-improvement lane, but it depends on a bounded official source and replayable ingest design |
| 3 | Team home-location data foundation, then travel / altitude / timezone features | Data / Feature | needs follow-up | still promising, but blocked until the repo has a reproducible, auditable location source |
| 4 | Correlated exposure caps by conference, slate window, and regime | Policy | approved | the seeded snapshot now shows concentrated losses on heavy same-day slates, so a small explicit same-day cap is worth one repo-local walk-forward test |
| 5 | Prospective LLM-assisted news retrieval plus structured event extraction with archived sources | Data / Research | deferred | viable shadow research later, but not the next production-facing use of time |
| 6 | Neutral-site and postseason features on the stored ESPN venue / season-type context | Feature | rejected | first modeling pass improved `2026`, but failed the full window on ROI and activity |
| 7 | Segment attribution and tail diagnostics | Evaluation | deferred | useful diagnostics already retained in the report, but not an active new implementation lane |
| 8 | Adaptive recalibration revisit after new data or stronger stable segments exist | Model / Evaluation | deferred | conceptually valid, but the current signal set does not justify another recalibration pass now |
| 9 | Market microstructure as attribution or filter support rather than direct model expansion | Evaluation / Policy | deferred | direct feature expansion already failed the full window, so keep this as evaluation support only |
| 10 | Segment abstention / kill-switch logic | Policy | rejected | current bad slices do not justify it |
| 11 | Static nonlinear residual ensembles on the current feature set | Model | rejected | runtime too high and evidence too weak |
| 12 | Score-only opponent-adjusted efficiency rebuilds | Feature | rejected | failed on the current information set |
| 13 | Generic conformal or reject-option gating | Model | rejected | zero-activity failure and weak local support |
| 14 | More same-signal phase-threshold or survivability retuning | Policy | rejected | both tightening and reopening already failed locally |
| 15 | Generic news sentiment features | Feature | rejected | weak auditability and weak causal mapping |

## Implementation Status

The research ranking above mixes immediate repo-local work with longer-horizon
data lanes. For implementation, use only the explicit statuses below.

### M-1: Closing-line matching and close-based evaluation hardening

Status: approved
Implementation: completed `2026-03-12`

Reason:
This is the highest-value repo-local item, and it directly supports the
report's main evidence chain around close EV, no-vig close delta, and price
CLV.

Delivered:
- `cbb model report` now surfaces close-market coverage near the assessment
- the generated report now includes a dedicated close-market coverage section
  before the detailed CLV table

### M-2: Official NCAA player-availability integration

Status: needs follow-up

Reason:
The idea is strong, but implementation needs a concrete data source, storage
plan, replay semantics, and a bounded first workflow before code should change.

### M-3: Team home-location foundation and travel / altitude / timezone features

Status: needs follow-up

Reason:
This remains blocked on a reproducible team-location source and auditable data
backfill plan.

### M-4: Correlated exposure caps

Status: approved
Implementation: completed `2026-03-12`

Reason:
The latest seeded snapshot shows a concrete same-slate concentration problem in
the weak season, especially on `5+` bet days. That makes a minimal same-day
cap the clearest remaining repo-local baseline-improvement experiment.

Implementation-ready first pass:

- add an explicit optional `max_bets_per_day` spread-policy control
- keep the first experiment narrow: one same-day cap only, with no conference
  or regime branching yet
- rank same-day candidates exactly the way the current bankroll limiter
  already does, then stop after the cap
- keep the live, backtest, report, and dashboard paths aligned through the
  shared policy object

Delivered:

- the deployable spread policy now applies an explicit `max_bets_per_day=6`
  cap after same-day candidates are ranked by the existing top-of-board sort
- the live prediction path, backtest path, report output, CLI summaries, and
  dashboard snapshot contract all now carry that policy field consistently
- the promoted full-window result moved from `+7.18%` ROI / `10.49%` drawdown
  on `570` bets to `+7.20%` ROI / `8.78%` drawdown on `536` bets

### M-5: Prospective LLM-assisted news retrieval and structured extraction

Status: needs follow-up

Reason:
The repo can support a bounded shadow pipeline, but archival reproducibility,
cost, and exact source policy need a narrower design before implementation.

### M-6: Neutral-site and postseason features on stored ESPN context

Status: rejected

Reason:
The first full-window experiment failed promotion and should not be advanced as
the active next lane.

### M-7: Segment attribution and tail diagnostics

Status: deferred

Reason:
These are already useful evaluation layers. They should be maintained, but they
are not the main implementation target for this run.

### M-8: Adaptive recalibration revisit

Status: deferred

Reason:
The latest same-signal recalibration attempt regressed at the gate. Revisit
only after new information or stronger stable segments exist.

### M-9: Market microstructure as attribution or filter support

Status: deferred

Reason:
Direct model expansion already failed. This can return later as attribution or
supporting filter work after the approved evaluation hardening lands.

### M-10: Segment abstention / kill-switch logic

Status: rejected

Reason:
Current bad slices are too small and still positive on close EV.

### M-11: Static nonlinear residual ensembles

Status: rejected

Reason:
Runtime cost is too high relative to current evidence.

### M-12: Score-only opponent-adjusted efficiency rebuilds

Status: rejected

Reason:
This failed on the current information set and should not be recycled as an
immediate next step.

### M-13: Generic conformal or reject-option gating

Status: rejected

Reason:
The prior design collapsed activity without proving a useful precision gain.

### M-14: More same-signal phase-threshold or survivability retuning

Status: rejected

Reason:
Both tightening and reopening already failed locally.

### M-15: Generic news sentiment features

Status: rejected

Reason:
This repo needs explicit, auditable event information rather than soft
sentiment features.

## Top 5 Experiments Now

### 1. Close-Based Evaluation Hardening

Status: approved

- objective:
  make the repo's main validation signal more trustworthy before optimizing
  around it further
- minimal design:
  - quantify close-coverage and unmatched-close rates in the canonical report
    path
  - diagnose whether remaining missing closes are provider absence, matching
    brittleness, or timestamp-window issues
  - improve bet-relevant close coverage if a small, local fix is justified
- success criteria:
  - clearer coverage accounting in the report path
  - lower unmatched-close rate where locally fixable
  - no distortion of existing canonical metrics

### 2. Tournament Availability Overlay

Status: needs follow-up

- objective:
  test whether bounded official availability information helps more than model
  complexity
- minimal design:
  - start with official NCAA March Madness availability reporting
  - keep the first version as a bounded postseason overlay or feature source
  - preserve exact timestamps and statuses for replayability
- success criteria:
  - better late-season and tournament segment results
  - no degradation of the regular-season baseline

### 3. Team Home-Location Foundation and Travel Features

Status: needs follow-up

- objective:
  unlock the next reproducible NCAA-information lane after availability data
- minimal design:
  - store durable team home coordinates and timezone data
  - derive travel distance, timezone shift, and altitude-change features
  - do not proceed until the home-location source is reproducible and auditable
- success criteria:
  - feature availability across the full stored history
  - no hidden manual data dependencies
  - credible walk-forward improvement after the data foundation exists

### 4. Correlated Exposure Caps

Status: approved

- objective:
  reduce same-slate drawdown concentration without breaking the execution-aware
  edge that still survives on the full window
- minimal design:
  - add one explicit same-day cap first
  - prefer a fixed top-of-board cap over conference-specific or regime-specific
    logic in the first pass
  - keep the cap small enough that activity does not collapse on normal slates
- success criteria:
  - full-window ROI improves meaningfully, or stays flat while drawdown
    improves materially
  - the weak `2024` season improves
  - activity remains realistic

### 5. Prospective News Shadow Pipeline

Status: deferred

- objective:
  build historical reproducibility for future public-information research
- minimal design:
  - retrieve and archive pregame articles for a bounded slate
  - extract structured event records with a strict schema
  - do not feed it into the model yet
- success criteria:
  - deterministic archived records
  - acceptable latency and cost
  - enough signal quality to justify a later prospective study

## What To Stop Trying For Now

These are not permanently impossible. They are the wrong use of time now.

- stop treating segment abstention as the top policy idea
  The current segment evidence is too weak to justify a kill-switch.

- stop treating same-signal adaptive recalibration as the default next move
  One more variant already failed, and the best new information lane is now
  available in stored data.

- stop trying static nonlinear ensembles on the current feature set
  They add runtime cost without proving stable walk-forward value.

- stop trying generic conformal reject bands
  The local failure mode was zero activity, not selective precision.

- stop trying score-only structural team-strength rebuilds
  They do not solve the missing-information problem.

- stop trying more global threshold-tightening or threshold-reopening
  Both directions already failed locally.

- stop trying generic news sentiment features
  The repo needs explicit missing information, not a noisy soft feature.

- stop trying unsourced LLM summaries as model inputs
  Without preserved sources and strict extraction, they are not auditable or
  reproducible enough for walk-forward research.

## Revised Phase Roadmap

### Phase 1: New NCAA Context and Better Evaluation

- close-line matching and close-based evaluation hardening
- keep the failed neutral-site / postseason model pass as a conditional revisit,
  not the active next lane
- keep segment attribution and tail diagnostics as evaluation, not as live
  abstention

Expected impact:

- better confidence in the repo's main validation signals
- less time spent overfitting the same stored probability pipeline before new
  external NCAA data exists

### Phase 2: Verifiable NCAA Information Expansion

- official NCAA tournament player-availability integration
- team home-location data foundation
- travel / altitude / timezone features once the data foundation exists
- correlated exposure caps can stay active if the same-slate cap clears the
  bar; deeper conference/regime caps still belong later

Expected impact:

- more genuine information edge than additional model complexity on stale data
- still operationally manageable and reproducible

### Phase 3: Prospective Public-Information Capture

- build archived pregame news retrieval for bounded slates
- use structured extraction for verifiable events only
- only after that, consider adding those features to a live or backtest path
- revisit adaptive recalibration only after new information creates stronger
  stable segments

Expected impact:

- this is the first path that could justify another structural-model pass later
- until archival and reproducibility exist, it remains a research lane, not a
  deployment lane

## Next Best Experiment

### Official NCAA Player-Availability Integration

Why this is next:

- the same-day exposure-cap experiment already captured the clearest remaining
  repo-local policy improvement
- the current promoted baseline now has better drawdown and a less-bad `2024`,
  but the edge still looks execution-driven more than information-driven
- the next realistic baseline-moving lane is new NCAA-specific information, not
  another tuning pass on the same stored features
- official NCAA tournament availability reporting is the most bounded and
  auditable missing-information source currently on the board

Exact research question:

- can a replayable official tournament availability overlay improve the late-
  season and championship window without degrading the regular-season baseline?

Current status:

- this is the highest-value remaining lane, but it still needs a concrete
  source contract, storage plan, and replay design before implementation
- the repo-local policy lane is now largely exhausted
- travel distance, altitude, and timezone-change features remain blocked by
  missing reproducible team home-location data

Coordinator review after the latest promoted baseline:

- all currently approved repo-local items are now completed
- no additional repo-local model or policy item is implementation-ready under
  the current roadmap without either new external NCAA data or a new
  reproducible location source
- the correct stop condition for this phase is to preserve the promoted
  baseline and defer further model changes until one of the `needs follow-up`
  data lanes is designed well enough to become approved

## Bottom Line

The core diagnosis is now:

- the repo has already harvested the clearest wins from calibration and
  uncertainty control
- the current edge still looks more execution- and calibration-driven than raw
  line-prediction-driven
- the latest same-signal recalibration attempt failed the gate
- the current segment and tail evidence does not support a kill-switch
- the current seeded snapshot now supports one bounded same-slate exposure-cap
  test as the best remaining repo-local live experiment
- that same-day cap has now been promoted because it kept ROI effectively flat
  while materially reducing max drawdown and improving the weak `2024` season
- structural model experiments are still underperforming because the current
  non-market information set is too weak
- the first neutral-site / postseason feature pass did not clear the full
  window, so stored venue/season-type context alone is not enough
- close-based evaluation quality should be treated as explicit roadmap work
  because close EV is now central to the repo's interpretation of edge
- the next plausible baseline-moving lane is official NCAA tournament
  availability data rather than another same-signal modeling tweak
- the most promising longer-horizon new lane is not generic sentiment, but
  bounded, verifiable public-information extraction

That means the near-term roadmap is now:

1. harden close-line matching and close-based evaluation quality
2. add real new NCAA information after that, starting with official tournament
   availability
3. extend to travel / altitude / timezone only after reproducible team
   home-location data exists
4. consider correlated exposure caps only if drawdown becomes the main weakness
   again
5. keep public-news capture in shadow mode until archival reproducibility is in
   place

It deprioritizes:

- further same-signal spread-calibration variants on the current stored
  information set
- segment kill-switch work
- static nonlinear ensembles
- generic conformal reject options
- score-only structural team-strength features
- generic news sentiment

## Research Log

### Experiment 10: Segment Attribution for Qualified Spread Bets

Hypothesis

- Adding segment-level attribution to the canonical backtest and report will
  show whether the current qualified spread losses are actually concentrated in
  a small set of regimes, without changing the promoted baseline itself.

Implementation

- Added stable spread segment metadata to candidate and placed bets so the
  walk-forward path can summarize:
  - season phase
  - spread line bucket
  - spread book-depth bucket
  - same-conference vs nonconference
  - conference group
  - tip window
- Extended backtest summaries with spread segment attribution tables keyed off
  realized ROI and spread closing EV.
- Extended `cbb model report` output to render aggregate spread segment
  attribution from the canonical report path.

Files changed

- [src/cbb/modeling/policy.py](../src/cbb/modeling/policy.py)
- [src/cbb/modeling/backtest.py](../src/cbb/modeling/backtest.py)
- [src/cbb/modeling/report.py](../src/cbb/modeling/report.py)
- [tests/test_modeling.py](../tests/test_modeling.py)
- [tests/test_report.py](../tests/test_report.py)
- [README.md](../README.md)
- [docs/model.md](model.md)
- [docs/architecture.md](architecture.md)
- [docs/results/best-model-3y-backtest.md](results/best-model-3y-backtest.md)

Backtest results

- `2026` gate: unchanged at `206` bets, `+$143.34`, ROI `+10.11%`, max
  drawdown `6.79%`, spread close EV `+0.094`
- full window: unchanged at `569` bets, `+$282.70`, ROI `+7.34%`, max
  drawdown `10.49%`, profitable seasons `2/3`
- aggregate segment findings:
  - line bucket: `priced_range` remained strongest at `+15.86%` ROI and
    `+0.060` close EV; `tight` stayed positive at `+3.57%` ROI and `+0.093`
    close EV
  - book depth: `mid_depth` was negative ROI at `-12.15%` on `16` bets, but
    still had positive close EV at `+0.091`
  - conference matchup: `nonconference` was slightly negative at `-0.76%` on
    `50` bets, but still had positive close EV at `+0.064`
  - conference group: `unknown` was negative at `-21.22%` on `8` bets, but
    still had positive close EV at `+0.043`
  - season phase and tip window were degenerate under the current baseline:
    all qualified bets were `established` and `0 to 6h`
- `2026` only, the same pattern held:
  - `mid_depth`: `11` bets, ROI `-19.74%`, close EV `+0.105`
  - `nonconference`: `5` bets, ROI `-72.22%`, close EV `+0.038`

Tradeoffs

- The canonical report is longer because it now includes aggregate segment
  attribution tables.
- The added tables are diagnostic only; they do not imply causal market
  structure on their own.

Conclusion

- Promoted.
- This remains a useful evaluation improvement, but it weakened the case for a
  blunt segment kill-switch because no current aggregate segment is both
  negative on ROI and negative on close EV.

### Experiment 11: Prior-Window Selective Abstention / Kill-Switch

Hypothesis

- A prior-window segment filter that blocks only small segments with negative
  ROI and negative spread close EV should improve stability without materially
  reducing activity.

Implementation

- Built a research-only walk-forward abstention path that replayed prior blocks
  and attempted to disable at most one segment when it met:
  - negative prior-window ROI
  - negative prior-window spread close EV
  - minimum sample
  - maximum share-of-bets cap
- The experiment was intentionally kept off the promoted baseline and was
  removed after evaluation.

Files changed

- temporary research edits in:
  - [src/cbb/modeling/backtest.py](../src/cbb/modeling/backtest.py)
  - [src/cbb/modeling/report.py](../src/cbb/modeling/report.py)
  - [tests/test_modeling.py](../tests/test_modeling.py)
- no selective-abstention code remains in the retained baseline after reversion

Backtest results

- `2026` gate did not finish in a reasonable time on the local walk-forward
  loop before quality was proven, so no promotable bankroll result was
  accepted.
- The attribution pass that preceded it already showed no aggregate segment
  with both negative ROI and negative close EV, which meant the filter had
  weak activation evidence before the runtime cost was paid.

Tradeoffs

- The research implementation added extra walk-forward replay cost before it
  showed any real edge.
- On the current baseline, the likely candidate segments were either too small
  or still positive on close EV, so the filter risked becoming an expensive
  no-op.

Conclusion

- Reverted.
- This lane is now demoted. Do not advance this exact kill-switch design again
  unless a later recalibration or new-data experiment surfaces a segment that
  is bad on both realized ROI and close EV with adequate sample size.

### Experiment 12: Spread Book-Depth Adaptive Recalibration

Hypothesis

- Adding spread book-depth-specific market-blend and max-market-delta
  calibrations should improve robustness under changing NCAA market quality
  without changing the core residual model or live policy thresholds.

Implementation

- Added a research-only spread book-depth calibration layer keyed off the
  existing stable depth buckets:
  - `low_depth`
  - `mid_depth`
  - `high_depth`
- Threaded those calibrations through spread artifact loading, spread scoring,
  and targeted regression tests.
- The experiment was reverted after gate evaluation.

Files changed

- temporary research edits in:
  - [src/cbb/modeling/artifacts.py](../src/cbb/modeling/artifacts.py)
  - [src/cbb/modeling/train.py](../src/cbb/modeling/train.py)
  - [tests/test_artifacts.py](../tests/test_artifacts.py)
  - [tests/test_modeling.py](../tests/test_modeling.py)
- no book-depth calibration code remains in the retained baseline after
  reversion

Backtest results

- baseline `2026` gate before the experiment: `206` bets, `+$143.34`, ROI
  `+10.11%`, max drawdown `6.79%`, spread close EV `+0.094`
- experiment `2026` gate: `208` bets, `+$109.91`, ROI `+8.06%`, max drawdown
  `7.43%`, spread close EV `+0.094`
- because the gate regressed on both profit and drawdown, the experiment was
  not advanced to the full 3-season report

Tradeoffs

- The design stayed additive and cheap to evaluate, but it increased runtime
  enough that the gate was not a free comparison.
- The added book-depth calibration did not improve close EV; it mainly changed
  which marginal spread bets qualified.

Conclusion

- Reverted.
- Stable-segment recalibration is still the right lane, but this specific
  book-depth-only version did not clear the gate and should not become the
  deployable baseline.

### Experiment 13: Tail Diagnostics for Qualified Spread Bets

Hypothesis

- Adding qualified-bet tail diagnostics for expected value and probability edge
  will show whether the accepted spread edge is concentrated in a specific tail
  region and whether that region is bad on both ROI and spread close EV.

Implementation

- Extended the existing spread segment attribution path to bucket qualified
  spread bets by:
  - expected value
  - probability edge
- Reused the canonical backtest and report machinery so the new tail buckets
  appear beside the existing line, depth, conference, and timing tables.

Files changed

- [src/cbb/modeling/policy.py](../src/cbb/modeling/policy.py)
- [src/cbb/modeling/report.py](../src/cbb/modeling/report.py)
- [tests/test_modeling.py](../tests/test_modeling.py)
- [tests/test_report.py](../tests/test_report.py)
- [README.md](../README.md)
- [docs/model.md](model.md)
- [docs/architecture.md](architecture.md)
- [docs/results/best-model-3y-backtest.md](results/best-model-3y-backtest.md)

Backtest results

- `2026` gate: unchanged at `206` bets, `+$143.34`, ROI `+10.11%`, max
  drawdown `6.79%`, spread close EV `+0.094`
- full window: unchanged at `569` bets, `+$282.70`, ROI `+7.34%`, max
  drawdown `10.49%`, profitable seasons `2/3`
- aggregate tail findings:
  - expected value bucket:
    - `4% to 6%`: `256` bets, ROI `+10.11%`, close EV `+0.037`
    - `6% to 8%`: `189` bets, ROI `+7.81%`, close EV `+0.095`
    - `8% to 10%`: `81` bets, ROI `-0.48%`, close EV `+0.142`
    - `10%+`: `43` bets, ROI `+10.16%`, close EV `+0.193`
  - probability edge bucket:
    - `4% to 6%`: `443` bets, ROI `+7.55%`, close EV `+0.067`
    - `6% to 8%`: `112` bets, ROI `+2.79%`, close EV `+0.131`
    - `8% to 10%`: `13` bets, ROI `+18.26%`, close EV `+0.200`
    - `10%+`: `1` bet, too small to drive a policy conclusion

Tradeoffs

- The canonical report is longer because the aggregate tail tables now sit
  alongside the older spread segment tables.
- The new diagnostics are still attribution only; they do not by themselves
  justify a live filter or threshold change.

Conclusion

- Promoted as evaluation.
- The added tail view did not reveal a segment that is bad on both realized ROI
  and close EV, so it did not justify another immediate recalibration or
  abstention experiment on the current stored data.

### Experiment 14: Venue / Neutral-Site / Postseason Data Foundation

Hypothesis

- The next roadmap lane needs stored walk-forward-ready venue and postseason
  context before any new NCAA-information experiment is meaningful, so the
  smallest useful step is to persist ESPN neutral-site, season-type, tournament
  note, and venue metadata in `games`, backfill it across the stored history,
  and extend audit coverage to validate those fields.

Implementation

- Added additive `games` columns for:
  - `neutral_site`
  - `conference_competition`
  - `season_type`
  - `season_type_slug`
  - `tournament_id`
  - `event_note_headline`
  - `venue_id`
  - `venue_name`
  - `venue_city`
  - `venue_state`
  - `venue_indoor`
- Extended ESPN historical ingest to extract those fields from scoreboard
  events.
- Updated game upserts so Odds API refreshes do not erase existing ESPN-derived
  venue/postseason context with nulls.
- Extended `cbb db audit` to validate stored context in addition to coverage,
  status, and scores.
- Backfilled the full stored game window and refreshed the canonical docs that
  describe ingest and stored data behavior.

Files changed

- [sql/schema.sql](../sql/schema.sql)
- [src/cbb/ingest/historical.py](../src/cbb/ingest/historical.py)
- [src/cbb/ingest/persistence.py](../src/cbb/ingest/persistence.py)
- [src/cbb/verify.py](../src/cbb/verify.py)
- [src/cbb/cli.py](../src/cbb/cli.py)
- [tests/test_historical_games.py](../tests/test_historical_games.py)
- [tests/test_verify.py](../tests/test_verify.py)
- [tests/test_persistence.py](../tests/test_persistence.py)
- [tests/test_odds_api.py](../tests/test_odds_api.py)
- [tests/test_cli.py](../tests/test_cli.py)
- [README.md](../README.md)
- [docs/model.md](model.md)
- [docs/architecture.md](architecture.md)

Backfill results

- schema initialized with `cbb db init` on March 11, 2026
- full ESPN force-refresh run:
  - command:
    `./.venv/bin/python -m cbb.cli ingest data --start-date 2023-03-08 --end-date 2026-03-13 --force-refresh`
  - result: `1102` dates requested, `19005` upstream games seen, `17439`
    games inserted, `1566` skipped
- targeted live-window repairs:
  - March 12, 2026:
    `./.venv/bin/python -m cbb.cli ingest data --start-date 2026-03-12 --end-date 2026-03-12 --force-refresh`
  - March 11, 2026:
    `./.venv/bin/python -m cbb.cli ingest data --start-date 2026-03-11 --end-date 2026-03-11 --force-refresh`
- stored-window coverage after backfill:
  - `17439` games across seasons `2023` to `2026`
  - `17437` games (`99.99%`) with non-null neutral-site, conference,
    season-type, and venue fields
  - `2271` neutral-site games
  - `356` postseason games (`season_type = 3`)
  - `1963` games with `tournament_id`
  - `2863` games with `event_note_headline`
- the two remaining null-context rows are synthetic Odds API duplicates whose
  canonical ESPN rows exist elsewhere on shifted UTC dates:
  - March 5, 2026 Memphis vs South Florida synthetic row; canonical ESPN row
    stored on March 6, 2026 as event `401828260`
  - March 12, 2026 Southern vs Arkansas-Pine Bluff synthetic row; canonical
    ESPN row stored on March 13, 2026 as event `401851720`

Audit / validation results

- targeted tests:
  `./.venv/bin/pytest -q tests/test_historical_games.py tests/test_verify.py tests/test_persistence.py tests/test_odds_api.py tests/test_cli.py`
  passed (`51` tests)
- repo verification:
  - `pytest -q` passed (`135` tests)
  - `ruff check src tests` passed
  - `mypy src/cbb` passed
  - `helm lint chart/cbb-upsets -f chart/cbb-upsets/values.yaml -f chart/cbb-upsets/values-local.yaml`
    passed
  - `helm template cbb-upsets chart/cbb-upsets -f chart/cbb-upsets/values.yaml -f chart/cbb-upsets/values-local.yaml`
    passed
- full-window audit on March 11 to March 13, 2026 remained slightly unstable
  because ESPN tournament schedules and same-day statuses changed during the
  long audit runtime
- stable historical audit:
  - command:
    `./.venv/bin/python -m cbb.cli db audit --start-date 2023-03-08 --end-date 2026-03-10`
  - result: `1099` dates checked, `17349` upstream games, `17349` present,
    `17349` verified, `0` missing, `0` status mismatches, `0` score
    mismatches, `0` context mismatches

Tradeoffs

- Historical ingest and audit remain slower than ideal because they reload the
  ESPN team catalog on each CLI run.
- Travel distance, altitude, and timezone features are still not actionable
  because the repo does not yet store reproducible team home locations.
- The stored window still contains two synthetic Odds API duplicates on shifted
  UTC dates; they do not break historical audit, but they keep field coverage
  slightly below `100%`.

Conclusion

- Promoted as data foundation.
- Venue/site and postseason storage are no longer blockers for the next
  neutral-site / postseason modeling experiment.
- Travel-focused features remain blocked until the repo has stable team
  location data.

### Experiment 15: Neutral-Site / Postseason Features on Stored ESPN Context

Hypothesis

- The newly stored neutral-site and postseason context is the first
  reproducible NCAA-information lane already available in the repo, so adding
  it to the spread model should improve the full-window walk-forward result or
  at least reduce drawdown without collapsing activity.

Implementation

- Extended the modeling dataset query to read the stored ESPN `games`
  context fields needed for:
  - `neutral_site`
  - `season_type`
  - `season_type_slug`
- Added additive spread-model features for:
  - neutral-site context
  - home-court advantage on campus-site games
  - postseason context
  - neutral-postseason interaction
- Extended spread segment attribution so the canonical report could compare:
  - campus-site vs neutral-site qualified bets
  - regular-season vs postseason qualified bets

Files changed

- [src/cbb/modeling/dataset.py](../src/cbb/modeling/dataset.py)
- [src/cbb/modeling/features.py](../src/cbb/modeling/features.py)
- [src/cbb/modeling/policy.py](../src/cbb/modeling/policy.py)
- [src/cbb/modeling/report.py](../src/cbb/modeling/report.py)
- [tests/test_features.py](../tests/test_features.py)
- [tests/test_modeling.py](../tests/test_modeling.py)

Backtest results

- baseline `2026` gate before the experiment:
  - `207` bets
  - `+$137.86`
  - ROI `+9.68%`
  - max drawdown `6.79%`
  - spread close EV `+0.093`
- experiment `2026` gate:
  - `173` bets
  - `+$127.63`
  - ROI `+10.91%`
  - max drawdown `5.23%`
  - spread close EV `+0.093`
- baseline full window before the experiment:
  - `570` bets
  - `+$277.21`
  - ROI `+7.18%`
  - max drawdown `10.49%`
  - profitable seasons `2/3`
- experiment full window:
  - `539` bets
  - `+$241.65`
  - ROI `+6.54%`
  - max drawdown `10.27%`
  - profitable seasons `2/3`
- season detail from the failed full-window run:
  - `2024`: `170` bets, `-$81.44`, ROI `-7.99%`
  - `2025`: `196` bets, `+$195.46`, ROI `+13.01%`
  - `2026`: `173` bets, `+$127.63`, ROI `+10.91%`
- aggregate segment findings from the failed run:
  - only `20` neutral-site bets qualified across the full window, though they
    posted `+32.93%` ROI on a tiny sample
  - only `3` postseason bets qualified across the full window, far too few to
    support a stable policy conclusion

Tradeoffs

- The experiment improved the latest season and reduced drawdown, but it did
  so by shrinking activity from `570` bets to `539`.
- The added context barely activated under the current deployable policy, so
  the experiment mostly acted as a sparse filter rather than a durable new
  information source.
- Runtime increased materially on the `2026` gate relative to the current
  baseline without earning a full-window improvement.

Conclusion

- Reverted.
- Stored neutral-site and postseason context alone is not enough to clear the
  promotion bar under the current market-anchored spread path.
- The next repo-local work should harden close-based evaluation quality, while
  the next plausible baseline-improvement lane requires truly new NCAA
  information such as official tournament availability.

### Experiment 16: Same-Day Spread Exposure Cap

Hypothesis

- The current promoted baseline still overexposes the heaviest same-day slates,
  especially in the weak `2024` season, so a small explicit same-day cap should
  improve drawdown and season stability without meaningfully hurting the
  execution-driven edge.

Implementation

- Added an optional `max_bets_per_day` field to the shared `BetPolicy`.
- Set the deployable spread baseline to `max_bets_per_day=6`.
- Applied the cap inside the existing same-day bankroll limiter after the
  current board-rank sort, so no new conference or regime logic was added.
- Threaded the new field through:
  - walk-forward backtest policy replay
  - live prediction policy construction
  - canonical report formatting
  - dashboard snapshot policy serialization
  - dashboard/UI compatibility loading for older snapshots

Files changed

- [src/cbb/modeling/policy.py](../src/cbb/modeling/policy.py)
- [src/cbb/modeling/backtest.py](../src/cbb/modeling/backtest.py)
- [src/cbb/modeling/report.py](../src/cbb/modeling/report.py)
- [src/cbb/dashboard/snapshot.py](../src/cbb/dashboard/snapshot.py)
- [src/cbb/cli.py](../src/cbb/cli.py)
- [src/cbb/ui/app.py](../src/cbb/ui/app.py)
- [tests/test_modeling.py](../tests/test_modeling.py)
- [tests/test_report.py](../tests/test_report.py)
- [tests/test_dashboard_snapshot.py](../tests/test_dashboard_snapshot.py)

Backtest results

- baseline `2026` gate before the experiment:
  - `207` bets
  - `+$137.86`
  - ROI `+9.68%`
  - max drawdown `6.79%`
  - spread close EV `+0.093`
- experiment `2026` gate:
  - `196` bets
  - `+$138.57`
  - ROI `+10.06%`
  - max drawdown `7.01%`
  - spread close EV `+0.097`
- baseline full window before the experiment:
  - `570` bets
  - `+$277.21`
  - ROI `+7.18%`
  - max drawdown `10.49%`
  - profitable seasons `2/3`
- experiment full window:
  - `536` bets
  - `+$268.02`
  - ROI `+7.20%`
  - max drawdown `8.78%`
  - profitable seasons `2/3`
- promoted season detail:
  - `2024`: `148` bets, `-$61.81`, ROI `-6.66%`, max drawdown `8.23%`
  - `2025`: `192` bets, `+$191.25`, ROI `+13.49%`, max drawdown `8.78%`
  - `2026`: `196` bets, `+$138.57`, ROI `+10.06%`, max drawdown `7.01%`

Tradeoffs

- Activity fell from `570` bets to `536`, but did not collapse and remained
  realistic for the deployable path.
- Aggregate profit dollars fell modestly because the cap trims both good and
  bad same-day bets, not only losers.
- `2025` remained strong but did give back some upside, so this is a stability
  promotion rather than a pure edge expansion.

Conclusion

- Promoted.
- The cap cleared the repo's promotion bar because ROI stayed slightly better
  while max drawdown improved materially from `10.49%` to `8.78%`.
- The strongest local gain was reduced same-slate damage in `2024`, which
  remains the weak season but is now less damaging.
- The next worthwhile lane is no longer another repo-local policy tweak; it is
  new NCAA information, starting with official tournament availability.

## Sources

External research and market-context links used in this refresh:

- [Machine Learning with Applications 2024: calibration and betting usefulness](https://doi.org/10.1016/j.mlwa.2024.100539)
- [Sports Economics Review 2024: normalized probabilities for betting-market efficiency tests](https://doi.org/10.1016/j.sper.2024.100011)
- [Applied Economics 2025: expected loss rates in betting markets](https://www.tandfonline.com/doi/full/10.1080/00036846.2025.2521504)
- [International Journal of Forecasting 2019: best-odds selection across books](https://www.sciencedirect.com/science/article/pii/S0169207018301134)
- [International Journal of Forecasting 2025: Asian handicap forecasts and market efficiency](https://ideas.repec.org/a/eee/intfor/v41y2025i1p95-117.html)
- [Journal of the American Statistical Association 2025: tail calibration](https://doi.org/10.1080/01621459.2024.2379666)
- [Journal of Forecasting 2025: robust probabilistic recalibration](https://doi.org/10.1002/for.70063)
- [Journal of Forecasting 2025: adaptive fusion instead of market-only combination](https://doi.org/10.1002/for.70023)
- [Information Fusion 2026: adaptive probabilistic fusion under concept drift](https://www.sciencedirect.com/science/article/pii/S1566253525000523)
- [PMLR 2024: conformal regression with reject option](https://proceedings.mlr.press/v230/johansson24a.html)
- [TMLR 2025: error-reject tradeoff for selective classification](https://openreview.net/forum?id=DnfHQ7rBQ4)
- [arXiv 2024 sports betting ML review](https://arxiv.org/abs/2410.21484)
- [From News to Forecast, 2024](https://doi.org/10.48550/arXiv.2409.17515)
- [ForestCast, Findings of EMNLP 2025](https://aclanthology.org/2025.findings-emnlp.678/)
- [Context Matters, 2024](https://doi.org/10.48550/arXiv.2410.12672)
- [OpenAI Responses API guide](https://developers.openai.com/api/docs/guides/responses-vs-chat-completions)
- [OpenAI web search guide](https://developers.openai.com/api/docs/guides/tools-web-search)
- [OpenAI function calling guide](https://developers.openai.com/api/docs/guides/function-calling)
- [OpenAI structured outputs guide](https://platform.openai.com/docs/guides/structured-outputs)
- [OpenAI API pricing](https://openai.com/api/pricing/)
- [NCAA, March 4, 2026: player-availability reporting details](https://www.ncaa.org/news/2026/3/4/media-center-ncaa-releases-penalty-and-process-details-for-march-madness-player-availability-reports.aspx)
- [NCAA, January 15, 2026: player props and first-half under integrity concerns](https://www.ncaa.org/news/2026/1/15/media-center-ncaa-asks-states-to-ban-player-props-and-first-half-under-betting-on-college-sports.aspx)
- [AGA Commercial Gaming Revenue Tracker, February 26, 2026](https://www.americangaming.org/resources/commercial-gaming-revenue-tracker/)
- [NBER Working Paper 33108: sports betting legalization and household finance](https://www.nber.org/papers/w33108)
