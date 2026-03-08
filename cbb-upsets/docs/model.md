# Model

Canonical links:

- [Repository README](../README.md)
- [System Architecture](architecture.md)
- [Current Best-Model Report](results/best-model-3y-backtest.md)

This document explains the durable modeling approach: inputs, feature families,
training flow, calibration, and evaluation method. Current tuned settings and
season-by-season performance live in the generated report, not in this doc.

## Model Overview

The modeling layer predicts pregame betting probabilities for NCAA men's
basketball games. It currently supports two markets:

- moneyline: probability that a selected team wins the game outright
- spread: probability that a selected side covers the listed spread

The output is not a raw classification label. The system produces calibrated
side-level probabilities, compares them to market prices, and then passes those
scores through a betting policy that decides whether a wager is actionable.

The deployable strategy market is `best`. In the current implementation,
`best` is spread-first: if a spread artifact is available, the live prediction
path uses spread candidates before falling back to moneyline. Exact policy
thresholds are intentionally kept out of this document because they change as
the model is re-evaluated.

## Prediction Goal

The goal is to turn stored game history and betting-market information into
probabilities that are usable for decision-making.

That means the model is trying to answer questions such as:

- "What is the probability this team wins outright?"
- "What is the probability this side covers the current spread?"
- "Is the model's probability meaningfully different from the market price?"

The system is optimized for betting use, so calibration and bankroll results
matter more than raw classification accuracy alone.

## Data Inputs

The model combines four input categories:

- historical game results from ESPN, including scores and game times
- rolling team performance state built only from prior completed games
- current and historical betting-market snapshots stored in `odds_snapshots`
- engineered market context derived from multiple bookmakers over time

The training set only uses examples that have usable pregame prices for the
target market. The full game history still matters because it is used to build
pregame team state for every example.

## Feature Engineering

Feature construction is sequential. For each game, the code rebuilds what would
have been known before tip-off and then emits side-based examples.

The main feature groups are:

- rolling team form: games played, win rate, average margin, scoring, and
  points allowed over the recent game window
- rating features: an Elo-style rating differential between the two teams
- schedule context: rest-day differential and a home-side indicator
- market features: implied probabilities and line values from the side being
  priced
- bookmaker-consensus features: opening and closing consensus prices across
  books, cross-book dispersion, and book count
- line-move features: changes from market open to market close, plus
  model-versus-consensus value signals
- totals-market features: total open, total close, total move, total
  dispersion, and spread/total interaction terms
- cross-market context: the moneyline model sees spread context and the spread
  model sees moneyline context

The feature set is intentionally explicit and relatively small so that training,
backtesting, and debugging stay fast and repeatable.

## Model Type

The deployable default for each market is still a regularized logistic
regression model. It was chosen because it is:

- easy to retrain often during walk-forward backtests
- cheap to store and load as a JSON artifact
- stable enough to debug when feature or data changes move results
- transparent enough that probability shifts can usually be traced back to
  inputs

For spread only, the repository also supports a histogram gradient-boosted tree
challenger. That path is useful for research, but it is not the default
deployment family unless it beats the logistic baseline on walk-forward
seasonal results.

Moneyline uses one extra layer beyond a single global model. The artifact can
store specialized band models for different price ranges and route a game to
the matching band at scoring time. This exists because moneyline behavior is
not equally well-behaved across the full price curve.

## Training Process

Training is performed from stored Postgres data, not directly from the upstream
APIs.

At a high level, training does this:

1. load the completed games and pregame odds for the selected seasons
2. rebuild rolling team state in chronological order
3. emit one example per side for the requested market
4. keep only priced, deployable examples for the target market
5. fit the selected model family on the engineered features
6. fit calibration parameters on held-out priced examples
7. save the trained artifact under `artifacts/models/`

By default the repository trains on a rolling three-season window. Moneyline
training is intentionally narrower than the full market universe; the current
default training band is centered on the prices the deployable strategy is most
likely to use.

## Calibration

Raw logistic outputs are not treated as ready-to-bet probabilities.

The current calibration stack includes:

- Platt scaling on held-out priced examples
- market blending, which shrinks predictions back toward the implied market
  probability
- a maximum market delta cap, which prevents the model from drifting too far
  away from the market on one example

Calibration is important because betting decisions are highly sensitive to
probability error. A model can have decent classification accuracy and still be
bad for wagering if it is systematically overconfident.

## Model Improvement Strategy

The model improves through a combination of better data, better features, and
more disciplined evaluation.

The current improvement path is:

- expand and audit historical odds coverage so more examples are trainable
- add richer bookmaker-consensus and line-move features
- keep improving spread-first deployment, because spread has been more stable
  than moneyline
- recover moneyline in tighter price segments before widening deployment
- compare the logistic spread baseline against stronger challenger models such
  as gradient-boosted trees, and only promote them if per-season walk-forward
  results improve
- keep live and backtest policy tuning walk-forward so thresholds are selected
  from prior data only

## Evaluation

The primary evaluation method is walk-forward backtesting, not the training-set
metrics printed after `model train`.

The main evaluation signals are:

- bankroll profit and ROI
- units won and bet volume
- max drawdown
- per-season behavior, not just one aggregate number
- training metrics such as log loss, Brier score, and accuracy
- eventually, closing line value for live picks

This matters because a deployable betting model must be judged on how it would
have behaved under realistic retraining and staking rules. The repository can
also evaluate one season at a time, which is the right way to see whether a
positive latest-season result is stable or just recent noise.
