# Model Improvement Roadmap

Canonical links:

- [Repository README](../README.md)
- [Model Documentation](model.md)
- [System Architecture](architecture.md)
- [Current Best-Model Report](results/best-model-3y-backtest.md)

Updated: `2026-03-11`

## Goal

This document is the current research view of how to improve the NCAA men's
basketball spread model.

The optimization target is unchanged:

- long-run ROI
- stability across seasons
- realistic betting activity
- no material drawdown increase

The strategic view changed again after the latest repo evidence and a fresh
outside-literature pass:

- rolling adaptive recalibration now moves ahead of segment abstention
- segment kill-switch logic is demoted because the current bad slices are
  small and still positive on close EV
- generic structural model complexity remains demoted
- a news/LLM lane is now in scope only as bounded, verifiable data acquisition,
  not as generic sentiment or free-form summarization

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

- aggregate: `+$282.70` on `569` bets, ROI `+7.34%`
- seasons: `2024=-8.76%`, `2025=+15.29%`, `2026=+10.11%`
- profitable seasons: `2/3`
- max drawdown: `10.49%`
- aggregate spread close EV: `+0.083`
- aggregate spread line CLV: `-0.46 pts`
- aggregate spread price CLV: `+1.87 pp`
- aggregate spread no-vig close delta: `+1.59 pp`

Current interpretation:

- the system still is not proving a durable raw spread-line edge
- it is proving a modest, repeatable price/execution edge against executable
  quotes
- the promoted gains so far came from calibration and uncertainty control, not
  from richer model structure

## What Has Actually Worked

The promoted changes in this repo all improved how the existing market-anchored
model qualifies and calibrates bets.

| Iteration | Change | Before | After | Result |
| --- | --- | --- | --- | --- |
| 1 | Season-phase spread calibration | `+3.66%` ROI, `14.22%` DD, `689` bets | `+5.80%` ROI, `13.38%` DD, `633` bets | promoted |
| 2 | Uncertainty-aware edge threshold / lower-bound quote gating | `+5.80%` ROI, `13.38%` DD, `633` bets | `+7.05%` ROI, `11.73%` DD, `575` bets | promoted |
| 3 | Heteroskedastic spread residual uncertainty | `+7.05%` ROI, `11.73%` DD, `575` bets | `+7.34%` ROI, `10.49%` DD, `569` bets | promoted |
| 10 | Segment attribution for qualified spread bets | no bankroll change | added segment diagnostics only | promoted as evaluation |

Local lesson:

- the remaining edge responds to better calibration, better uncertainty
  handling, and better execution-aware evaluation
- it has not responded to attempts to make the core predictive model more
  expressive on the same information set

## Recent Failed Experiments

The recent failures are consistent enough to justify another roadmap reset.

| Iteration | Change | Gate / Full Result | Failure Mode | Decision |
| --- | --- | --- | --- | --- |
| 4 | Score-only opponent-adjusted efficiency and schedule strength | `2026 ROI: 10.11% -> 5.56%`, DD `6.79% -> 9.13%` | worse ROI and worse drawdown before a full-window test | reverted |
| 5 | Microstructure features as direct model inputs | `2026` improved, full-window ROI `7.34% -> 6.14%` | improved latest season but broke `2025` | reverted |
| 6 | Coverage-rate survivability gate | `2026 ROI: 10.11% -> 8.14-8.63%` | cut good activity immediately | reverted |
| 7 | Phase-specific betting thresholds | full-window ROI `7.34% -> 3.83%`, DD `10.49% -> 20.88%` | reopened too much weak activity, especially `2025` | reverted |
| 8 | Nonlinear residual ensemble | `2026` gate did not finish in reasonable runtime | runtime cost failed before quality was proven | reverted |
| 9 | Conformal abstention band | `2026` gate collapsed from `232` candidates to `0` bets | reject-option design was far too conservative | reverted |
| 11 | Prior-window selective abstention / kill-switch | no promotable result; activation evidence weak | small bad slices still had positive close EV | reverted |

## Failure Pattern Diagnosis

The failure pattern is now specific enough that the next roadmap should stop
hedging.

### 1. Structural model experiments are failing on information, not only on tuning

The repo still does not model:

- player availability outside market proxies
- lineup continuity
- transfer shocks
- coaching changes
- travel and altitude
- neutral-site context
- tournament-specific context beyond limited regime proxies

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

### 4. The current segment tables do not justify a kill-switch

The new report-level segment attribution weakens the prior abstention-first
recommendation.

Current bad segments are:

- `Mid Depth`: `16` bets, ROI `-12.15%`, close EV `+0.091`
- `Non-Conference`: `50` bets, ROI `-0.76%`, close EV `+0.064`
- `Unknown` conference group: `8` bets, ROI `-21.22%`, close EV `+0.043`

Those slices are either:

- too small to support a stable block rule
- or still positive on close EV, which suggests noise or timing/execution
  mismatch rather than a cleanly bad segment

Inference from local evidence:

- segment attribution is still useful as evaluation
- segment abstention is not currently justified as the next live experiment

### 5. Runtime is now part of the promotion bar

The nonlinear residual ensemble failure showed that research-operational cost
is not a side issue. If an experiment cannot finish a reasonable walk-forward
loop cheaply, it is not a near-term roadmap item.

## Fresh External Research

The refreshed outside evidence reinforces the shift away from generic
structural complexity.

### Calibration, Tails, and Adaptive Recalibration

- [Machine Learning with Applications 2024](https://doi.org/10.1016/j.mlwa.2024.100539)
  argues that betting usefulness depends heavily on calibrated probabilities,
  not just model accuracy.
- [Journal of the American Statistical Association 2025](https://doi.org/10.1080/01621459.2024.2379666)
  emphasizes tail calibration for probabilistic forecasts. That matters here
  because bets live in the tail of model-vs-market disagreement.
- [Journal of Forecasting 2025](https://doi.org/10.1002/for.70063)
  shows robust probabilistic recalibration can outperform direct use of raw
  forecasts under drift or tail misspecification.
- [Journal of Forecasting 2025](https://doi.org/10.1002/for.70023)
  supports adaptive fusion instead of fixed market-only combination rules when
  non-market information exists.
- [Information Fusion 2026](https://www.sciencedirect.com/science/article/pii/S1566253525000523)
  supports adaptive probabilistic fusion under concept drift rather than one
  static blend.

Implication for this repo:

- adaptive recalibration now has both the strongest local evidence and the
  strongest outside support
- the next model work should change how probabilities are stabilized over time,
  not change the base spread model family

### Market Efficiency and Evaluation

- [Sports Economics Review 2024](https://doi.org/10.1016/j.sper.2024.100011)
  argues market-efficiency tests should use normalized no-vig probabilities.
- [Applied Economics 2025](https://www.tandfonline.com/doi/full/10.1080/00036846.2025.2521504)
  shows overround alone is an incomplete proxy for realized bettor losses.
- [International Journal of Forecasting 2019](https://www.sciencedirect.com/science/article/pii/S0169207018301134)
  remains one of the clearest pieces of evidence that best-odds selection
  across books is where residual edge is most plausible.
- [International Journal of Forecasting 2025](https://ideas.repec.org/a/eee/intfor/v41y2025i1p95-117.html)
  is another warning that spread-like markets can be very efficient and hard
  to beat with richer function classes alone.

Implication for this repo:

- keep price/no-vig/close-EV diagnostics first-class
- keep treating raw line CLV as incomplete for this system
- do not assume more structural model capacity is the highest-value lane

### Abstention and Reject-Option Methods

- [Transactions on Machine Learning Research 2025](https://openreview.net/forum?id=DnfHQ7rBQ4)
  shows error-reject systems have to be tuned for acceptable rejection
  behavior; they do not give a free improvement.
- [PMLR 2024](https://proceedings.mlr.press/v230/johansson24a.html)
  shows conformal reject-option design is a control problem, not a free alpha
  source.

Implication for this repo:

- the conformal failure is not surprising in hindsight
- reject-option work should stay demoted until there is stronger evidence that
  a well-defined bad region exists

### News, Event Extraction, and Real-Time Forecasting

- [arXiv 2024 sports betting ML review](https://arxiv.org/abs/2410.21484)
  points toward multimodal and real-time information as the next major gain
  area, with data quality as the main bottleneck.
- [From News to Forecast, 2024](https://doi.org/10.48550/arXiv.2409.17515)
  argues that structured event analysis can improve forecasting more than
  naive use of raw news text.
- [ForestCast, Findings of EMNLP 2025](https://aclanthology.org/2025.findings-emnlp.678/)
  focuses on where and how relevant news context should enter forecasting
  pipelines rather than treating all news as equally useful.
- [Context Matters, 2024](https://doi.org/10.48550/arXiv.2410.12672)
  also supports contextual and selective use of auxiliary signals rather than
  generic unstructured text features.

Implication for this repo:

- if the project explores news, it should prioritize retrieval plus structured
  event extraction
- generic sentiment is the wrong first design
- new information should be explicit and verifiable: player availability,
  suspensions, coaching changes, venue/travel disruptions

### OpenAI Product / API Guidance for a News Pipeline

Official OpenAI documentation now makes a news-extraction prototype technically
feasible:

- [Responses API guide](https://developers.openai.com/api/docs/guides/responses-vs-chat-completions)
  is the current orchestration entry point.
- [Web search guide](https://developers.openai.com/api/docs/guides/tools-web-search)
  supports current web retrieval and cited sources in Responses API outputs.
- [Function calling guide](https://developers.openai.com/api/docs/guides/function-calling)
  supports tool-using workflows that pull outside information into the model.
- [Structured outputs guide](https://platform.openai.com/docs/guides/structured-outputs)
  supports strict schema-constrained extraction.
- [API pricing](https://openai.com/api/pricing/)
  makes the cost side explicit for tool calls and model usage.

Implication for this repo:

- a bounded LLM pipeline is now feasible as an engineering workflow
- feasibility does not make it a near-term backtestable alpha source
- historical reproducibility is still the hardest problem

## Adaptive Recalibration vs Segment Abstention

This is now the key roadmap choice.

| Lane | Assessment | Why |
| --- | --- | --- |
| Rolling adaptive recalibration of market blend and probability shrinkage by stable window or segment | `GO` | matches local wins, supported by current literature on recalibration under drift, cheap enough to test |
| Segment attribution as report/backtest diagnostics | `GO` | useful evaluation layer, already promoted |
| Segment abstention / kill-switch as the next live experiment | `NO-GO for now` | current bad slices are too small and still positive on close EV |
| Generic reject-option / conformal abstention | `NO-GO for now` | local zero-activity failure plus weak local evidence of a truly bad region |

Current decision:

- adaptive recalibration moves up to the top of the roadmap
- segment abstention is demoted to a future conditional experiment

Condition for reviving segment abstention later:

- only revisit it if a later recalibration or new-data experiment produces a
  segment with both:
  - adequate sample size
  - negative ROI and negative close EV in prior windows

## LLM / News Pipeline Feasibility

The news idea is promising enough to keep, but only in a narrow form.

### Could a ChatGPT / OpenAI API news pipeline create useful NCAA signals?

Yes, but only if it is framed as structured public-information extraction, not
as generic sentiment or free-form summaries.

The best candidate signal classes are:

- player availability and late scratches
- suspensions and disciplinary news
- coaching changes or absences
- venue, travel, or weather disruption context
- bounded postseason news where official sources exist

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
2. use structured outputs or function calling to extract a strict event schema
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

## Go / No-Go Assessment

| Idea | Assessment | Current Role |
| --- | --- | --- |
| Rolling adaptive recalibration | `GO` | next live experiment |
| Segment abstention / kill-switch | `NO-GO for now` | keep only as a later conditional revisit |
| LLM / ChatGPT API pregame news pipeline | `Research-only GO` | build only as bounded, archived, structured extraction |
| New NCAA-specific data acquisition | `GO` | high-priority medium-term lane |

## Revised Ranked Ideas

The ranking below is now based on both the repo evidence and the refreshed
outside research.

| Rank | Idea | Category | Status | Why it moved |
| --- | --- | --- | --- | --- |
| 1 | Rolling adaptive recalibration of spread market-blend and shrinkage controls by stable window or stable segment | Model / Evaluation | promoted | strongest fit to local wins and current literature on drift |
| 2 | Tail diagnostics and qualified-bet recalibration for the accepted edge region | Evaluation | promoted | current gains live in the tails; global calibration is not enough |
| 3 | Travel, neutral-site, altitude, and postseason flags | Feature | promoted | simple new information is a better next bet than model complexity |
| 4 | Official NCAA player-availability integration, starting with March Madness reporting | Data | promoted | bounded, verifiable, and directly addresses a known missing signal |
| 5 | Correlated exposure caps by conference, slate window, and regime | Policy | promoted | stability and drawdown control without changing the base model |
| 6 | Market microstructure as attribution, diagnostics, or filter support rather than direct model expansion | Evaluation / Policy | reframed | direct feature expansion already failed the full window |
| 7 | Prospective LLM-assisted news retrieval plus structured event extraction with archived sources | Data / Research | new, bounded | viable as future data capture, not as immediate alpha |
| 8 | Segment attribution | Evaluation | retained | useful diagnostics, but no longer the next policy experiment |
| 9 | Segment abstention / kill-switch logic | Policy | demoted | current bad slices do not justify it |
| 10 | Score-only opponent-adjusted efficiency rebuilds | Feature | demoted | failed on the current information set |
| 11 | Static nonlinear residual ensembles on the current feature set | Model | demoted | runtime too high and evidence too weak |
| 12 | Generic conformal or reject-option gating | Model | demoted | zero-activity failure and weak local support |
| 13 | Regime detector or mixture-of-experts before new data arrives | Model | demoted | higher-complexity version of a lane already failing |
| 14 | Generic news sentiment features | Feature | removed | weak auditability and weak causal mapping |
| 15 | More global survivability tightening or phase-threshold reopening | Policy | removed | both directions already failed locally |

## Top 5 Experiments Now

### 1. Rolling Adaptive Recalibration

- objective:
  improve robustness under season drift without changing the core spread model
  family
- minimal design:
  - keep the current linear residual model unchanged
  - adapt market-blend weight and max-market-delta controls on a trailing
    walk-forward window
  - if segmenting, use only stable buckets with enough sample, such as line
    bucket or book depth, not tiny conference slivers
  - evaluate on ROI, drawdown, activity, and spread close EV
- success criteria:
  - full-window ROI improvement of at least `0.25pp`, or
  - same ROI with lower drawdown, and
  - no activity collapse, and
  - `2/3` profitable seasons remain

### 2. Tail Diagnostics for Qualified Bets

- objective:
  test whether the accepted bet region is miscalibrated even when global
  calibration looks acceptable
- minimal design:
  - add report/backtest summaries for:
    - top expected-value buckets
    - top probability-edge buckets
    - spread line buckets
    - book-depth buckets
  - use those diagnostics to refine recalibration, not to add a blunt global
    filter
- success criteria:
  - explains the `2025` instability better, and
  - produces a narrower, better-grounded recalibration change

### 3. Travel / Neutral-Site / Postseason Context

- objective:
  add simple new information before revisiting any complex model class
- minimal design:
  - derive neutral-site and postseason flags from existing game metadata
  - add travel distance, altitude, and time-zone-change features only if they
    can be derived reliably
- success criteria:
  - improve the full-window result without runtime penalty
  - do not make `2025` worse

### 4. Tournament Availability Overlay

- objective:
  test whether bounded official availability information helps more than model
  complexity
- minimal design:
  - start with official NCAA March Madness availability reporting
  - keep the first version as a bounded postseason overlay
- success criteria:
  - better late-season and tournament segment results
  - no degradation of the regular-season baseline

### 5. Prospective News Shadow Pipeline

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

### Phase 1: Adaptive Recalibration and Better Evaluation

- rolling adaptive recalibration of market-blend and shrinkage controls
- tail diagnostics for qualified bets
- keep segment attribution as diagnostics, not as live abstention
- add correlated exposure caps if recalibration alone does not improve
  drawdown enough

Expected impact:

- better season stability
- low runtime risk
- stronger explanation of why `2025` breaks some experiments

### Phase 2: New Verifiable NCAA Information

- travel, neutral-site, altitude, and postseason flags
- official NCAA tournament player-availability integration
- bounded postseason overlays where official reporting exists

Expected impact:

- more genuine information edge than additional model complexity on stale data
- still operationally manageable

### Phase 3: Prospective Public-Information Pipeline

- build archived pregame news retrieval for bounded slates
- use structured extraction for verifiable events only
- only after that, consider adding those features to a live or backtest path

Expected impact:

- this is the first path that could justify another structural-model pass later
- until archival and reproducibility exist, it remains a research lane, not a
  deployment lane

## Next Best Experiment

### Neutral-Site / Postseason Context, With Travel Follow-On Once Team Locations Exist

Why this is next:

- the first adaptive recalibration attempt failed the `2026` gate
- the new tail diagnostics did not surface an obvious bad qualified-bet region
  with negative close EV
- the remaining roadmap gain is more likely to come from new NCAA information
  than from more shrinkage tuning on the same data

Exact research question:

- can the spread model improve full-window ROI or reduce drawdown once it has
  explicit neutral-site, postseason, and eventually travel context rather than
  more calibration logic on the current information set?

Current status:

- the repo now persists venue/site metadata, neutral-site flags, season-type
  indicators, tournament notes, and venue ids/names/city/state/indoor flags
  from the ESPN scoreboard feed
- that means a first neutral-site / postseason feature experiment is now
  actionable from stored walk-forward data
- travel distance, altitude, and timezone-change features are still blocked by
  missing reproducible team home-location data

## Bottom Line

The core diagnosis is now:

- the repo has already harvested the clearest wins from calibration and
  uncertainty control
- the current segment evidence does not support a segment kill-switch as the
  next move
- the first post-refresh adaptive recalibration attempt failed the gate
- the new tail diagnostics still did not identify a bad region with both
  negative ROI and negative close EV
- structural model experiments are still failing because the current
  information set is too weak
- the most defensible next step is now a first neutral-site / postseason
  feature experiment on the newly stored ESPN context
- travel/altitude/timezone work is still blocked on team home-location data
- the most promising longer-horizon new lane is not generic sentiment, but
  bounded, verifiable public-information extraction

That means the near-term roadmap is now:

1. test neutral-site / postseason features on the newly stored venue/site
   context
2. extend that lane to travel / altitude / timezone only after reproducible
   team home-location data exists
3. real new NCAA information after that, starting with official availability
4. archived public-information capture only after the data foundation exists

It deprioritizes:

- further spread-calibration variants on the current stored information set
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
