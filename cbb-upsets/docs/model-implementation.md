# Betting Model Implementation

## Current Scope

The implemented model stack is a baseline betting workflow built around:

- a native logistic-regression trainer
- rolling team-form and Elo-style features
- optional market features when stored odds are available
- a bankroll-aware betting policy
- walk-forward backtesting
- prediction of current upcoming bets

As of March 8, 2026:

- the free ESPN game history covers the loaded three-season corpus
- the paid historical moneyline-close backfill has been run for season `2026`
- older `2024` and `2025` seasons still do not have full historical closes
- spread history is still incomplete and should not be treated as production
  quality

The code lives under `src/cbb/modeling/` and is exposed through:

- `cbb model train`
- `cbb model backtest`
- `cbb model predict`

## What Is Trained

Two separate artifacts can be trained:

- `moneyline`: predicts the probability that one side wins outright
- `spread`: predicts the probability that one side covers the spread

Training is side-based:

- each game becomes two examples
- one example is the home side
- one example is the away side

The current baseline uses:

- rolling win percentage
- rolling scoring margin
- rolling points for and against
- home-side flag
- rest-day difference
- Elo difference
- totals and line-derived features when present

After the `2026` moneyline-close backfill, the current moneyline artifact was
trained with:

- `33,984` side-based training examples
- `9,264` priced examples with stored moneyline context

## Default Training Behavior

`cbb model train` defaults to:

- market: `moneyline`
- seasons back: `3`
- epochs: `100`
- learning rate: `0.05`
- L2 penalty: `0.001`
- minimum examples: `50`

Artifacts are written under `artifacts/models/`.

If you train with a custom artifact name, for example:

```bash
cbb model train --artifact-name initial_algo
```

the command writes both:

- `artifacts/models/moneyline_initial_algo.json`
- `artifacts/models/moneyline_latest.json`

That lets `cbb model predict` work without forcing you to pass
`--artifact-name` every time.

## What `cbb model predict` Does

`cbb model predict`:

1. loads the trained artifact or artifacts
2. loads completed games to rebuild rolling team state
3. loads upcoming games in the prediction window
4. scores both sides of each eligible market
5. filters out bets that fail the policy thresholds
6. applies bankroll sizing and daily exposure caps
7. returns ranked recommendations

The default `best` mode loads both `moneyline` and `spread` artifacts when
available. It then keeps at most one bet per game, choosing the candidate with
the strongest expected value.

## Prediction Output

Each prediction row includes:

- local game time
- team and opponent
- market and line used
- `model`: the model-estimated probability
- `implied`: the sportsbook implied probability from the American odds
- `edge`: expected profit per dollar staked based on the model probability
- `stake`: recommended dollar stake and bankroll fraction

Example:

```text
2026-03-08 18:00 EDT | Southern Miss Golden Eagles vs Troy Trojans | spread +3.5 @ -110 | model=0.792 | implied=0.524 | edge=0.511 | stake=$50.00 (0.050)
```

Interpretation:

- the model estimates a `79.2%` cover probability
- the sportsbook price implies about `52.4%`
- the expected value calculation is strongly positive
- the policy capped the stake at `5%` of a `$1000` bankroll

## Default Betting Policy

The default policy is:

- minimum edge: `0.01`
- minimum confidence: `0.50`
- Kelly fraction: `0.25`
- max bet fraction: `0.05`
- max daily exposure fraction: `0.20`

That means the model does not simply rank edges. It also decides:

- whether the bet is worth taking
- how much of bankroll to commit
- how to avoid overexposure on one day

## Backtest Behavior

`cbb model backtest` uses walk-forward evaluation.

Default behavior:

- market: `best`
- seasons back: `3`
- evaluation season: latest loaded season
- retrain cadence: every `30` days
- starting bankroll: `$1000`
- unit size: `$25`

For each evaluation block, the model:

1. trains on prior completed games only
2. scores the next block of games
3. places bets that pass the policy
4. settles those bets into bankroll
5. advances the window

## Current Backtest Snapshot

Live run on the current database on March 8, 2026:

```bash
cbb model backtest --market moneyline
```

Result:

- seasons: `2024..2026`
- evaluation season: `2026`
- blocks: `5`
- candidates: `2,174`
- bets placed: `493`
- wins: `231`
- losses: `262`
- profit: `$-962.64`
- ending bankroll: `$37.36`
- ROI: `-0.3404`
- units won: `-38.51`
- max drawdown: `0.9630`
- total staked: `$2,827.68`

## How Good Is It Right Now

The honest answer: the current moneyline model is not good enough.

What this backtest tells us:

- the pipeline is now using a much more realistic moneyline-close sample
- once that richer price history is included, the model performs badly
- the model is overestimating some long-shot underdogs and creating false edge
- the bankroll policy then turns those bad probabilities into real losses

So the current system is useful as a real baseline and a working research
pipeline, but it is not a deployable betting model.

## Important Limitations

The current implementation still has important limits:

- historical game coverage is strong, but historical odds coverage is partial
- moneyline training now has a meaningful current-season close sample, but
  `2024` and `2025` still lack full historical closes
- within season `2026`, `4,623` of `5,453` completed games currently have a
  stored closing moneyline, leaving `830` completed games without one
- spread artifacts currently train on a much smaller dataset than moneyline
- probabilities are not yet calibrated with Platt scaling or isotonic
- there is no feature store for earlier-day snapshots yet
- the current policy has no odds-range sanity filter, so extreme plus-money
  underdogs can still generate oversized apparent edges if the model is
  miscalibrated

Because of that, the backtest should be treated as a directional benchmark, not
as final proof of edge.

## Recommended Next Steps

- finish the remaining unmatched `2026` moneyline-close gaps, then backfill
  older seasons when quota allows
- store and use more historical spread snapshots before trusting spread output
- add odds-range and price-sanity filters before trusting raw Kelly sizing
- add probability calibration
- compare the logistic baseline against a tree-based challenger
- track CLV once earlier and closing snapshots are both stored
