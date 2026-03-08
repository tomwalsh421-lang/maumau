"""Feature engineering for betting-model training and inference."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from cbb.modeling.artifacts import ModelMarket
from cbb.modeling.dataset import GameOddsRecord
from cbb.modeling.ratings import (
    TeamSnapshot,
    TeamState,
    build_team_snapshot,
    update_team_states,
)

COMMON_FEATURE_NAMES = (
    "home_side",
    "side_games_played",
    "opponent_games_played",
    "games_played_diff",
    "win_pct_diff",
    "average_margin_diff",
    "average_points_for_diff",
    "average_points_against_diff",
    "elo_diff",
    "rest_days_diff",
    "total_points",
    "has_total_points",
)
MONEYLINE_FEATURE_NAMES = COMMON_FEATURE_NAMES + (
    "market_implied_probability",
    "has_market_line",
    "spread_line",
    "spread_price_implied_probability",
    "has_spread_line",
)
SPREAD_FEATURE_NAMES = COMMON_FEATURE_NAMES + (
    "spread_line",
    "market_implied_probability",
    "has_market_line",
    "moneyline_implied_probability",
    "has_moneyline_line",
)


@dataclass(frozen=True)
class ModelExample:
    """One side-based training or prediction example."""

    game_id: int
    season: int
    commence_time: str
    market: ModelMarket
    team_name: str
    opponent_name: str
    side: str
    features: dict[str, float]
    label: int | None
    settlement: str
    market_price: float | None
    market_implied_probability: float | None
    minimum_games_played: int
    line_value: float | None


def feature_names_for_market(market: ModelMarket) -> tuple[str, ...]:
    """Return the stable feature ordering for one market."""
    if market == "moneyline":
        return MONEYLINE_FEATURE_NAMES
    return SPREAD_FEATURE_NAMES


def build_training_examples(
    *,
    game_records: list[GameOddsRecord],
    market: ModelMarket,
    target_seasons: set[int],
) -> list[ModelExample]:
    """Build sequential training examples for one market."""
    team_states: dict[int, TeamState] = defaultdict(TeamState)
    examples: list[ModelExample] = []

    for record in game_records:
        home_state = team_states[record.home_team_id]
        away_state = team_states[record.away_team_id]
        home_snapshot = build_team_snapshot(home_state, record.commence_time)
        away_snapshot = build_team_snapshot(away_state, record.commence_time)

        if record.season in target_seasons:
            examples.extend(
                _build_examples_for_record(
                    record=record,
                    market=market,
                    home_snapshot=home_snapshot,
                    away_snapshot=away_snapshot,
                )
            )

        if (
            record.completed
            and record.home_score is not None
            and record.away_score is not None
        ):
            update_team_states(
                home_state=home_state,
                away_state=away_state,
                home_score=record.home_score,
                away_score=record.away_score,
                commence_time=record.commence_time,
            )

    return examples


def build_prediction_examples(
    *,
    completed_records: list[GameOddsRecord],
    upcoming_records: list[GameOddsRecord],
    market: ModelMarket,
) -> list[ModelExample]:
    """Build current prediction examples for one market."""
    team_states: dict[int, TeamState] = defaultdict(TeamState)

    for record in completed_records:
        home_state = team_states[record.home_team_id]
        away_state = team_states[record.away_team_id]
        if (
            record.completed
            and record.home_score is not None
            and record.away_score is not None
        ):
            update_team_states(
                home_state=home_state,
                away_state=away_state,
                home_score=record.home_score,
                away_score=record.away_score,
                commence_time=record.commence_time,
            )

    examples: list[ModelExample] = []
    for record in upcoming_records:
        home_snapshot = build_team_snapshot(
            team_states[record.home_team_id], record.commence_time
        )
        away_snapshot = build_team_snapshot(
            team_states[record.away_team_id], record.commence_time
        )
        examples.extend(
            _build_examples_for_record(
                record=record,
                market=market,
                home_snapshot=home_snapshot,
                away_snapshot=away_snapshot,
            )
        )
    return examples


def feature_matrix(
    examples: list[ModelExample],
    feature_names: tuple[str, ...],
) -> list[list[float]]:
    """Convert examples into a matrix matching the artifact feature order."""
    return [
        [example.features[feature_name] for feature_name in feature_names]
        for example in examples
    ]


def labels_for_examples(examples: list[ModelExample]) -> list[int]:
    """Return non-null labels for examples used in training."""
    labels: list[int] = []
    for example in examples:
        if example.label is None:
            continue
        labels.append(example.label)
    return labels


def training_examples_only(examples: list[ModelExample]) -> list[ModelExample]:
    """Filter examples down to trainable rows with non-null labels."""
    return [example for example in examples if example.label is not None]


def _build_examples_for_record(
    *,
    record: GameOddsRecord,
    market: ModelMarket,
    home_snapshot: TeamSnapshot,
    away_snapshot: TeamSnapshot,
) -> list[ModelExample]:
    home_features = _base_feature_map(
        home_side=True,
        side_snapshot=home_snapshot,
        opponent_snapshot=away_snapshot,
        total_points=record.total_points,
    )
    away_features = _base_feature_map(
        home_side=False,
        side_snapshot=away_snapshot,
        opponent_snapshot=home_snapshot,
        total_points=record.total_points,
    )
    minimum_games_played = min(home_snapshot.games_played, away_snapshot.games_played)
    home_moneyline_probability = normalized_implied_probability_from_prices(
        side_american_price=record.home_h2h_price,
        opponent_american_price=record.away_h2h_price,
    )
    away_moneyline_probability = normalized_implied_probability_from_prices(
        side_american_price=record.away_h2h_price,
        opponent_american_price=record.home_h2h_price,
    )
    home_spread_probability = normalized_implied_probability_from_prices(
        side_american_price=record.home_spread_price,
        opponent_american_price=record.away_spread_price,
    )
    away_spread_probability = normalized_implied_probability_from_prices(
        side_american_price=record.away_spread_price,
        opponent_american_price=record.home_spread_price,
    )

    if market == "moneyline":
        home_features.update(
            _moneyline_feature_map(
                market_implied_probability=home_moneyline_probability,
                spread_line=record.home_spread_line,
                spread_price_implied_probability=home_spread_probability,
            )
        )
        away_features.update(
            _moneyline_feature_map(
                market_implied_probability=away_moneyline_probability,
                spread_line=record.away_spread_line,
                spread_price_implied_probability=away_spread_probability,
            )
        )
        return [
            ModelExample(
                game_id=record.game_id,
                season=record.season,
                commence_time=record.commence_time.isoformat(),
                market=market,
                team_name=record.home_team_name,
                opponent_name=record.away_team_name,
                side="home",
                features=home_features,
                label=_moneyline_label(record.home_score, record.away_score),
                settlement=_moneyline_settlement(record.home_score, record.away_score),
                market_price=record.home_h2h_price,
                market_implied_probability=home_moneyline_probability,
                minimum_games_played=minimum_games_played,
                line_value=record.home_h2h_price,
            ),
            ModelExample(
                game_id=record.game_id,
                season=record.season,
                commence_time=record.commence_time.isoformat(),
                market=market,
                team_name=record.away_team_name,
                opponent_name=record.home_team_name,
                side="away",
                features=away_features,
                label=_moneyline_label(record.away_score, record.home_score),
                settlement=_moneyline_settlement(record.away_score, record.home_score),
                market_price=record.away_h2h_price,
                market_implied_probability=away_moneyline_probability,
                minimum_games_played=minimum_games_played,
                line_value=record.away_h2h_price,
            ),
        ]

    spread_examples: list[ModelExample] = []
    for example in [
        (
            "home",
            record.home_team_name,
            record.away_team_name,
            home_features,
            record.home_spread_line,
            record.home_spread_price,
            record.home_h2h_price,
            home_spread_probability,
            record.home_score,
            record.away_score,
        ),
        (
            "away",
            record.away_team_name,
            record.home_team_name,
            away_features,
            record.away_spread_line,
            record.away_spread_price,
            record.away_h2h_price,
            away_spread_probability,
            record.away_score,
            record.home_score,
        ),
    ]:
        (
            side,
            team_name,
            opponent_name,
            feature_map,
            spread_line,
            spread_price,
            moneyline_price,
            spread_implied_probability,
            side_score,
            opponent_score,
        ) = example
        if spread_line is None or spread_price is None:
            continue
        feature_map.update(
            _spread_feature_map(
                spread_line=spread_line,
                market_implied_probability=spread_implied_probability,
                moneyline_implied_probability=normalized_implied_probability_from_prices(
                    side_american_price=moneyline_price,
                    opponent_american_price=(
                        record.away_h2h_price
                        if side == "home"
                        else record.home_h2h_price
                    ),
                ),
            )
        )
        label, settlement = _spread_outcome(
            side_score=side_score,
            opponent_score=opponent_score,
            spread_line=spread_line,
        )
        spread_examples.append(
            ModelExample(
                game_id=record.game_id,
                season=record.season,
                commence_time=record.commence_time.isoformat(),
                market=market,
                team_name=team_name,
                opponent_name=opponent_name,
                side=side,
                features=feature_map,
                label=label,
                settlement=settlement,
                market_price=spread_price,
                market_implied_probability=spread_implied_probability,
                minimum_games_played=minimum_games_played,
                line_value=spread_line,
            )
        )
    return spread_examples


def _base_feature_map(
    *,
    home_side: bool,
    side_snapshot: TeamSnapshot,
    opponent_snapshot: TeamSnapshot,
    total_points: float | None,
) -> dict[str, float]:
    return {
        "home_side": 1.0 if home_side else 0.0,
        "side_games_played": float(side_snapshot.games_played),
        "opponent_games_played": float(opponent_snapshot.games_played),
        "games_played_diff": float(
            side_snapshot.games_played - opponent_snapshot.games_played
        ),
        "win_pct_diff": side_snapshot.win_pct - opponent_snapshot.win_pct,
        "average_margin_diff": (
            side_snapshot.average_margin - opponent_snapshot.average_margin
        ),
        "average_points_for_diff": (
            side_snapshot.average_points_for - opponent_snapshot.average_points_for
        ),
        "average_points_against_diff": (
            side_snapshot.average_points_against
            - opponent_snapshot.average_points_against
        ),
        "elo_diff": side_snapshot.elo - opponent_snapshot.elo,
        "rest_days_diff": side_snapshot.rest_days - opponent_snapshot.rest_days,
        "total_points": total_points or 0.0,
        "has_total_points": 1.0 if total_points is not None else 0.0,
    }


def _moneyline_feature_map(
    *,
    market_implied_probability: float | None,
    spread_line: float | None,
    spread_price_implied_probability: float | None,
) -> dict[str, float]:
    return {
        "market_implied_probability": _default_probability(market_implied_probability),
        "has_market_line": 1.0 if market_implied_probability is not None else 0.0,
        "spread_line": spread_line or 0.0,
        "spread_price_implied_probability": _default_probability(
            spread_price_implied_probability
        ),
        "has_spread_line": 1.0 if spread_line is not None else 0.0,
    }


def _spread_feature_map(
    *,
    spread_line: float,
    market_implied_probability: float | None,
    moneyline_implied_probability: float | None,
) -> dict[str, float]:
    return {
        "spread_line": spread_line,
        "market_implied_probability": _default_probability(market_implied_probability),
        "has_market_line": 1.0 if market_implied_probability is not None else 0.0,
        "moneyline_implied_probability": _default_probability(
            moneyline_implied_probability
        ),
        "has_moneyline_line": 1.0 if moneyline_implied_probability is not None else 0.0,
    }


def _moneyline_label(side_score: int | None, opponent_score: int | None) -> int | None:
    if side_score is None or opponent_score is None:
        return None
    return 1 if side_score > opponent_score else 0


def _moneyline_settlement(
    side_score: int | None,
    opponent_score: int | None,
) -> str:
    label = _moneyline_label(side_score, opponent_score)
    if label is None:
        return "pending"
    return "win" if label == 1 else "loss"


def _spread_outcome(
    *,
    side_score: int | None,
    opponent_score: int | None,
    spread_line: float,
) -> tuple[int | None, str]:
    if side_score is None or opponent_score is None:
        return None, "pending"
    margin_with_line = float(side_score - opponent_score) + spread_line
    if margin_with_line > 0:
        return 1, "win"
    if margin_with_line < 0:
        return 0, "loss"
    return None, "push"


def _default_probability(probability: float | None) -> float:
    if probability is None:
        return 0.5
    return probability


def implied_probability_from_american(american_price: float | None) -> float | None:
    """Convert American odds into implied win probability."""
    if american_price is None:
        return None
    if american_price > 0:
        return 100.0 / (american_price + 100.0)
    if american_price < 0:
        return -american_price / (-american_price + 100.0)
    return None


def normalized_implied_probability_from_prices(
    *,
    side_american_price: float | None,
    opponent_american_price: float | None,
) -> float | None:
    """Convert a two-sided market into a no-vig side probability when possible."""
    side_probability = implied_probability_from_american(side_american_price)
    opponent_probability = implied_probability_from_american(opponent_american_price)
    if side_probability is None:
        return None
    if opponent_probability is None:
        return side_probability

    total_probability = side_probability + opponent_probability
    if total_probability <= 0:
        return None
    return side_probability / total_probability
