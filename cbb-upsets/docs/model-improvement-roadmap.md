# Model Improvement Roadmap

Canonical links:

- [Repository README](../README.md)
- [Model Documentation](model.md)
- [System Architecture](architecture.md)
- [Current Best-Model Report](results/best-model-3y-backtest.md)

Updated: `2026-03-11`

## Goal

This document captures the current research view of how to improve the NCAA
men's basketball spread-upset betting model. The focus is not training metrics.
The focus is:

- long-run ROI
- stability across seasons
- realistic betting activity
- no increase in max drawdown without a compelling return benefit

All recommendations in this document are grounded in walk-forward backtests.

## Current System Summary

The current deployable path is a spread-first `best` strategy. The system:

1. builds sequential pregame features from historical NCAA game and odds data
2. trains a spread model that predicts margin relative to the market line
3. converts that residual-margin estimate into a cover probability
4. calibrates the probability with held-out Platt scaling and market-relative
   shrinkage
5. evaluates executable quotes across books and keeps the best surviving quote
6. applies fixed spread policy thresholds and bankroll limits

Relevant code paths:

- training: [src/cbb/modeling/train.py](../src/cbb/modeling/train.py)
- features: [src/cbb/modeling/features.py](../src/cbb/modeling/features.py)
- quote execution: [src/cbb/modeling/execution.py](../src/cbb/modeling/execution.py)
- backtesting: [src/cbb/modeling/backtest.py](../src/cbb/modeling/backtest.py)
- bet policy: [src/cbb/modeling/policy.py](../src/cbb/modeling/policy.py)

## Major Assumptions

- The market is the correct anchor and the model should learn structured,
  stable deviations around it.
- Spread edge comes more from quote selection, calibration, and regime-aware
  modeling than from replacing the market outright.
- Simple, explicit features and frequent retraining are preferable to a more
  opaque model that cannot survive walk-forward testing.
- Cross-book survivability matters. A bet is more credible when the same side
  stays positive EV across multiple books.

## Weaknesses and Blind Spots

- No direct player-availability, injury, lineup, transfer, or coaching-change
  data.
- No travel, altitude, neutral-site, or tournament-context features.
- No opponent-adjusted possession-level efficiency features.
- Spread uncertainty is still mostly handled through a global residual scale.
- Policy thresholds are fixed rather than uncertainty-aware.
- The existing tree challenger did not improve results materially enough to
  justify promotion.
- The timing layer is too sparse in current form to be a deployable activity
  engine.

## What the Current Results Say

The current tracked report is:

- [results/best-model-3y-backtest.md](results/best-model-3y-backtest.md)

After the current experiment described below, the three-season report shows:

- aggregate result: `+$247.12` on `633` bets, ROI `+5.80%`
- profitable seasons: `2/3`
- max drawdown: `13.38%`
- aggregate spread close EV: `+0.080`

Important interpretation:

- raw spread line CLV is still negative
- spread price CLV, no-vig close delta, and close EV are positive

This suggests the model's strongest current signal is more likely in
execution-quality and market-relative pricing than in consistently beating the
closing line in raw points.

## Literature and Method Signals

The most relevant themes from betting, forecasting, and trading research are:

- margin and distributional modeling are generally more defensible than raw
  cover classification for spread markets
- calibration matters more than raw accuracy for decision usefulness
- best-odds and cross-book selection are where residual edge is most plausible
- nonstationary environments benefit from regime handling and uncertainty-aware
  abstention
- bankroll sizing is fragile when probability estimates are noisy, which argues
  for robust or fractional Kelly rather than aggressive sizing

Primary references:

- Sports betting ML review: <https://doi.org/10.48550/arXiv.2410.21484>
- Calibration and betting usefulness: <https://doi.org/10.1016/j.mlwa.2024.100539>
- Cross-book sports market efficiency: <https://www.sciencedirect.com/science/article/pii/S0169207018301134>
- College basketball opening vs closing lines: <https://www.sciencedirect.com/science/article/abs/pii/S0148619513000295>
- NCAA tournament efficiency: <https://link.springer.com/article/10.1007/s12197-020-09507-7>
- Conformalized Quantile Regression: <https://proceedings.neurips.cc/paper/2019/hash/5103c3584b063c431bd12689b5e76fb-Abstract.html>
- Deep Ensembles uncertainty: <https://papers.neurips.cc/paper/2017/hash/9ef2ed4b7fd2c810847ff9926e217b1e-Abstract.html>
- NCAA March Madness player-availability reporting: <https://www.ncaa.org/news/2026/3/4/media-center-ncaa-releases-penalty-and-process-details-for-march-madness-player-availability-reports.aspx>

## Ranked Improvement Ideas

Impact Score = `(ROI improvement x robustness x activity increase) / implementation complexity`

| Rank | Idea | Category | ROI | Robustness | Activity | Complexity | Impact Score | Overfit Risk | Data Change |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 1 | Dynamic uncertainty-aware edge threshold using lower-bound EV | Policy | 4 | 5 | 4 | 2 | 40.0 | medium | none |
| 2 | Season-phase spread calibration by opener / early / established games | Model | 4 | 5 | 3 | 2 | 30.0 | low | none |
| 3 | Heteroskedastic residual scale by phase, line size, and book depth | Model | 4 | 4 | 4 | 3 | 21.3 | medium | none |
| 4 | Travel, neutral-site, altitude, and tournament flags | Feature | 3 | 4 | 3 | 2 | 18.0 | low | modest |
| 5 | Tune multi-book survivability with median EV and worst acceptable line | Policy | 3 | 4 | 3 | 2 | 18.0 | low | none |
| 6 | Opponent-adjusted efficiency and strength-of-schedule features | Feature | 4 | 4 | 3 | 3 | 16.0 | medium | modest |
| 7 | Market microstructure features: stale quote age, leader-lagger, velocity, entropy | Feature | 4 | 4 | 3 | 3 | 16.0 | medium | none |
| 8 | Phase-specific policy thresholds instead of one global spread filter | Policy | 3 | 4 | 4 | 3 | 16.0 | medium | none |
| 9 | Tournament and player-availability feed integration | Data | 3 | 5 | 2 | 2 | 15.0 | low | new feed |
| 10 | Conformal abstention or prediction-interval reject option | Model | 3 | 5 | 2 | 3 | 10.0 | low | none |
| 11 | Correlated exposure caps by conference and tip window | Policy | 2 | 5 | 2 | 2 | 10.0 | low | none |
| 12 | Linear residual plus tree residual ensemble | Model | 4 | 3 | 3 | 4 | 9.0 | medium | none |
| 13 | Histogram gradient boosting regressor for spread residual | Model | 4 | 3 | 3 | 4 | 9.0 | medium | none |
| 14 | Quantile or distributional margin model | Model | 4 | 3 | 3 | 4 | 9.0 | high | none |
| 15 | Regime detector or mixture-of-experts by phase and market depth | Model | 4 | 4 | 2 | 4 | 8.0 | high | none |
| 16 | Direct close-EV second-stage filter | Model | 3 | 4 | 2 | 3 | 8.0 | medium | none |
| 17 | Lineup continuity, transfer, and coach continuity features | Feature | 4 | 4 | 2 | 4 | 8.0 | medium | new data |
| 18 | Regular-season injury and news ingestion | Data | 4 | 4 | 2 | 5 | 6.4 | high | new feed |
| 19 | Reworked timing model as bet-now / wait / pass classifier | Policy | 3 | 3 | 2 | 3 | 6.0 | medium | none |
| 20 | Hierarchical Bayesian conference shrinkage | Model | 3 | 4 | 2 | 4 | 6.0 | medium | none |

## Top 5 Experiments

### 1. Uncertainty-Aware Thresholding

- modeling approach: bet only when a lower-bound edge estimate clears the
  threshold instead of using point-estimate EV
- required features: current model outputs, residual uncertainty proxy, line
  bucket, season phase, book depth
- evaluation: walk-forward backtest on identical blocks and policy caps
- success criteria:
  - `+0.75pp` or better three-season ROI
  - no worse max drawdown
  - at least `90%` of current activity

### 2. Heteroskedastic Spread Uncertainty

- modeling approach: predict residual scale `sigma(x)` rather than one global
  spread residual scale
- required features: line size, min games played, book count, dispersion,
  totals move, conference
- evaluation: 2026 backtest first, then three-season report
- success criteria:
  - improved close EV
  - improved three-season ROI
  - no material drawdown increase

### 3. Opponent-Adjusted Efficiency and Schedule Strength

- modeling approach: replace simple rolling points and margins with adjusted
  offense, defense, pace, and schedule-strength features
- required features: possession estimates and opponent-adjusted rolling team
  quality
- evaluation: walk-forward only
- success criteria:
  - same or higher activity
  - improved three-season ROI
  - better per-season stability

### 4. Market Microstructure Expansion

- modeling approach: add stale-quote, quote-age, leader-lagger, disagreement
  entropy, and intraday move-velocity features
- required features: quote timestamps and cross-book market states
- evaluation: walk-forward plus spread price CLV and close EV
- success criteria:
  - same or better ROI
  - better spread price CLV or close EV
  - no drawdown regression

### 5. Nonlinear Residual Ensemble

- modeling approach: blend the current linear residual model with a nonlinear
  residual model, then recalibrate
- required features: current feature set
- evaluation: season-by-season walk-forward comparison
- success criteria:
  - improve aggregate ROI
  - keep at least `2/3` profitable seasons
  - no collapse in bet frequency

## Implemented Experiment Log

### Hypothesis

NCAA spread instability is partly a regime-calibration problem. Season openers,
early-season games, and established-game contexts should not share one
identical spread calibration rule.

### Implementation

Added season-phase spread calibration support:

- new artifact field and payload support:
  [src/cbb/modeling/artifacts.py](../src/cbb/modeling/artifacts.py)
- new phase buckets and calibration search:
  [src/cbb/modeling/train.py](../src/cbb/modeling/train.py)
- scoring-time spread calibration override:
  [src/cbb/modeling/train.py](../src/cbb/modeling/train.py)
- regression tests:
  [tests/test_modeling.py](../tests/test_modeling.py),
  [tests/test_artifacts.py](../tests/test_artifacts.py)

### Files Changed

- [src/cbb/modeling/artifacts.py](../src/cbb/modeling/artifacts.py)
- [src/cbb/modeling/train.py](../src/cbb/modeling/train.py)
- [tests/test_modeling.py](../tests/test_modeling.py)
- [tests/test_artifacts.py](../tests/test_artifacts.py)
- [docs/model.md](model.md)
- [docs/architecture.md](architecture.md)

### Results

Baseline before experiment:

- three-season aggregate: `+$175.49`, ROI `+3.66%`, bets `689`
- 2026: `+$134.21`, ROI `+7.90%`, bets `237`

After season-phase calibration:

- three-season aggregate: `+$247.12`, ROI `+5.80%`, bets `633`
- max drawdown improved from `14.22%` to `13.38%`
- 2026: `+$124.91`, ROI `+8.27%`, bets `219`
- 2026 spread closing EV improved from `+0.078` to `+0.092`

Tradeoff:

- 2024 worsened from `-$105.86` to `-$112.38`

### Conclusion

This experiment improved aggregate ROI, aggregate drawdown, and closing EV, but
it did not fix season instability fully. It is a credible improvement and a
better research baseline, not a final solution.

## Continuous Optimization Log

### Iteration 1

- hypothesis: season-phase-aware spread calibration will improve ROI and close
  quality without materially increasing drawdown
- experiment: add opener / early / established spread calibration buckets
- results:
  - 2026 ROI improved from `7.90%` to `8.27%`
  - three-season ROI improved from `3.66%` to `5.80%`
  - max drawdown improved from `14.22%` to `13.38%`
  - activity declined from `689` bets to `633`
  - 2024 worsened slightly
- conclusion: keep as the current research-leading baseline, but do not stop
  here

## Recommended Next Improvement

The next experiment should be:

### Heteroskedastic Spread Uncertainty plus Lower-Bound EV Gating

Why this should be next:

- the current tree challenger failed materially on walk-forward results
- the current timing layer is too sparse to be a deployable activity engine
- the season-phase calibration improvement helped aggregate ROI but did not
  solve the bad season
- the largest remaining modeling weakness is still a mostly global spread
  uncertainty assumption

Recommended design:

1. predict both expected spread residual and residual uncertainty
2. compute a lower-bound cover edge instead of using only point-estimate EV
3. require that lower-bound EV clear the policy threshold
4. compare ROI, drawdown, close EV, and seasonal dispersion against the current
   baseline

## Phase Roadmap

### Phase 1: Low-Risk Improvements

- keep season-phase spread calibration
- add uncertainty-aware thresholding and Kelly shrinkage
- tune survivability with median EV and worst acceptable line
- add travel, neutral-site, altitude, and tournament flags

Expected impact:

- `+0.5pp` to `+1.5pp` three-season ROI
- same or lower drawdown
- stable or slightly lower activity with better quality

### Phase 2: Structural Model Changes

- heteroskedastic residual scale
- opponent-adjusted efficiency and strength-of-schedule features
- market microstructure leader-lagger features
- lineup continuity, transfer, and coach continuity features

Expected impact:

- another `+1pp` to `+2pp` if uncertainty is modeled well
- better early-season stability

### Phase 3: Experimental Advanced Models

- nonlinear residual ensemble
- conformal abstention band
- regime detector or mixture-of-experts
- tournament and regular-season player-availability feeds

Expected impact:

- smaller marginal ROI improvement
- larger robustness gains if the models hold up out of sample

## Verification

Executed during this research cycle:

- `ruff check src/cbb/modeling/artifacts.py src/cbb/modeling/train.py tests/test_modeling.py tests/test_artifacts.py docs/model.md docs/architecture.md`
- `pytest -q tests/test_artifacts.py tests/test_modeling.py`
- walk-forward backtests against local Postgres for:
  - 2026 logistic spread baseline
  - 2026 histogram gradient boosting challenger
  - 2026 timing-layer variant
  - 2026 season-phase calibration variant
  - full three-season report refresh
