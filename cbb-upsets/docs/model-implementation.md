# Betting Model Implementation

## Current Scope

The implemented model stack is now a conservative deployable moneyline workflow
built around:

- a native logistic-regression trainer
- rolling team-form and Elo-style features
- no-vig market probabilities derived from stored prices
- out-of-sample Platt calibration on held-out priced examples
- validation-selected shrinkage back toward the market
- a bankroll-aware betting policy with hard deployment rails
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

The current moneyline implementation uses:

- rolling win percentage
- rolling scoring margin
- rolling points for and against
- games played for each side
- home-side flag
- rest-day difference
- Elo difference
- totals and line-derived features when present
- no-vig market implied probability from the stored close or latest pregame line

For deployment, moneyline training only uses side examples that have stored
pregame prices. Unpriced games still matter because they feed the rolling team
state that produces the feature snapshots.

After the `2026` moneyline-close backfill, the current deployable moneyline
artifact was trained with:

- `33,984` side-based training examples
- `9,264` priced deployable training examples

## Default Training Behavior

`cbb model train` defaults to:

- market: `moneyline`
- seasons back: `3`
- epochs: `100`
- learning rate: `0.05`
- L2 penalty: `0.001`
- minimum examples: `50`

Artifacts are written under `artifacts/models/`.

During training, the moneyline artifact now also learns:

- Platt scaling parameters from an out-of-sample priced calibration slice
- a market blend weight chosen on a held-out priced validation slice
- a maximum allowed probability deviation from the market

That means the deployed probability is not the raw logistic output. It is first
calibrated on held-out priced data, then shrunk back toward the market so it
stays close to the price unless the data supports a measured deviation.

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
- `implied`: the no-vig sportsbook implied probability from the stored prices
- `prob_edge`: the model minus market probability difference
- `edge`: expected profit per dollar staked based on the model probability
- `stake`: recommended dollar stake and bankroll fraction

Example:

```text
2026-03-08 15:30 EDT | Green Bay Phoenix vs Northern Kentucky Norse | moneyline +124 | model=0.468 | implied=0.428 | prob_edge=0.040 | edge=0.048 | stake=$3.89 (0.004)
```

Interpretation:

- the model estimates a `46.8%` win probability
- the stored line implies about `42.8%` after removing vig
- the model only sees a `4.0%` probability edge, so the stake stays small
- the policy sized the bet at well under `1%` of a `$1000` bankroll

## Default Betting Policy

The default policy is:

- minimum EV edge: `0.02`
- minimum confidence: `0.00`
- minimum probability edge versus market: `0.025`
- minimum prior games per team: `8`
- Kelly fraction: `0.10`
- max bet fraction: `0.02`
- max daily exposure fraction: `0.05`
- moneyline price band: `-500` through `+400`

That means the model does not simply rank edges. It also decides:

- whether the bet is worth taking
- how much of bankroll to commit
- how to avoid overexposure on one day
- whether the market is too extreme to trust with the current data
- whether both teams have enough prior sample to support a bet

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
- candidates: `0`
- bets placed: `0`
- wins: `0`
- losses: `0`
- profit: `$0.00`
- ending bankroll: `$1000.00`
- ROI: `0.0000`
- units won: `0.00`
- max drawdown: `0.0000`
- total staked: `$0.00`

## How Good Is It Right Now

The honest answer: the deployed default is now safe enough to use, but it is
still not a high-confidence edge model.

What this backtest tells us:

- the model no longer forces action just because it can compute a probability
- the deployment rails are strong enough to block the bad long-shot behavior
  that previously destroyed bankroll
- with the currently loaded historical close coverage, the honest default result
  is often "no bet"

That is a better deployment posture than the earlier version, which placed many
bad bets and lost heavily. The system is now usable as a conservative betting
engine and a safer research baseline.

## Important Limitations

The current implementation still has important limits:

- historical game coverage is strong, but historical odds coverage is partial
- moneyline training now has a meaningful current-season close sample, but
  `2024` and `2025` still lack full historical closes
- within season `2026`, `4,623` of `5,453` completed games currently have a
  stored closing moneyline, leaving `830` completed games without one
- spread artifacts currently train on a much smaller dataset than moneyline
- the Platt calibration layer is still trained on a relatively small priced
  holdout compared with what a mature production system would want
- there is no feature store for earlier-day snapshots yet
- older seasons do not have enough paid historical close coverage yet for a
  full multi-season deployable walk-forward test

Because of that, the backtest should be treated as a directional benchmark, not
as final proof of edge.

## Recommended Next Steps

- finish the remaining unmatched `2026` moneyline-close gaps, then backfill
  older seasons when quota allows
- store and use more historical spread snapshots before trusting spread output
- compare the current Platt-plus-market calibration against isotonic or stacked
  calibration on a larger priced corpus
- compare the logistic baseline against a tree-based challenger
- track CLV once earlier and closing snapshots are both stored
