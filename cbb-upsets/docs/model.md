# Model

Canonical links:

- [Repository README](../README.md)
- [System Architecture](architecture.md)
- [Current Best-Model Report](results/best-model-5y-backtest.md)

This document explains the durable modeling approach: inputs, feature families,
training flow, calibration, and evaluation method. Current tuned settings and
season-by-season performance live in the generated report, not in this doc.

## Model Overview

The modeling layer predicts pregame betting probabilities for NCAA men's
basketball games. It currently supports two markets:

- moneyline: probability that a selected team wins the game outright
- spread: probability that a selected side covers the listed spread, derived
  from an expected margin-versus-market estimate rather than a direct binary
  cover classifier

The output is not a raw classification label. The system produces calibrated
side-level probabilities, compares them to market prices, and then passes those
scores through a betting policy that decides whether a wager is actionable.
Model fitting and calibration stay anchored to the modeled market view, while
bet sizing now evaluates every currently executable bookmaker quote and uses
the best available line or price that clears policy.

For spread only, the repository also has an opt-in timing layer. That auxiliary
model estimates whether the currently available early spread is likely to beat
the eventual close, using the existing open/close move features plus bookmaker
depth and dispersion as practical low-profile proxies. When enabled, the system
bets early only when that predicted close move is favorable and otherwise marks
the candidate as a wait.

The deployable strategy market is `best`. In the current implementation,
`best` uses spread only when a spread artifact is available, and only falls
back to moneyline when spread cannot train or load. The default deployable
spread policy is a fixed searched policy rather than the older walk-forward
auto-tuned path; auto-tuning still exists as an opt-in research mode. That
fixed policy now includes a small schedule-quality guard so extreme rest-gap
situations are filtered out before staking, and it now also caps the same-day
spread card at five bets so the board stays concentrated on the top-ranked
opportunities rather than reopening the heaviest slates. It also applies a
small spread-only conservative probability buffer before edge gating and Kelly
sizing. That policy guard now sits on top of a learned heteroskedastic spread
residual scale keyed off line size, season phase, and book depth rather than a
single global spread uncertainty assumption. The opt-in spread auto-tuner now
works off replay-safe candidate blocks: it sweeps the core threshold grid
first, then does a bounded pass over support controls such as
`min_positive_ev_books` and `min_median_expected_value`, then does one final
threshold refinement pass around the best replayable challenger. The live
prediction output also
surfaces conservative bankroll controls and an uncertainty disclosure so users
can see current loss limits and which important information classes are still
missing. The default
report/live bankroll assumption is now a notional `+$3,750.00`, which keeps
the typical qualified stake close to one `$25` unit unless the operator
overrides that scale from the CLI. The v1 predict
contract also exposes a canonical JSON payload with one deterministic per-game
status:
`bet`, `wait`, or `pass`, plus the selected sportsbook and cross-book
survivability context behind that decision.

## Prediction Goal

The goal is to turn stored game history and betting-market information into
probabilities that are usable for decision-making.

That means the model is trying to answer questions such as:

- "What is the probability this team wins outright?"
- "What is the probability this side covers the current spread?"
- "Is the model's probability meaningfully different from the market price?"

The system is optimized for betting use, so calibration and bankroll results
matter more than raw classification accuracy alone.

There is now one bounded non-betting wrapper around that same probability
engine: `cbb model tournament`. It uses the moneyline artifact to fill the
tracked NCAA bracket spec for the current men's field. Real live First Four
and round-of-64 rows use stored upcoming market records when they exist, while
later rounds are scored as synthetic neutral-site matchups so the full bracket
can be completed before those games have lines. When a bracket matchup has no
usable moneyline market row, that wrapper now falls back to a separate
tournament-only logistic model trained on the common team-state feature set
instead of pushing zero-filled market fields through the main moneyline
artifact. That path is for bracket guidance and advancement odds, not for the
promoted live betting policy.
For completed years, `cbb model tournament-backtest` replays the tracked local
`2023-2025` men's bracket specs, retrains one moneyline artifact per evaluation
season using only games available through the first play-in tip, freezes any
known early-round market rows at that anchor, applies the same marketless
fallback logic to synthetic rows, and then compares deterministic bracket picks
against the actual tournament path. That backtest is an honesty check on the
bracket wrapper, not a promotion lane for the live deployable betting policy.

That same interpretation now carries into the local dashboard UI: it surfaces
ROI, drawdown, probability edge, expected value, and closing-market quality in
plain English, with close-EV and price/no-vig context treated as more decision-
relevant than raw spread line CLV by itself.

## Data Inputs

The model combines four input categories:

- historical game results from ESPN, including scores, game times, and stored
  neutral-site / postseason / venue metadata
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
- schedule context: rest-day differential, a home-side indicator, and a
  same-conference flag
- market features: implied probabilities and line values from the side being
  priced
- bookmaker-consensus features: opening and closing consensus prices across
  books, cross-book dispersion, and book count
- line-move features: changes from market open to market close, plus
  model-versus-consensus value signals
- bookmaker-quality features: weighted quote views, best-vs-weighted book
  edges, and residual-based quality signals learned from prior completed games
- totals-market features: total open, total close, total move, total
  dispersion, and spread/total interaction terms
- conference context: persisted team conference metadata used for same-
  conference features and conference-aware spread stabilization
- offseason-regime proxies: season openers, early-season flags, Elo carryover
  from the prior season, and in-season Elo shift relative to that carryover
- cross-market context: the moneyline model sees spread context and the spread
  model sees moneyline context

The feature set is intentionally explicit and relatively small so that training,
backtesting, and debugging stay fast and repeatable.

Bookmaker-quality weighting is also intentionally damped on spread. Repaired
historical market coverage now changes the path-dependent bookmaker error state
more often than the earlier thinner dataset did, so spread quote weighting uses
a heavier prior and a bounded weight transform when history is still sparse.
That keeps repaired backfills from swinging weighted spread quote features too
far on only a small amount of newly recovered book history, while still
allowing stable long-run book differentiation once observations accumulate.

The repository can now store official player-availability reports in shadow
form through `cbb ingest availability` for audit and coverage review. That
lane now includes the NCAA tournament wrapper plus wrapped free-source 2026
conference archive captures, but the promoted live prediction, backtest, and
betting-policy paths still do not consume those fields yet. The current
coverage is materially better for diagnostics, not yet strong enough for live
promotion, so where those signals matter today the model still relies on
practical proxies such as early-season regime flags and market movement.
The live prediction contract can now attach additive per-game availability
shadow context to current upcoming and live-board rows when stored official
reports exist, and it now also summarizes how many upcoming rows currently
carry that stored coverage plus how fresh the covered reports are, but the
metadata is descriptive only and does not change qualification, ranking, or
staking.

The data layer now also stores neutral-site, season-type, tournament-note, and
venue metadata from ESPN historical ingest, and the repo now tracks a
home-location catalog in `data/team_home_locations.csv` so report-time travel
and timezone diagnostics are reproducible. The first direct walk-forward
challenger that added those travel values to the trained feature vector helped
`2026` but regressed `2024` and the full window, so the promoted baseline
still does not feed travel-distance, altitude, or timezone-aware inputs into
the trained model or staking logic.

## Model Type

Moneyline and spread use related but not identical deployable models.

Moneyline uses a regularized logistic regression model. Spread uses a
regularized linear residual model that predicts expected margin relative to the
market line, then converts that margin estimate into a cover probability before
calibration. In CLI terms, that deployable spread baseline still sits behind
the `logistic` family setting. These linear defaults were chosen because they
are:

- easy to retrain often during walk-forward backtests
- cheap to store and load as a JSON artifact
- stable enough to debug when feature or data changes move results
- transparent enough that probability shifts can usually be traced back to
  inputs

For spread only, the repository also supports a histogram gradient-boosted tree
challenger. That path is useful for research, but it is not the default
deployment family unless it beats the linear residual baseline on walk-forward
seasonal results.

Moneyline uses one extra layer beyond a single global model. The artifact can
store specialized band models for different price ranges and route a game to
the matching band at scoring time. This exists because moneyline behavior is
not equally well-behaved across the full price curve.

That segmentation is meant to sharpen the model inside the existing anti-
longshot guardrails, not to widen them. The default deployable moneyline cap
still stays on the short end of the dog curve, while favorites, balanced
prices, and capped short dogs can each calibrate differently instead of
sharing one global stabilization rule.

## Training Process

Training is performed from stored Postgres data, not directly from the upstream
APIs.

At a high level, training does this:

1. load the completed games and pregame odds for the selected seasons
2. rebuild rolling team state in chronological order
3. emit one example per side for the requested market
4. keep only priced, deployable examples for the target market
5. fit the selected model family on the engineered features
   For spread, the deployable linear path fits expected cover margin relative
   to the current line, not a raw cover/no-cover label.
6. fit calibration parameters on held-out priced examples
7. save the trained artifact under `artifacts/models/`

By default the repository trains on a rolling five-season window. Moneyline
training is intentionally narrower than the full market universe; the current
default training band is centered on the prices the deployable strategy is most
likely to use.

## Calibration

Raw model outputs are not treated as ready-to-bet probabilities.

The current calibration stack includes:

- For spread, a raw margin-residual estimate is first converted into cover
  probability using a learned residual scale.
- for spread, the residual scale can also widen or tighten by spread absolute
  line, season phase, and spread book depth so long lines, early-season games,
  and thinner markets do not have to share one identical uncertainty level
- Platt scaling on held-out priced examples
- market blending, which shrinks predictions back toward the implied market
  probability
- for moneyline, segment-aware stabilization so heavy favorites, favorites,
  balanced prices, and capped short dogs do not all share the same calibration
  controls
- for spread, optional absolute-line bucket overrides for market blend and
  market-delta controls so short spreads and wider spreads do not have to share
  one identical stabilization setting
- for spread, optional season-phase overrides keyed off minimum in-season games
  played, so season openers and early-season games can stay closer to market
  than established conference-play games
- for spread, additive conference-aware stabilization so some team-conference
  contexts can stay closer to market than others without changing the core
  linear model family
- a maximum market delta cap, which prevents the model from drifting too far
  away from the market on one example

Those spread-specialized overrides are now kept only when they beat the default
spread calibration on a later held-out slice from the same scoped bucket. That
guard applies to absolute-line, conference, and season-phase overrides, and it
exists specifically to keep repaired-data segmentation from surviving purely on
same-sample wins.

The timing layer is separate from this probability calibration stack. It does
not change the cover model itself; it decides whether an early spread number is
worth taking now versus waiting for more market information. Its feature set now
includes explicit early-season and offseason-regime proxies in addition to line
movement, dispersion, and book-depth features. The artifact can now store
separate timing models for lower-profile versus higher-profile games, with book
depth acting as the practical profile split and the older single timing model
remaining as a backward-compatible fallback.

Execution is a separate step from calibration. After the model produces a side
probability, the live and backtest paths enumerate the latest available quotes
across books, reprice spread probabilities at each executable line, require the
side to stay positive EV across a minimum number of books, and then keep the
best surviving quote per game side before bankroll limits are applied. The
current deployable spread default uses `min_positive_ev_books=4`, a `0.040`
expected-value floor, a `0.040` probability-edge floor, `8` minimum prior
games per team, and a five-bet same-day top-of-board cap that trims the
heaviest slates before staking. Before that edge check, spread quotes now
convert the model's point estimate into a conservative lower-bound
probability. That lower-bound check is informed by both the learned
heteroskedastic spread residual scale and the remaining quote-level policy
buffer, and it is also used for fractional Kelly sizing so noisy quotes are
both harder to qualify and sized more cautiously when they do qualify.

Calibration is important because betting decisions are highly sensitive to
probability error. A model can have decent classification accuracy and still be
bad for wagering if it is systematically overconfident.

## Model Improvement Strategy

The model improves through a combination of better data, better features, and
more disciplined evaluation.

That evaluation loop now includes the canonical `cbb model report` segment
tables for qualified spread bets, so the current report can show whether ROI
and spread close EV are concentrated in specific expected-value tails,
probability-edge tails, line, depth, conference, or timing regimes before
policy changes are promoted. The report also keeps a short decision snapshot
and close-market coverage summary near the top, because the repo's strongest
current evidence still depends on how much of the settled bet set has matched
close diagnostics. The report now also shows capital-deployment diagnostics,
including requested-versus-placed stake capture, active-day exposure usage,
and how often same-day bet caps or daily exposure caps actually bind the
portfolio before Kelly or exposure widening is approved.

The local dashboard is intentionally read-only against that same evaluation
stack. Its recent-performance and pick-history pages are built from the
canonical dashboard snapshot generated alongside `cbb model report`, plus the
current prediction path, so the UI stays aligned with the canonical backtest
and live decision surfaces without rebuilding the heavy historical report on
every request.
Alias-aware team search is a navigation aid only; it does not change model
inputs, team identity, or evaluation semantics.

The current improvement path is:

- expand and audit historical odds coverage so more examples are trainable
- add richer bookmaker-consensus and line-move features
- learn bookmaker quality within NCAA men's basketball before widening scope,
  because bookmaker information flow and execution quality are market-specific
- keep improving spread-first deployment, because spread has been more stable
  than moneyline
- keep spread calibration regime-aware so season openers, early-season games,
  and established-game contexts do not all share one identical NCAA spread
  stabilization rule
- keep spread uncertainty regime-aware so long lines, early-season games, and
  low-depth markets can widen or tighten the residual distribution instead of
  sharing one global spread sigma
- keep the default deployable spread policy fixed and explicit, and treat the
  auto-tuned spread policy path as a research comparison unless it clearly
  outperforms the fixed deployable baseline
- keep spread staking conservative under uncertainty by qualifying and sizing
  quotes off a lower-bound spread probability, not only the point estimate
- qualify cross-book spread execution on survivability first, then stake only
  the best surviving quote; research controls can tighten this with higher
  positive-EV book counts or a minimum median EV across eligible books
- keep the fixed spread baseline strict enough to hold up across the full
  five-season window, even if that means fewer bets than looser research
  variants
- keep spread policy tuning deployable by requiring both enough activity and
  non-negative out-of-sample spread close quality, then rank surviving
  candidates by total walk-forward profit before ROI and stability tiebreakers
- recover moneyline in tighter price segments before widening deployment
- compare the linear residual spread baseline against stronger challenger models such
  as gradient-boosted trees, and only promote them if per-season walk-forward
  results improve
- keep live and backtest policy search aligned so the fixed deployable spread
  baseline and any opt-in auto-tuned comparison are evaluated consistently

## Evaluation

The primary evaluation method is walk-forward backtesting, not the training-set
metrics printed after `model train`.

The main evaluation signals are:

- bankroll profit and ROI
- units won and bet volume
- max drawdown
- per-season behavior, not just one aggregate number
- training metrics such as log loss, Brier score, and accuracy
- closing-line value, tracked separately from ROI so early-entry strategies can
  be judged on whether they actually beat the market close; for spread this now
  includes line movement, price/no-vig close deltas, and model EV at the close

This matters because a deployable betting model must be judged on how it would
have behaved under realistic retraining and staking rules. The repository can
also evaluate one season at a time, which is the right way to see whether a
positive latest-season result is stable or just recent noise.
