# Betting Model Design

## Goal

Build a trainable and invokable betting system that can:

- backtrain on the current season and previous season
- predict moneyline and spread opportunities
- rank the best bets for a given slate
- size bets larger or smaller based on confidence
- evaluate success by bankroll growth and profit, not just prediction accuracy

## Core Design

Use a two-layer architecture:

1. Predictive models estimate outcome probabilities.
2. A betting policy converts those probabilities into bet/no-bet decisions and
   stake sizes.

This separation is important. The predictive model should focus on estimating
probabilities well. The betting policy should focus on extracting profit from
those probabilities.

## Supported Bet Types

Two separate models should be trained:

- `moneyline_model`: predicts `P(win)`
- `spread_model`: predicts `P(cover)`

Do not force one model to handle both targets. The targets are different and
should be modeled independently.

## Data Requirements

The training set should be side-based:

- each game becomes two rows, one for each team side
- moneyline target: `win = 1` if that side won
- spread target: `cover = 1` if that side covered the closing spread

Only use information available before tipoff.

For MVP, use closing lines as the market inputs and benchmark. That means live
prediction should be treated as a near-tipoff workflow unless earlier odds
snapshots are stored later.

## Features

### Market Features

- closing moneyline
- closing implied probability
- closing spread
- closing total
- bookmaker or consensus-close indicator

### Team Form Features

- rolling win rate
- rolling point differential
- rolling scoring and allowed scoring
- home or away flag
- rest days
- opponent strength proxy

### Rating Features

- Elo-style team rating
- rating difference
- recent form delta

All rolling features must be computed using only games prior to the current
game.

## Model Choices

Start with two model families:

- baseline: regularized logistic regression
- challenger: gradient-boosted trees such as LightGBM or CatBoost

After fitting, calibrate probabilities using:

- Platt scaling, or
- isotonic regression

Calibration matters because bankroll decisions depend on accurate probability
estimates, not just classification rank.

## Betting Policy

The betting policy should decide:

- whether a bet qualifies
- whether to take moneyline or spread
- how much to stake

### Edge Calculation

For moneyline:

- convert American odds to decimal odds
- compute expected value using the model win probability

For spread:

- use the model cover probability and the closing spread price

### Bet Filters

Bet only when:

- expected value is above a minimum threshold
- model confidence is above a minimum threshold
- odds are within allowed bounds
- bankroll and exposure limits permit the bet

### Stake Sizing

Use fractional Kelly as the default policy:

- calculate Kelly fraction from model probability and payout
- multiply by a conservative factor such as `0.25` or `0.50`
- cap max stake per game
- cap total daily exposure

This allows larger positions when the model sees a larger edge while still
protecting bankroll from volatility.

## Backtraining Strategy

Do not train on an entire season and evaluate on that same season.

Use walk-forward evaluation:

1. Train on the previous season.
2. Add current-season games only up to the prediction date.
3. Predict the next block of games.
4. Advance the window and repeat.

Good retraining cadence for MVP:

- weekly, or
- every 3 to 7 days

This gives a realistic simulation of how the system would behave in production.

## Evaluation Metrics

Primary metrics should be bankroll-based:

- ending bankroll
- profit in dollars
- units won
- ROI
- log bankroll growth
- max drawdown

Secondary metrics:

- hit rate
- number of bets
- average odds
- average stake size
- calibration error

Profitability should be the main score, but calibration and drawdown should be
tracked so the model does not simply overbet noisy edges.

## Invocation Workflow

The prediction workflow should:

1. load the trained artifact
2. build features for the current slate
3. score moneyline and spread opportunities
4. compute expected value
5. apply the betting policy
6. output ranked bets with stake recommendations

Expected output for each candidate bet:

- game
- market type
- side
- closing or latest line used
- model probability
- implied probability
- estimated edge
- recommended stake

## Suggested Repository Structure

Add a dedicated modeling package:

- `src/cbb/modeling/dataset.py`
- `src/cbb/modeling/features.py`
- `src/cbb/modeling/ratings.py`
- `src/cbb/modeling/train.py`
- `src/cbb/modeling/infer.py`
- `src/cbb/modeling/backtest.py`
- `src/cbb/modeling/policy.py`
- `src/cbb/modeling/artifacts.py`

Suggested CLI:

- `cbb model train`
- `cbb model backtest`
- `cbb model predict`

Store trained artifacts on disk first, not in Postgres. Use a gitignored
artifacts directory.

## MVP Scope

Build in this order:

1. Moneyline only.
2. Train on previous season plus rolling current-season data.
3. Backtest with bankroll simulation and fractional Kelly sizing.
4. Add prediction output for best current bets.
5. Add spread modeling after historical closing spread coverage is complete.

## Key Constraint

If the model is trained on closing lines, truly pregame predictions are only
honest near tipoff because the close is not known earlier in the day.

So for MVP:

- train against closing lines
- invoke close to game start using the latest available line as a close proxy

If earlier-day predictions become important later, the system should store and
train against historical earlier snapshots in addition to closes.
