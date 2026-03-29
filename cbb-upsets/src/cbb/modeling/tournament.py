"""Tournament-mode bracket prediction built on the moneyline model."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from random import Random
from typing import Protocol

import orjson

from cbb.db import REPO_ROOT, get_engine
from cbb.ingest.matching import best_alias_score, build_team_aliases
from cbb.ingest.utils import derive_cbb_season
from cbb.modeling.artifacts import (
    DEFAULT_ARTIFACT_NAME,
    ModelArtifact,
    load_artifact,
)
from cbb.modeling.dataset import (
    GameOddsRecord,
    MarketSnapshotAggregate,
    OddsSnapshotRecord,
    derive_game_record_at_observation_time,
    get_available_seasons,
    load_completed_game_records,
    load_live_board_game_records,
)
from cbb.modeling.features import (
    COMMON_FEATURE_NAMES,
    PredictionFeatureContext,
    build_prediction_context,
    build_prediction_examples_from_context,
    build_training_examples,
    training_examples_only,
)
from cbb.modeling.train import (
    DEFAULT_MODEL_SEASONS_BACK,
    LogisticRegressionConfig,
    _build_training_metrics,
    _fit_probability_model,
    resolve_training_seasons,
    score_examples,
    train_artifact_from_records,
)
from cbb.team_catalog import load_team_catalog_from_database

DEFAULT_TOURNAMENT_BRACKET_DIR = REPO_ROOT / "data" / "tournaments"
DEFAULT_TOURNAMENT_BRACKET_PATH = DEFAULT_TOURNAMENT_BRACKET_DIR / "ncaa_men_2026.json"
LIVE_MATCHUP_SOURCE = "live_market"
SYNTHETIC_MATCHUP_SOURCE = "synthetic_neutral_site"
ACTUAL_MATCHUP_SOURCE = "actual_result"
LIVE_MARKET_ARTIFACT_SOURCE = "moneyline_market_artifact"
SYNTHETIC_FALLBACK_ARTIFACT_SOURCE = "synthetic_common_feature_artifact"
TOURNAMENT_SYNTHETIC_FEATURE_NAMES = COMMON_FEATURE_NAMES
FAVORITE_PICK_SEED_ROLE = "favorite_pick"
UPSET_PICK_SEED_ROLE = "upset_pick"
SAME_SEED_PICK_ROLE = "same_seed_pick"
TOURNAMENT_SYNTHETIC_UPSET_FLOOR = 0.60
TOURNAMENT_PICK_SEED_ROLE_ORDER = (
    FAVORITE_PICK_SEED_ROLE,
    UPSET_PICK_SEED_ROLE,
    SAME_SEED_PICK_ROLE,
)


@dataclass(frozen=True)
class TournamentOptions:
    """Options for tournament-mode bracket generation."""

    artifact_name: str = DEFAULT_ARTIFACT_NAME
    bracket_path: Path = DEFAULT_TOURNAMENT_BRACKET_PATH
    simulations: int = 5000
    database_url: str | None = None
    artifacts_dir: Path | None = None
    now: datetime | None = None
    random_seed: int = 20260318


@dataclass(frozen=True)
class TournamentBacktestOptions:
    """Options for prior-years tournament backtesting."""

    seasons: int = DEFAULT_MODEL_SEASONS_BACK
    max_season: int | None = None
    bracket_dir: Path = DEFAULT_TOURNAMENT_BRACKET_DIR
    database_url: str | None = None
    now: datetime | None = None
    training_seasons_back: int = DEFAULT_MODEL_SEASONS_BACK
    config: LogisticRegressionConfig = field(default_factory=LogisticRegressionConfig)


@dataclass(frozen=True)
class TournamentParticipantSpec:
    """One tournament bracket participant or play-in dependency."""

    seed: int
    team_name: str | None = None
    play_in_game_key: str | None = None


@dataclass(frozen=True)
class TournamentPlayInGameSpec:
    """One First Four play-in game."""

    game_key: str
    region: str
    seed: int
    scheduled_time: datetime
    teams: tuple[str, str]
    venue_city: str | None = None
    venue_state: str | None = None


@dataclass(frozen=True)
class TournamentRoundOf64GameSpec:
    """One round-of-64 game in a named region."""

    game_key: str
    scheduled_time: datetime
    home: TournamentParticipantSpec
    away: TournamentParticipantSpec
    venue_city: str | None = None
    venue_state: str | None = None
    actual_winner_team_name: str | None = None


@dataclass(frozen=True)
class TournamentRegionSiteSpec:
    """Region-specific sweet-16 and elite-eight schedule metadata."""

    sweet_16_time: datetime
    elite_8_time: datetime
    venue_city: str
    venue_state: str


@dataclass(frozen=True)
class TournamentRegionSpec:
    """One NCAA tournament region."""

    name: str
    round_of_64_games: tuple[TournamentRoundOf64GameSpec, ...]
    site: TournamentRegionSiteSpec


@dataclass(frozen=True)
class TournamentFinalFourSpec:
    """Final Four and title-game metadata."""

    semifinal_time: datetime
    championship_time: datetime
    venue_city: str
    venue_state: str
    pairings: tuple[tuple[str, str], tuple[str, str]]


@dataclass(frozen=True)
class TournamentBracketSpec:
    """Tracked local bracket input for one tournament field."""

    tournament_key: str
    label: str
    season: int
    play_in_games: tuple[TournamentPlayInGameSpec, ...]
    regions: tuple[TournamentRegionSpec, ...]
    final_four: TournamentFinalFourSpec


@dataclass(frozen=True)
class TournamentTeamInfo:
    """Stored team metadata needed to build synthetic game records."""

    team_id: int
    team_name: str
    team_key: str | None
    conference_key: str | None
    conference_name: str | None


@dataclass(frozen=True)
class TournamentEntrant:
    """Resolved tournament entrant with bracket seed and region."""

    team: TournamentTeamInfo
    seed: int
    region: str


@dataclass(frozen=True)
class MatchupEvaluation:
    """One scored straight-up matchup."""

    team_a_probability: float
    source: str
    scoring_source: str
    live_game_id: int | None
    scheduled_time: str


@dataclass(frozen=True)
class TournamentGamePick:
    """One deterministic bracket pick."""

    game_key: str
    round_label: str
    region: str | None
    scheduled_time: str
    home_team_name: str
    home_seed: int
    away_team_name: str
    away_seed: int
    winner_name: str
    winner_seed: int
    winner_probability: float
    source: str
    scoring_source: str
    live_game_id: int | None = None


@dataclass(frozen=True)
class TournamentTeamAdvancement:
    """Simulation-based advancement probabilities for one team."""

    team_name: str
    seed: int
    region: str
    round_of_64_probability: float
    round_of_32_probability: float
    sweet_16_probability: float
    elite_8_probability: float
    final_4_probability: float
    championship_probability: float
    title_probability: float


@dataclass(frozen=True)
class TournamentSummary:
    """Full tournament-mode bracket output."""

    tournament_key: str
    label: str
    season: int
    generated_at: datetime
    artifact_name: str
    bracket_picks: list[TournamentGamePick]
    team_advancement: list[TournamentTeamAdvancement]
    simulations: int


@dataclass(frozen=True)
class TournamentBacktestRoundSummary:
    """Round-level tournament-backtest accuracy summary."""

    round_label: str
    games: int
    correct_picks: int
    accuracy: float
    average_actual_winner_probability: float
    source_summaries: list[TournamentBacktestSourceSummary] = field(
        default_factory=list
    )


@dataclass(frozen=True)
class TournamentBacktestSourceSummary:
    """Source-level tournament-backtest accuracy summary."""

    source: str
    games: int
    correct_picks: int
    accuracy: float
    average_actual_winner_probability: float


@dataclass(frozen=True)
class TournamentBacktestPickSeedRoleSummary:
    """Pick seed-role tournament-backtest accuracy summary."""

    role: str
    games: int
    correct_picks: int
    accuracy: float
    average_actual_winner_probability: float


@dataclass(frozen=True)
class TournamentBacktestSeedGapSummary:
    """Exact seed-gap tournament-backtest accuracy summary."""

    seed_gap: int
    games: int
    correct_picks: int
    accuracy: float
    average_actual_winner_probability: float


@dataclass(frozen=True)
class TournamentBacktestSeasonSummary:
    """One season of completed tournament backtest results."""

    tournament_key: str
    label: str
    season: int
    training_seasons: tuple[int, ...]
    games: int
    correct_picks: int
    accuracy: float
    average_actual_winner_probability: float
    predicted_champion_name: str | None
    predicted_champion_seed: int | None
    predicted_champion_probability: float | None
    actual_champion_name: str | None
    actual_champion_seed: int | None
    champion_correct: bool
    final_four_teams_correct: int
    round_summaries: list[TournamentBacktestRoundSummary]
    source_summaries: list[TournamentBacktestSourceSummary]
    pick_seed_role_summaries: list[TournamentBacktestPickSeedRoleSummary] = field(
        default_factory=list
    )
    pick_seed_gap_summaries: list[TournamentBacktestSeedGapSummary] = field(
        default_factory=list
    )


@dataclass(frozen=True)
class TournamentBacktestSummary:
    """Aggregate prior-years tournament backtest output."""

    generated_at: datetime
    season_summaries: list[TournamentBacktestSeasonSummary]
    games: int
    correct_picks: int
    accuracy: float
    champion_hits: int
    average_actual_winner_probability: float
    round_summaries: list[TournamentBacktestRoundSummary]
    source_summaries: list[TournamentBacktestSourceSummary]
    pick_seed_role_summaries: list[TournamentBacktestPickSeedRoleSummary] = field(
        default_factory=list
    )
    pick_seed_gap_summaries: list[TournamentBacktestSeedGapSummary] = field(
        default_factory=list
    )


class TournamentBracketScorer(Protocol):
    """Minimal scorer interface used by bracket traversal helpers."""

    def entrant(self, *, team_name: str, seed: int, region: str) -> TournamentEntrant:
        """Resolve one named team into tournament entrant metadata."""

    def evaluate(
        self,
        *,
        team_a: TournamentEntrant,
        team_b: TournamentEntrant,
        scheduled_time: datetime,
        venue_city: str | None,
        venue_state: str | None,
    ) -> MatchupEvaluation:
        """Score or resolve one tournament matchup."""


def predict_tournament_bracket(options: TournamentOptions) -> TournamentSummary:
    """Build a tournament bracket plus advancement probabilities."""
    generated_at = options.now or datetime.now(UTC)
    bracket = load_tournament_bracket(options.bracket_path)
    if options.simulations <= 0:
        raise ValueError("simulations must be positive")

    available_seasons = get_available_seasons(options.database_url)
    if bracket.season not in available_seasons:
        raise ValueError(
            f"Tournament season {bracket.season} is not available in the database"
        )

    completed_records = load_completed_game_records(
        max_season=bracket.season,
        database_url=options.database_url,
    )
    live_records = [
        record
        for record in load_live_board_game_records(
            database_url=options.database_url,
            now=options.now,
        )
        if not record.completed
    ]
    teams_by_name = _build_team_lookup(
        completed_records=completed_records,
        live_records=live_records,
    )
    team_aliases_by_id = _load_team_aliases_from_database(
        database_url=options.database_url,
        teams_by_name=teams_by_name,
    )
    artifact = load_artifact(
        market="moneyline",
        artifact_name=options.artifact_name,
        artifacts_dir=options.artifacts_dir,
    )
    synthetic_training_seasons = _artifact_training_seasons(artifact)
    synthetic_training_records = [
        record
        for record in completed_records
        if (
            record.season in set(synthetic_training_seasons)
            and record.commence_time < generated_at
        )
    ]
    scorer = TournamentMatchupScorer(
        artifact=artifact,
        synthetic_artifact=_train_tournament_synthetic_artifact(
            game_records=synthetic_training_records,
            seasons=synthetic_training_seasons,
            config=LogisticRegressionConfig(),
        ),
        context=build_prediction_context(completed_records=completed_records),
        teams_by_name=teams_by_name,
        team_aliases_by_id=team_aliases_by_id,
        live_records=live_records,
        season=bracket.season,
    )

    deterministic_picks = build_deterministic_bracket(
        bracket=bracket,
        scorer=scorer,
    )
    advancement = simulate_tournament(
        bracket=bracket,
        scorer=scorer,
        simulations=options.simulations,
        random_seed=options.random_seed,
    )
    return TournamentSummary(
        tournament_key=bracket.tournament_key,
        label=bracket.label,
        season=bracket.season,
        generated_at=generated_at,
        artifact_name=options.artifact_name,
        bracket_picks=deterministic_picks,
        team_advancement=advancement,
        simulations=options.simulations,
    )


def backtest_tournament_model(
    options: TournamentBacktestOptions,
) -> TournamentBacktestSummary:
    """Backtest tournament bracket picks across completed prior seasons."""
    generated_at = options.now or datetime.now(UTC)
    if options.seasons <= 0:
        raise ValueError("seasons must be positive")
    if options.training_seasons_back <= 0:
        raise ValueError("training_seasons_back must be positive")

    brackets = load_tournament_brackets(options.bracket_dir)
    default_max_season = derive_cbb_season(generated_at) - 1
    selected_brackets = [
        bracket
        for bracket in brackets
        if bracket.season <= (options.max_season or default_max_season)
    ]
    if len(selected_brackets) < options.seasons:
        raise ValueError(
            "Not enough completed tournament specs are available for the requested "
            f"window: requested {options.seasons}, found {len(selected_brackets)}"
        )
    selected_brackets = selected_brackets[-options.seasons :]

    completed_records = load_completed_game_records(
        max_season=max(bracket.season for bracket in selected_brackets),
        database_url=options.database_url,
    )
    teams_by_name = _build_team_lookup(
        completed_records=completed_records,
        live_records=[],
    )
    team_aliases_by_id = _load_team_aliases_from_database(
        database_url=options.database_url,
        teams_by_name=teams_by_name,
    )

    season_summaries: list[TournamentBacktestSeasonSummary] = []
    for bracket in selected_brackets:
        anchor_time = _tournament_anchor_time(bracket)
        training_seasons = tuple(
            resolve_training_seasons(
                seasons_back=options.training_seasons_back,
                max_season=bracket.season,
                database_url=options.database_url,
            )
        )
        training_records = [
            record
            for record in completed_records
            if record.season in training_seasons and record.commence_time < anchor_time
        ]
        artifact = train_artifact_from_records(
            market="moneyline",
            game_records=training_records,
            seasons=training_seasons,
            config=options.config,
        )
        season_records = [
            record for record in completed_records if record.season == bracket.season
        ]
        known_initial_records = _load_known_tournament_records_at_anchor(
            bracket=bracket,
            season_records=season_records,
            teams_by_name=teams_by_name,
            team_aliases_by_id=team_aliases_by_id,
            anchor_time=anchor_time,
        )
        scorer = TournamentMatchupScorer(
            artifact=artifact,
            synthetic_artifact=_train_tournament_synthetic_artifact(
                game_records=training_records,
                seasons=training_seasons,
                config=options.config,
            ),
            context=build_prediction_context(completed_records=training_records),
            teams_by_name=teams_by_name,
            team_aliases_by_id=team_aliases_by_id,
            live_records=known_initial_records,
            season=bracket.season,
        )
        predicted_picks = build_deterministic_bracket(
            bracket=bracket,
            scorer=scorer,
        )
        actual_resolver = TournamentActualResultResolver(
            completed_records=season_records,
            teams_by_name=teams_by_name,
            team_aliases_by_id=team_aliases_by_id,
            bracket=bracket,
        )
        actual_picks = build_deterministic_bracket(
            bracket=bracket,
            scorer=actual_resolver,
        )
        season_summaries.append(
            summarize_tournament_backtest_season(
                bracket=bracket,
                training_seasons=training_seasons,
                predicted_picks=predicted_picks,
                actual_picks=actual_picks,
            )
        )
    return summarize_tournament_backtest(
        generated_at=generated_at,
        season_summaries=season_summaries,
    )


def load_tournament_bracket(path: Path) -> TournamentBracketSpec:
    """Load a tracked local tournament bracket specification."""
    payload = orjson.loads(path.read_bytes())
    play_in_games = tuple(
        TournamentPlayInGameSpec(
            game_key=str(item["game_key"]),
            region=str(item["region"]),
            seed=int(item["seed"]),
            scheduled_time=_parse_iso_datetime(item["scheduled_time"]),
            teams=_load_play_in_teams(item["teams"]),
            venue_city=_optional_str(item.get("venue_city")),
            venue_state=_optional_str(item.get("venue_state")),
        )
        for item in payload["play_in_games"]
    )
    regions = tuple(
        TournamentRegionSpec(
            name=str(region_payload["name"]),
            round_of_64_games=tuple(
                TournamentRoundOf64GameSpec(
                    game_key=str(game_payload["game_key"]),
                    scheduled_time=_parse_iso_datetime(
                        game_payload["scheduled_time"]
                    ),
                    home=_load_participant_spec(game_payload["home"]),
                    away=_load_participant_spec(game_payload["away"]),
                    venue_city=_optional_str(game_payload.get("venue_city")),
                    venue_state=_optional_str(game_payload.get("venue_state")),
                    actual_winner_team_name=_optional_str(
                        game_payload.get("actual_winner")
                    ),
                )
                for game_payload in region_payload["round_of_64_games"]
            ),
            site=TournamentRegionSiteSpec(
                sweet_16_time=_parse_iso_datetime(region_payload["site"]["sweet_16"]),
                elite_8_time=_parse_iso_datetime(region_payload["site"]["elite_8"]),
                venue_city=str(region_payload["site"]["venue_city"]),
                venue_state=str(region_payload["site"]["venue_state"]),
            ),
        )
        for region_payload in payload["regions"]
    )
    return TournamentBracketSpec(
        tournament_key=str(payload["tournament_key"]),
        label=str(payload["label"]),
        season=int(payload["season"]),
        play_in_games=play_in_games,
        regions=regions,
        final_four=TournamentFinalFourSpec(
            semifinal_time=_parse_iso_datetime(
                payload["final_four"]["semifinal_time"]
            ),
            championship_time=_parse_iso_datetime(
                payload["final_four"]["championship_time"]
            ),
            venue_city=str(payload["final_four"]["venue_city"]),
            venue_state=str(payload["final_four"]["venue_state"]),
            pairings=_load_final_four_pairings(payload["final_four"]["pairings"]),
        ),
    )


def load_tournament_brackets(directory: Path) -> list[TournamentBracketSpec]:
    """Load all tracked tournament bracket specifications from one directory."""
    if not directory.exists():
        raise FileNotFoundError(
            f"Tournament bracket directory does not exist: {directory}"
        )
    bracket_paths = sorted(directory.glob("*.json"))
    if not bracket_paths:
        raise ValueError(f"No tournament bracket specs found in {directory}")
    return sorted(
        (load_tournament_bracket(path) for path in bracket_paths),
        key=lambda bracket: bracket.season,
    )


def _load_play_in_teams(value: object) -> tuple[str, str]:
    """Validate and normalize one First Four matchup payload."""
    if not isinstance(value, (list, tuple)):
        raise ValueError("play_in_games[].teams must be an array")
    teams = tuple(str(team_name) for team_name in value)
    if len(teams) != 2:
        raise ValueError("play_in_games[].teams must contain exactly two teams")
    return (teams[0], teams[1])


def _load_final_four_pairings(value: object) -> tuple[tuple[str, str], tuple[str, str]]:
    """Validate and normalize the two Final Four semifinal pairings."""
    if not isinstance(value, (list, tuple)):
        raise ValueError("final_four.pairings must be an array")
    pairings = tuple(_load_region_pairing(item) for item in value)
    if len(pairings) != 2:
        raise ValueError("final_four.pairings must contain exactly two semifinals")
    return (pairings[0], pairings[1])


def _load_region_pairing(value: object) -> tuple[str, str]:
    """Validate and normalize one semifinal region pairing."""
    if not isinstance(value, (list, tuple)):
        raise ValueError("final_four.pairings[] must be an array")
    pairing = tuple(str(region_name) for region_name in value)
    if len(pairing) != 2:
        raise ValueError("final_four.pairings[] must contain exactly two regions")
    return (pairing[0], pairing[1])


def build_deterministic_bracket(
    *,
    bracket: TournamentBracketSpec,
    scorer: TournamentBracketScorer,
) -> list[TournamentGamePick]:
    """Return one deterministic bracket using the higher-probability side."""
    picks: list[TournamentGamePick] = []
    play_in_winners: dict[str, TournamentEntrant] = {}
    region_winners: dict[str, TournamentEntrant] = {}

    for play_in in bracket.play_in_games:
        winner, pick = _play_in_pick(
            play_in=play_in,
            scorer=scorer,
            pick_winner=True,
        )
        play_in_winners[play_in.game_key] = winner
        picks.append(pick)

    for region in bracket.regions:
        winner, region_picks = _deterministic_region_picks(
            region=region,
            play_in_winners=play_in_winners,
            scorer=scorer,
        )
        region_winners[region.name] = winner
        picks.extend(region_picks)

    semifinal_winners: list[TournamentEntrant] = []
    for index, pairing in enumerate(bracket.final_four.pairings, start=1):
        home = region_winners[pairing[0]]
        away = region_winners[pairing[1]]
        winner, pick = _evaluate_pick(
            game_key=f"final-four-{index}",
            round_label="Final Four",
            region=None,
            home=home,
            away=away,
            scheduled_time=bracket.final_four.semifinal_time,
            venue_city=bracket.final_four.venue_city,
            venue_state=bracket.final_four.venue_state,
            scorer=scorer,
            pick_winner=True,
        )
        semifinal_winners.append(winner)
        picks.append(pick)

    _, title_pick = _evaluate_pick(
        game_key="championship",
        round_label="Championship",
        region=None,
        home=semifinal_winners[0],
        away=semifinal_winners[1],
        scheduled_time=bracket.final_four.championship_time,
        venue_city=bracket.final_four.venue_city,
        venue_state=bracket.final_four.venue_state,
        scorer=scorer,
        pick_winner=True,
    )
    picks.append(title_pick)
    return picks


def summarize_tournament_backtest_season(
    *,
    bracket: TournamentBracketSpec,
    training_seasons: Sequence[int],
    predicted_picks: Sequence[TournamentGamePick],
    actual_picks: Sequence[TournamentGamePick],
) -> TournamentBacktestSeasonSummary:
    """Summarize one completed tournament season against actual outcomes."""
    if len(predicted_picks) != len(actual_picks):
        raise ValueError("Predicted and actual tournament pick counts do not match")

    predicted_by_key = {pick.game_key: pick for pick in predicted_picks}
    actual_by_key = {pick.game_key: pick for pick in actual_picks}
    if predicted_by_key.keys() != actual_by_key.keys():
        raise ValueError("Predicted and actual tournament game keys do not match")

    correct_picks = 0
    total_actual_winner_probability = 0.0
    round_totals: dict[str, int] = defaultdict(int)
    round_correct: dict[str, int] = defaultdict(int)
    round_actual_winner_probability: dict[str, float] = defaultdict(float)
    round_source_totals: dict[str, dict[str, int]] = defaultdict(dict)
    round_source_correct: dict[str, dict[str, int]] = defaultdict(dict)
    round_source_actual_winner_probability: dict[str, dict[str, float]] = defaultdict(
        dict
    )
    round_source_order: dict[str, list[str]] = defaultdict(list)
    source_totals: dict[str, int] = defaultdict(int)
    source_correct: dict[str, int] = defaultdict(int)
    source_actual_winner_probability: dict[str, float] = defaultdict(float)
    source_order: list[str] = []
    pick_seed_role_totals: dict[str, int] = defaultdict(int)
    pick_seed_role_correct: dict[str, int] = defaultdict(int)
    pick_seed_role_actual_winner_probability: dict[str, float] = defaultdict(float)
    pick_seed_gap_totals: dict[int, int] = defaultdict(int)
    pick_seed_gap_correct: dict[int, int] = defaultdict(int)
    pick_seed_gap_actual_winner_probability: dict[int, float] = defaultdict(float)

    for game_key in [pick.game_key for pick in predicted_picks]:
        predicted = predicted_by_key[game_key]
        actual = actual_by_key[game_key]
        is_correct = predicted.winner_name == actual.winner_name
        pick_seed_role = _tournament_pick_seed_role(predicted)
        pick_seed_gap = abs(predicted.home_seed - predicted.away_seed)
        actual_winner_probability = (
            predicted.winner_probability
            if is_correct
            else 1.0 - predicted.winner_probability
        )
        if is_correct:
            correct_picks += 1
        total_actual_winner_probability += actual_winner_probability
        round_totals[predicted.round_label] += 1
        round_correct[predicted.round_label] += int(is_correct)
        round_actual_winner_probability[predicted.round_label] += (
            actual_winner_probability
        )
        round_source_totals[predicted.round_label][predicted.scoring_source] = (
            round_source_totals[predicted.round_label].get(predicted.scoring_source, 0)
            + 1
        )
        round_source_correct[predicted.round_label][predicted.scoring_source] = (
            round_source_correct[predicted.round_label].get(
                predicted.scoring_source, 0
            )
            + int(is_correct)
        )
        round_source_actual_winner_probability[predicted.round_label][
            predicted.scoring_source
        ] = (
            round_source_actual_winner_probability[predicted.round_label].get(
                predicted.scoring_source, 0.0
            )
            + actual_winner_probability
        )
        if predicted.scoring_source not in round_source_order[predicted.round_label]:
            round_source_order[predicted.round_label].append(predicted.scoring_source)
        if predicted.scoring_source not in source_order:
            source_order.append(predicted.scoring_source)
        source_totals[predicted.scoring_source] += 1
        source_correct[predicted.scoring_source] += int(is_correct)
        source_actual_winner_probability[predicted.scoring_source] += (
            actual_winner_probability
        )
        pick_seed_role_totals[pick_seed_role] += 1
        pick_seed_role_correct[pick_seed_role] += int(is_correct)
        pick_seed_role_actual_winner_probability[pick_seed_role] += (
            actual_winner_probability
        )
        pick_seed_gap_totals[pick_seed_gap] += 1
        pick_seed_gap_correct[pick_seed_gap] += int(is_correct)
        pick_seed_gap_actual_winner_probability[pick_seed_gap] += (
            actual_winner_probability
        )

    predicted_champion = _tournament_champion_pick_from_picks(predicted_picks)
    actual_champion = _tournament_champion_pick_from_picks(actual_picks)
    predicted_final_four = _tournament_final_four_teams(predicted_picks)
    actual_final_four = _tournament_final_four_teams(actual_picks)
    games = len(predicted_picks)

    return TournamentBacktestSeasonSummary(
        tournament_key=bracket.tournament_key,
        label=bracket.label,
        season=bracket.season,
        training_seasons=tuple(training_seasons),
        games=games,
        correct_picks=correct_picks,
        accuracy=(correct_picks / games) if games > 0 else 0.0,
        average_actual_winner_probability=(
            total_actual_winner_probability / games if games > 0 else 0.0
        ),
        predicted_champion_name=(
            predicted_champion.winner_name if predicted_champion is not None else None
        ),
        predicted_champion_seed=(
            predicted_champion.winner_seed if predicted_champion is not None else None
        ),
        predicted_champion_probability=(
            predicted_champion.winner_probability
            if predicted_champion is not None
            else None
        ),
        actual_champion_name=(
            actual_champion.winner_name if actual_champion is not None else None
        ),
        actual_champion_seed=(
            actual_champion.winner_seed if actual_champion is not None else None
        ),
        champion_correct=(
            predicted_champion is not None
            and actual_champion is not None
            and predicted_champion.winner_name == actual_champion.winner_name
        ),
        final_four_teams_correct=len(predicted_final_four & actual_final_four),
        round_summaries=[
            TournamentBacktestRoundSummary(
                round_label=round_label,
                games=round_totals[round_label],
                correct_picks=round_correct[round_label],
                accuracy=(
                    round_correct[round_label] / round_totals[round_label]
                    if round_totals[round_label] > 0
                    else 0.0
                ),
                average_actual_winner_probability=(
                    round_actual_winner_probability[round_label]
                    / round_totals[round_label]
                    if round_totals[round_label] > 0
                    else 0.0
                ),
                source_summaries=_build_tournament_source_summaries(
                    source_order=round_source_order[round_label],
                    source_totals=round_source_totals[round_label],
                    source_correct=round_source_correct[round_label],
                    source_actual_winner_probability=(
                        round_source_actual_winner_probability[round_label]
                    ),
                ),
            )
            for round_label in _round_label_order(predicted_picks)
        ],
        source_summaries=_build_tournament_source_summaries(
            source_order=source_order,
            source_totals=source_totals,
            source_correct=source_correct,
            source_actual_winner_probability=source_actual_winner_probability,
        ),
        pick_seed_role_summaries=_build_tournament_pick_seed_role_summaries(
            pick_seed_role_totals=pick_seed_role_totals,
            pick_seed_role_correct=pick_seed_role_correct,
            pick_seed_role_actual_winner_probability=(
                pick_seed_role_actual_winner_probability
            ),
        ),
        pick_seed_gap_summaries=_build_tournament_pick_seed_gap_summaries(
            pick_seed_gap_totals=pick_seed_gap_totals,
            pick_seed_gap_correct=pick_seed_gap_correct,
            pick_seed_gap_actual_winner_probability=(
                pick_seed_gap_actual_winner_probability
            ),
        ),
    )


def summarize_tournament_backtest(
    *,
    generated_at: datetime,
    season_summaries: Sequence[TournamentBacktestSeasonSummary],
) -> TournamentBacktestSummary:
    """Aggregate tournament-backtest results across many seasons."""
    if not season_summaries:
        raise ValueError("At least one season summary is required")

    games = sum(summary.games for summary in season_summaries)
    correct_picks = sum(summary.correct_picks for summary in season_summaries)
    champion_hits = sum(int(summary.champion_correct) for summary in season_summaries)
    total_actual_winner_probability = sum(
        summary.average_actual_winner_probability * summary.games
        for summary in season_summaries
    )
    round_totals: dict[str, int] = defaultdict(int)
    round_correct: dict[str, int] = defaultdict(int)
    round_actual_winner_probability: dict[str, float] = defaultdict(float)
    round_order: list[str] = []
    round_source_totals: dict[str, dict[str, int]] = defaultdict(dict)
    round_source_correct: dict[str, dict[str, int]] = defaultdict(dict)
    round_source_actual_winner_probability: dict[str, dict[str, float]] = defaultdict(
        dict
    )
    round_source_order: dict[str, list[str]] = defaultdict(list)
    source_totals: dict[str, int] = defaultdict(int)
    source_correct: dict[str, int] = defaultdict(int)
    source_actual_winner_probability: dict[str, float] = defaultdict(float)
    source_order: list[str] = []
    pick_seed_role_totals: dict[str, int] = defaultdict(int)
    pick_seed_role_correct: dict[str, int] = defaultdict(int)
    pick_seed_role_actual_winner_probability: dict[str, float] = defaultdict(float)
    pick_seed_gap_totals: dict[int, int] = defaultdict(int)
    pick_seed_gap_correct: dict[int, int] = defaultdict(int)
    pick_seed_gap_actual_winner_probability: dict[int, float] = defaultdict(float)
    for season_summary in season_summaries:
        for round_summary in season_summary.round_summaries:
            if round_summary.round_label not in round_order:
                round_order.append(round_summary.round_label)
            round_totals[round_summary.round_label] += round_summary.games
            round_correct[round_summary.round_label] += round_summary.correct_picks
            round_actual_winner_probability[round_summary.round_label] += (
                round_summary.average_actual_winner_probability * round_summary.games
            )
            for source_summary in round_summary.source_summaries:
                round_totals_by_source = round_source_totals[
                    round_summary.round_label
                ]
                round_totals_by_source[source_summary.source] = (
                    round_totals_by_source.get(source_summary.source, 0)
                    + source_summary.games
                )
                round_source_correct[
                    round_summary.round_label
                ][source_summary.source] = (
                    round_source_correct[round_summary.round_label].get(
                        source_summary.source, 0
                    )
                    + source_summary.correct_picks
                )
                round_source_actual_winner_probability[
                    round_summary.round_label
                ][source_summary.source] = (
                    round_source_actual_winner_probability[
                        round_summary.round_label
                    ].get(source_summary.source, 0.0)
                    + (
                        source_summary.average_actual_winner_probability
                        * source_summary.games
                    )
                )
                if (
                    source_summary.source
                    not in round_source_order[round_summary.round_label]
                ):
                    round_source_order[round_summary.round_label].append(
                        source_summary.source
                    )
        for source_summary in season_summary.source_summaries:
            if source_summary.source not in source_order:
                source_order.append(source_summary.source)
            source_totals[source_summary.source] += source_summary.games
            source_correct[source_summary.source] += source_summary.correct_picks
            source_actual_winner_probability[source_summary.source] += (
                source_summary.average_actual_winner_probability
                * source_summary.games
            )
        for pick_seed_role_summary in season_summary.pick_seed_role_summaries:
            pick_seed_role_totals[pick_seed_role_summary.role] += (
                pick_seed_role_summary.games
            )
            pick_seed_role_correct[pick_seed_role_summary.role] += (
                pick_seed_role_summary.correct_picks
            )
            pick_seed_role_actual_winner_probability[
                pick_seed_role_summary.role
            ] += (
                pick_seed_role_summary.average_actual_winner_probability
                * pick_seed_role_summary.games
            )
        for pick_seed_gap_summary in season_summary.pick_seed_gap_summaries:
            pick_seed_gap_totals[pick_seed_gap_summary.seed_gap] += (
                pick_seed_gap_summary.games
            )
            pick_seed_gap_correct[pick_seed_gap_summary.seed_gap] += (
                pick_seed_gap_summary.correct_picks
            )
            pick_seed_gap_actual_winner_probability[
                pick_seed_gap_summary.seed_gap
            ] += (
                pick_seed_gap_summary.average_actual_winner_probability
                * pick_seed_gap_summary.games
            )

    return TournamentBacktestSummary(
        generated_at=generated_at,
        season_summaries=list(season_summaries),
        games=games,
        correct_picks=correct_picks,
        accuracy=(correct_picks / games) if games > 0 else 0.0,
        champion_hits=champion_hits,
        average_actual_winner_probability=(
            total_actual_winner_probability / games if games > 0 else 0.0
        ),
        round_summaries=[
            TournamentBacktestRoundSummary(
                round_label=round_label,
                games=round_totals[round_label],
                correct_picks=round_correct[round_label],
                accuracy=(
                    round_correct[round_label] / round_totals[round_label]
                    if round_totals[round_label] > 0
                    else 0.0
                ),
                average_actual_winner_probability=(
                    round_actual_winner_probability[round_label]
                    / round_totals[round_label]
                    if round_totals[round_label] > 0
                    else 0.0
                ),
                source_summaries=_build_tournament_source_summaries(
                    source_order=round_source_order[round_label],
                    source_totals=round_source_totals[round_label],
                    source_correct=round_source_correct[round_label],
                    source_actual_winner_probability=(
                        round_source_actual_winner_probability[round_label]
                    ),
                ),
            )
            for round_label in round_order
        ],
        source_summaries=_build_tournament_source_summaries(
            source_order=source_order,
            source_totals=source_totals,
            source_correct=source_correct,
            source_actual_winner_probability=source_actual_winner_probability,
        ),
        pick_seed_role_summaries=_build_tournament_pick_seed_role_summaries(
            pick_seed_role_totals=pick_seed_role_totals,
            pick_seed_role_correct=pick_seed_role_correct,
            pick_seed_role_actual_winner_probability=(
                pick_seed_role_actual_winner_probability
            ),
        ),
        pick_seed_gap_summaries=_build_tournament_pick_seed_gap_summaries(
            pick_seed_gap_totals=pick_seed_gap_totals,
            pick_seed_gap_correct=pick_seed_gap_correct,
            pick_seed_gap_actual_winner_probability=(
                pick_seed_gap_actual_winner_probability
            ),
        ),
    )


def _build_tournament_source_summaries(
    *,
    source_order: Sequence[str],
    source_totals: dict[str, int],
    source_correct: dict[str, int],
    source_actual_winner_probability: dict[str, float],
) -> list[TournamentBacktestSourceSummary]:
    """Build deterministic source-level tournament-backtest summaries."""
    return [
        TournamentBacktestSourceSummary(
            source=source,
            games=source_totals[source],
            correct_picks=source_correct[source],
            accuracy=(
                source_correct[source] / source_totals[source]
                if source_totals[source] > 0
                else 0.0
            ),
            average_actual_winner_probability=(
                source_actual_winner_probability[source] / source_totals[source]
                if source_totals[source] > 0
                else 0.0
            ),
        )
        for source in source_order
    ]


def _build_tournament_pick_seed_role_summaries(
    *,
    pick_seed_role_totals: dict[str, int],
    pick_seed_role_correct: dict[str, int],
    pick_seed_role_actual_winner_probability: dict[str, float],
) -> list[TournamentBacktestPickSeedRoleSummary]:
    """Build deterministic pick seed-role tournament-backtest summaries."""
    return [
        TournamentBacktestPickSeedRoleSummary(
            role=role,
            games=pick_seed_role_totals[role],
            correct_picks=pick_seed_role_correct[role],
            accuracy=(
                pick_seed_role_correct[role] / pick_seed_role_totals[role]
                if pick_seed_role_totals[role] > 0
                else 0.0
            ),
            average_actual_winner_probability=(
                pick_seed_role_actual_winner_probability[role]
                / pick_seed_role_totals[role]
                if pick_seed_role_totals[role] > 0
                else 0.0
            ),
        )
        for role in TOURNAMENT_PICK_SEED_ROLE_ORDER
        if pick_seed_role_totals.get(role, 0) > 0
    ]


def _build_tournament_pick_seed_gap_summaries(
    *,
    pick_seed_gap_totals: dict[int, int],
    pick_seed_gap_correct: dict[int, int],
    pick_seed_gap_actual_winner_probability: dict[int, float],
) -> list[TournamentBacktestSeedGapSummary]:
    """Build deterministic exact-seed-gap tournament-backtest summaries."""
    return [
        TournamentBacktestSeedGapSummary(
            seed_gap=seed_gap,
            games=pick_seed_gap_totals[seed_gap],
            correct_picks=pick_seed_gap_correct[seed_gap],
            accuracy=(
                pick_seed_gap_correct[seed_gap] / pick_seed_gap_totals[seed_gap]
                if pick_seed_gap_totals[seed_gap] > 0
                else 0.0
            ),
            average_actual_winner_probability=(
                pick_seed_gap_actual_winner_probability[seed_gap]
                / pick_seed_gap_totals[seed_gap]
                if pick_seed_gap_totals[seed_gap] > 0
                else 0.0
            ),
        )
        for seed_gap in sorted(pick_seed_gap_totals)
    ]


def _tournament_pick_seed_role(pick: TournamentGamePick) -> str:
    """Classify one predicted pick as a favorite, upset, or same-seed result."""
    loser_seed = (
        pick.away_seed if pick.winner_name == pick.home_team_name else pick.home_seed
    )
    if pick.winner_seed < loser_seed:
        return FAVORITE_PICK_SEED_ROLE
    if pick.winner_seed > loser_seed:
        return UPSET_PICK_SEED_ROLE
    return SAME_SEED_PICK_ROLE


def simulate_tournament(
    *,
    bracket: TournamentBracketSpec,
    scorer: TournamentBracketScorer,
    simulations: int,
    random_seed: int,
) -> list[TournamentTeamAdvancement]:
    """Run Monte Carlo tournament simulations using cached matchup probabilities."""
    rng = Random(random_seed)
    counts: dict[str, dict[str, int]] = defaultdict(
        lambda: defaultdict(int)
    )
    entrants = _all_entrants(bracket=bracket, scorer=scorer)

    for _ in range(simulations):
        play_in_winners: dict[str, TournamentEntrant] = {}

        for entrant in entrants.values():
            if entrant.region and entrant.seed > 0:
                counts[entrant.team.team_name]["field"] += 1

        for play_in in bracket.play_in_games:
            winner, _ = _play_in_pick(
                play_in=play_in,
                scorer=scorer,
                pick_winner=False,
                rng=rng,
            )
            play_in_winners[play_in.game_key] = winner
            counts[winner.team.team_name]["round_of_64"] += 1

        for entrant in entrants.values():
            if not _team_requires_play_in(bracket=bracket, entrant=entrant):
                counts[entrant.team.team_name]["round_of_64"] += 1

        region_winners: dict[str, TournamentEntrant] = {}
        for region in bracket.regions:
            winner = _simulate_region(
                region=region,
                play_in_winners=play_in_winners,
                scorer=scorer,
                rng=rng,
                counts=counts,
            )
            region_winners[region.name] = winner
            counts[winner.team.team_name]["final_4"] += 1

        semifinal_winners: list[TournamentEntrant] = []
        for pairing in bracket.final_four.pairings:
            winner = _sample_winner(
                home=region_winners[pairing[0]],
                away=region_winners[pairing[1]],
                scheduled_time=bracket.final_four.semifinal_time,
                venue_city=bracket.final_four.venue_city,
                venue_state=bracket.final_four.venue_state,
                scorer=scorer,
                rng=rng,
            )
            semifinal_winners.append(winner)
            counts[winner.team.team_name]["championship"] += 1

        champion = _sample_winner(
            home=semifinal_winners[0],
            away=semifinal_winners[1],
            scheduled_time=bracket.final_four.championship_time,
            venue_city=bracket.final_four.venue_city,
            venue_state=bracket.final_four.venue_state,
            scorer=scorer,
            rng=rng,
        )
        counts[champion.team.team_name]["title"] += 1

    advancement: list[TournamentTeamAdvancement] = []
    for entrant in sorted(
        entrants.values(),
        key=lambda item: (item.region, item.seed, item.team.team_name),
    ):
        team_counts = counts[entrant.team.team_name]
        advancement.append(
            TournamentTeamAdvancement(
                team_name=entrant.team.team_name,
                seed=entrant.seed,
                region=entrant.region,
                round_of_64_probability=team_counts["round_of_64"] / simulations,
                round_of_32_probability=team_counts["round_of_32"] / simulations,
                sweet_16_probability=team_counts["sweet_16"] / simulations,
                elite_8_probability=team_counts["elite_8"] / simulations,
                final_4_probability=team_counts["final_4"] / simulations,
                championship_probability=team_counts["championship"] / simulations,
                title_probability=team_counts["title"] / simulations,
            )
        )
    advancement.sort(
        key=lambda item: (-item.title_probability, item.seed, item.team_name)
    )
    return advancement


class TournamentMatchupScorer:
    """Cache-aware matchup scorer for tournament bracket use."""

    def __init__(
        self,
        *,
        artifact: ModelArtifact,
        synthetic_artifact: ModelArtifact | None,
        context: PredictionFeatureContext,
        teams_by_name: dict[str, TournamentTeamInfo],
        team_aliases_by_id: dict[int, frozenset[str]],
        live_records: list[GameOddsRecord],
        season: int,
    ) -> None:
        self.artifact = artifact
        self.synthetic_artifact = synthetic_artifact
        self.context = context
        self.teams_by_name = teams_by_name
        self.season = season
        self.team_aliases_by_id = team_aliases_by_id
        self.live_records_by_pair = _records_by_team_pair(live_records)
        self._evaluation_cache: dict[
            tuple[int, int, str, str | None], MatchupEvaluation
        ] = {}
        self._synthetic_game_id = -1

    def entrant(self, *, team_name: str, seed: int, region: str) -> TournamentEntrant:
        """Resolve one bracket team name to stored team metadata."""
        team = _resolve_team_info(
            team_name=team_name,
            teams_by_name=self.teams_by_name,
            team_aliases_by_id=self.team_aliases_by_id,
        )
        return TournamentEntrant(team=team, seed=seed, region=region)

    def evaluate(
        self,
        *,
        team_a: TournamentEntrant,
        team_b: TournamentEntrant,
        scheduled_time: datetime,
        venue_city: str | None,
        venue_state: str | None,
    ) -> MatchupEvaluation:
        """Score one neutral-site straight-up matchup."""
        live_record = self._match_live_record(
            team_a_id=team_a.team.team_id,
            team_b_id=team_b.team.team_id,
            scheduled_time=scheduled_time,
        )
        cache_key = (
            team_a.team.team_id,
            team_b.team.team_id,
            scheduled_time.isoformat(),
            str(live_record.game_id) if live_record is not None else None,
        )
        cached = self._evaluation_cache.get(cache_key)
        if cached is not None:
            return cached

        home_record = self._record_for_orientation(
            home=team_a,
            away=team_b,
            scheduled_time=scheduled_time,
            venue_city=venue_city,
            venue_state=venue_state,
            live_record=live_record,
        )
        away_record = self._record_for_orientation(
            home=team_b,
            away=team_a,
            scheduled_time=scheduled_time,
            venue_city=venue_city,
            venue_state=venue_state,
            live_record=live_record,
        )
        home_probability, home_scoring_source = self._side_probability(
            record=home_record,
            team_name=team_a.team.team_name,
        )
        away_probability, away_scoring_source = self._side_probability(
            record=away_record,
            team_name=team_a.team.team_name,
        )
        if home_scoring_source != away_scoring_source:
            raise RuntimeError("Expected tournament scoring source to stay aligned")
        evaluation = MatchupEvaluation(
            team_a_probability=(home_probability + away_probability) / 2.0,
            source=(
                LIVE_MATCHUP_SOURCE
                if live_record is not None
                else SYNTHETIC_MATCHUP_SOURCE
            ),
            scoring_source=home_scoring_source,
            live_game_id=live_record.game_id if live_record is not None else None,
            scheduled_time=(
                live_record.commence_time.isoformat()
                if live_record is not None
                else scheduled_time.isoformat()
            ),
        )
        self._evaluation_cache[cache_key] = evaluation
        return evaluation

    def _match_live_record(
        self,
        *,
        team_a_id: int,
        team_b_id: int,
        scheduled_time: datetime,
    ) -> GameOddsRecord | None:
        return _match_record_for_pair(
            records_by_pair=self.live_records_by_pair,
            team_a_id=team_a_id,
            team_b_id=team_b_id,
            scheduled_time=scheduled_time,
        )

    def _side_probability(
        self,
        *,
        record: GameOddsRecord,
        team_name: str,
    ) -> tuple[float, str]:
        examples = build_prediction_examples_from_context(
            context=self.context,
            upcoming_records=[record],
            market="moneyline",
        )
        scoring_artifact = _tournament_scoring_artifact_for_record(
            record=record,
            artifact=self.artifact,
            synthetic_artifact=self.synthetic_artifact,
        )
        probabilities = score_examples(
            artifact=scoring_artifact,
            examples=examples,
        )
        if len(examples) != 2 or len(probabilities) != 2:
            raise RuntimeError("Expected exactly two moneyline examples per matchup")
        probability_by_team = {
            example.team_name: probability
            for example, probability in zip(examples, probabilities, strict=True)
        }
        team_probability = probability_by_team[team_name]
        opponent_probability = sum(probabilities) - team_probability
        total = team_probability + opponent_probability
        if total <= 0.0:
            normalized_probability = 0.5
        else:
            normalized_probability = team_probability / total
        return normalized_probability, (
            LIVE_MARKET_ARTIFACT_SOURCE
            if scoring_artifact is self.artifact
            else SYNTHETIC_FALLBACK_ARTIFACT_SOURCE
        )

    def _record_for_orientation(
        self,
        *,
        home: TournamentEntrant,
        away: TournamentEntrant,
        scheduled_time: datetime,
        venue_city: str | None,
        venue_state: str | None,
        live_record: GameOddsRecord | None,
        ) -> GameOddsRecord:
        if live_record is None:
            return self._synthetic_record(
                home=home,
                away=away,
                scheduled_time=scheduled_time,
                venue_city=venue_city,
                venue_state=venue_state,
            )
        if (
            live_record.home_team_id == home.team.team_id
            and live_record.away_team_id == away.team.team_id
        ):
            return replace(
                live_record,
                neutral_site=True,
                venue_city=venue_city or live_record.venue_city,
                venue_state=venue_state or live_record.venue_state,
            )
        if (
            live_record.home_team_id == away.team.team_id
            and live_record.away_team_id == home.team.team_id
        ):
            return replace(
                _swap_game_record(live_record),
                neutral_site=True,
                venue_city=venue_city or live_record.venue_city,
                venue_state=venue_state or live_record.venue_state,
            )
        raise ValueError(
            "Live matchup record does not match the requested tournament entrants"
        )

    def _synthetic_record(
        self,
        *,
        home: TournamentEntrant,
        away: TournamentEntrant,
        scheduled_time: datetime,
        venue_city: str | None,
        venue_state: str | None,
    ) -> GameOddsRecord:
        synthetic_game_id = self._synthetic_game_id
        self._synthetic_game_id -= 1
        return GameOddsRecord(
            game_id=synthetic_game_id,
            season=self.season,
            game_date=scheduled_time.date().isoformat(),
            commence_time=scheduled_time,
            completed=False,
            home_score=None,
            away_score=None,
            home_team_id=home.team.team_id,
            home_team_name=home.team.team_name,
            away_team_id=away.team.team_id,
            away_team_name=away.team.team_name,
            home_h2h_price=None,
            away_h2h_price=None,
            home_spread_line=None,
            away_spread_line=None,
            home_spread_price=None,
            away_spread_price=None,
            total_points=None,
            h2h_open=None,
            h2h_close=None,
            spread_open=None,
            spread_close=None,
            total_open=None,
            total_close=None,
            home_conference_key=home.team.conference_key,
            home_conference_name=home.team.conference_name,
            away_conference_key=away.team.conference_key,
            away_conference_name=away.team.conference_name,
            observation_time=scheduled_time,
            snapshots=(),
            current_h2h_quotes=(),
            current_spread_quotes=(),
            home_team_key=home.team.team_key,
            away_team_key=away.team.team_key,
            neutral_site=True,
            venue_name=None,
            venue_city=venue_city,
            venue_state=venue_state,
            last_score_update=None,
        )


class TournamentActualResultResolver:
    """Actual-result resolver used to replay completed tournament brackets."""

    def __init__(
        self,
        *,
        completed_records: list[GameOddsRecord],
        teams_by_name: dict[str, TournamentTeamInfo],
        team_aliases_by_id: dict[int, frozenset[str]],
        bracket: TournamentBracketSpec,
    ) -> None:
        self.completed_records_by_pair = _records_by_team_pair(completed_records)
        self.teams_by_name = teams_by_name
        self.team_aliases_by_id = team_aliases_by_id
        self.actual_result_overrides = _build_actual_result_overrides(
            bracket=bracket,
            teams_by_name=teams_by_name,
            team_aliases_by_id=team_aliases_by_id,
        )

    def entrant(self, *, team_name: str, seed: int, region: str) -> TournamentEntrant:
        team = _resolve_team_info(
            team_name=team_name,
            teams_by_name=self.teams_by_name,
            team_aliases_by_id=self.team_aliases_by_id,
        )
        return TournamentEntrant(team=team, seed=seed, region=region)

    def evaluate(
        self,
        *,
        team_a: TournamentEntrant,
        team_b: TournamentEntrant,
        scheduled_time: datetime,
        venue_city: str | None,
        venue_state: str | None,
    ) -> MatchupEvaluation:
        del venue_city, venue_state
        record = _match_record_for_pair(
            records_by_pair=self.completed_records_by_pair,
            team_a_id=team_a.team.team_id,
            team_b_id=team_b.team.team_id,
            scheduled_time=scheduled_time,
        )
        if record is None:
            override_winner_team_id = self.actual_result_overrides.get(
                _actual_result_override_key(
                    team_a_id=team_a.team.team_id,
                    team_b_id=team_b.team.team_id,
                    scheduled_time=scheduled_time,
                )
            )
            if override_winner_team_id is None:
                raise ValueError(
                    "Could not resolve actual tournament result for "
                    f"{team_a.team.team_name} vs {team_b.team.team_name}"
                )
            return MatchupEvaluation(
                team_a_probability=(
                    1.0 if override_winner_team_id == team_a.team.team_id else 0.0
                ),
                source=ACTUAL_MATCHUP_SOURCE,
                scoring_source=ACTUAL_MATCHUP_SOURCE,
                live_game_id=None,
                scheduled_time=scheduled_time.isoformat(),
            )
        if record.home_score is None or record.away_score is None:
            raise ValueError(
                "Completed tournament backtest requires final scores for every game"
            )
        team_a_won = (
            record.home_score > record.away_score
            if record.home_team_id == team_a.team.team_id
            else record.away_score > record.home_score
        )
        return MatchupEvaluation(
            team_a_probability=1.0 if team_a_won else 0.0,
            source=ACTUAL_MATCHUP_SOURCE,
            scoring_source=ACTUAL_MATCHUP_SOURCE,
            live_game_id=record.game_id,
            scheduled_time=record.commence_time.isoformat(),
        )


def _build_actual_result_overrides(
    *,
    bracket: TournamentBracketSpec,
    teams_by_name: dict[str, TournamentTeamInfo],
    team_aliases_by_id: dict[int, frozenset[str]],
) -> dict[tuple[frozenset[int], str], int]:
    overrides: dict[tuple[frozenset[int], str], int] = {}
    for region in bracket.regions:
        for game in region.round_of_64_games:
            if (
                game.actual_winner_team_name is None
                or game.home.team_name is None
                or game.away.team_name is None
            ):
                continue
            home = _resolve_team_info(
                team_name=game.home.team_name,
                teams_by_name=teams_by_name,
                team_aliases_by_id=team_aliases_by_id,
            )
            away = _resolve_team_info(
                team_name=game.away.team_name,
                teams_by_name=teams_by_name,
                team_aliases_by_id=team_aliases_by_id,
            )
            winner = _resolve_team_info(
                team_name=game.actual_winner_team_name,
                teams_by_name=teams_by_name,
                team_aliases_by_id=team_aliases_by_id,
            )
            overrides[
                _actual_result_override_key(
                    team_a_id=home.team_id,
                    team_b_id=away.team_id,
                    scheduled_time=game.scheduled_time,
                )
            ] = winner.team_id
    return overrides


def _actual_result_override_key(
    *,
    team_a_id: int,
    team_b_id: int,
    scheduled_time: datetime,
) -> tuple[frozenset[int], str]:
    return (frozenset((team_a_id, team_b_id)), scheduled_time.isoformat())


def _load_participant_spec(payload: object) -> TournamentParticipantSpec:
    if not isinstance(payload, dict):
        raise TypeError("Bracket participant payload must be an object")
    return TournamentParticipantSpec(
        seed=int(payload["seed"]),
        team_name=_optional_str(payload.get("team")),
        play_in_game_key=_optional_str(payload.get("play_in_game")),
    )


def _parse_iso_datetime(value: object) -> datetime:
    if not isinstance(value, str):
        raise TypeError("Expected ISO datetime string in tournament spec")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _play_in_pick(
    *,
    play_in: TournamentPlayInGameSpec,
    scorer: TournamentBracketScorer,
    pick_winner: bool,
    rng: Random | None = None,
) -> tuple[TournamentEntrant, TournamentGamePick]:
    home = scorer.entrant(
        team_name=play_in.teams[0],
        seed=play_in.seed,
        region=play_in.region,
    )
    away = scorer.entrant(
        team_name=play_in.teams[1],
        seed=play_in.seed,
        region=play_in.region,
    )
    winner, pick = _evaluate_pick(
        game_key=play_in.game_key,
        round_label="First Four",
        region=play_in.region,
        home=home,
        away=away,
        scheduled_time=play_in.scheduled_time,
        venue_city=play_in.venue_city,
        venue_state=play_in.venue_state,
        scorer=scorer,
        pick_winner=pick_winner,
        rng=rng,
    )
    return winner, pick


def _deterministic_region_picks(
    *,
    region: TournamentRegionSpec,
    play_in_winners: dict[str, TournamentEntrant],
    scorer: TournamentBracketScorer,
) -> tuple[TournamentEntrant, list[TournamentGamePick]]:
    picks: list[TournamentGamePick] = []
    round_of_64_winners: list[TournamentEntrant] = []
    for game in region.round_of_64_games:
        home = _resolve_participant(
            participant=game.home,
            region=region.name,
            play_in_winners=play_in_winners,
            scorer=scorer,
        )
        away = _resolve_participant(
            participant=game.away,
            region=region.name,
            play_in_winners=play_in_winners,
            scorer=scorer,
        )
        winner, pick = _evaluate_pick(
            game_key=game.game_key,
            round_label="Round of 64",
            region=region.name,
            home=home,
            away=away,
            scheduled_time=game.scheduled_time,
            venue_city=game.venue_city,
            venue_state=game.venue_state,
            scorer=scorer,
            pick_winner=True,
        )
        round_of_64_winners.append(winner)
        picks.append(pick)

    round_of_32_winners = _deterministic_round(
        game_prefix=f"{region.name.lower()}-r32",
        round_label="Round of 32",
        region=region.name,
        scheduled_times=_round_of_32_times(region),
        venue_city=None,
        venue_state=None,
        entrants=round_of_64_winners,
        scorer=scorer,
        picks=picks,
    )
    sweet_16_winners = _deterministic_round(
        game_prefix=f"{region.name.lower()}-s16",
        round_label="Sweet 16",
        region=region.name,
        scheduled_times=(region.site.sweet_16_time, region.site.sweet_16_time),
        venue_city=region.site.venue_city,
        venue_state=region.site.venue_state,
        entrants=round_of_32_winners,
        scorer=scorer,
        picks=picks,
    )
    elite_winner = _deterministic_round(
        game_prefix=f"{region.name.lower()}-e8",
        round_label="Elite 8",
        region=region.name,
        scheduled_times=(region.site.elite_8_time,),
        venue_city=region.site.venue_city,
        venue_state=region.site.venue_state,
        entrants=sweet_16_winners,
        scorer=scorer,
        picks=picks,
    )
    return elite_winner[0], picks


def _deterministic_round(
    *,
    game_prefix: str,
    round_label: str,
    region: str,
    scheduled_times: tuple[datetime, ...],
    venue_city: str | None,
    venue_state: str | None,
    entrants: list[TournamentEntrant],
    scorer: TournamentBracketScorer,
    picks: list[TournamentGamePick],
) -> list[TournamentEntrant]:
    winners: list[TournamentEntrant] = []
    for index, scheduled_time in enumerate(scheduled_times, start=1):
        home = entrants[(index - 1) * 2]
        away = entrants[((index - 1) * 2) + 1]
        winner, pick = _evaluate_pick(
            game_key=f"{game_prefix}-{index}",
            round_label=round_label,
            region=region,
            home=home,
            away=away,
            scheduled_time=scheduled_time,
            venue_city=venue_city,
            venue_state=venue_state,
            scorer=scorer,
            pick_winner=True,
        )
        winners.append(winner)
        picks.append(pick)
    return winners


def _round_of_32_times(region: TournamentRegionSpec) -> tuple[datetime, ...]:
    return tuple(
        min(
            region.round_of_64_games[index * 2].scheduled_time,
            region.round_of_64_games[(index * 2) + 1].scheduled_time,
        )
        + timedelta(days=2)
        for index in range(4)
    )


def _resolve_participant(
    *,
    participant: TournamentParticipantSpec,
    region: str,
    play_in_winners: dict[str, TournamentEntrant],
    scorer: TournamentBracketScorer,
) -> TournamentEntrant:
    if participant.team_name is not None:
        return scorer.entrant(
            team_name=participant.team_name,
            seed=participant.seed,
            region=region,
        )
    if participant.play_in_game_key is None:
        raise ValueError("Participant must specify a team or a play-in game key")
    return play_in_winners[participant.play_in_game_key]


def _evaluate_pick(
    *,
    game_key: str,
    round_label: str,
    region: str | None,
    home: TournamentEntrant,
    away: TournamentEntrant,
    scheduled_time: datetime,
    venue_city: str | None,
    venue_state: str | None,
    scorer: TournamentBracketScorer,
    pick_winner: bool,
    rng: Random | None = None,
) -> tuple[TournamentEntrant, TournamentGamePick]:
    evaluation = scorer.evaluate(
        team_a=home,
        team_b=away,
        scheduled_time=scheduled_time,
        venue_city=venue_city,
        venue_state=venue_state,
    )
    evaluation = _apply_tournament_synthetic_upset_floor(
        home=home,
        away=away,
        evaluation=evaluation,
    )
    if pick_winner:
        winner = home if evaluation.team_a_probability >= 0.5 else away
    else:
        if rng is None:
            raise ValueError("rng is required when sampling a winner")
        winner = home if rng.random() <= evaluation.team_a_probability else away
    winner_probability = (
        evaluation.team_a_probability
        if winner.team.team_name == home.team.team_name
        else 1.0 - evaluation.team_a_probability
    )
    return winner, TournamentGamePick(
        game_key=game_key,
        round_label=round_label,
        region=region,
        scheduled_time=evaluation.scheduled_time,
        home_team_name=home.team.team_name,
        home_seed=home.seed,
        away_team_name=away.team.team_name,
        away_seed=away.seed,
        winner_name=winner.team.team_name,
        winner_seed=winner.seed,
        winner_probability=winner_probability,
        source=evaluation.source,
        scoring_source=evaluation.scoring_source,
        live_game_id=evaluation.live_game_id,
    )


def _apply_tournament_synthetic_upset_floor(
    *,
    home: TournamentEntrant,
    away: TournamentEntrant,
    evaluation: MatchupEvaluation,
) -> MatchupEvaluation:
    """Flip low-confidence synthetic upset probabilities back to the favorite."""
    if evaluation.scoring_source != SYNTHETIC_FALLBACK_ARTIFACT_SOURCE:
        return evaluation
    if home.seed == away.seed:
        return evaluation
    winner = home if evaluation.team_a_probability >= 0.5 else away
    winner_probability = (
        evaluation.team_a_probability
        if winner.team.team_name == home.team.team_name
        else 1.0 - evaluation.team_a_probability
    )
    favorite = home if home.seed < away.seed else away
    if winner.seed <= favorite.seed:
        return evaluation
    if winner_probability >= TOURNAMENT_SYNTHETIC_UPSET_FLOOR:
        return evaluation
    return replace(evaluation, team_a_probability=1.0 - evaluation.team_a_probability)


def _simulate_region(
    *,
    region: TournamentRegionSpec,
    play_in_winners: dict[str, TournamentEntrant],
    scorer: TournamentBracketScorer,
    rng: Random,
    counts: dict[str, dict[str, int]],
) -> TournamentEntrant:
    round_of_64_winners: list[TournamentEntrant] = []
    for game in region.round_of_64_games:
        home = _resolve_participant(
            participant=game.home,
            region=region.name,
            play_in_winners=play_in_winners,
            scorer=scorer,
        )
        away = _resolve_participant(
            participant=game.away,
            region=region.name,
            play_in_winners=play_in_winners,
            scorer=scorer,
        )
        winner = _sample_winner(
            home=home,
            away=away,
            scheduled_time=game.scheduled_time,
            venue_city=game.venue_city,
            venue_state=game.venue_state,
            scorer=scorer,
            rng=rng,
        )
        counts[winner.team.team_name]["round_of_32"] += 1
        round_of_64_winners.append(winner)

    round_of_32_winners = _sample_round(
        entrants=round_of_64_winners,
        scheduled_times=_round_of_32_times(region),
        venue_city=None,
        venue_state=None,
        scorer=scorer,
        rng=rng,
        counts=counts,
        stage_key="sweet_16",
    )
    sweet_16_winners = _sample_round(
        entrants=round_of_32_winners,
        scheduled_times=(region.site.sweet_16_time, region.site.sweet_16_time),
        venue_city=region.site.venue_city,
        venue_state=region.site.venue_state,
        scorer=scorer,
        rng=rng,
        counts=counts,
        stage_key="elite_8",
    )
    return _sample_round(
        entrants=sweet_16_winners,
        scheduled_times=(region.site.elite_8_time,),
        venue_city=region.site.venue_city,
        venue_state=region.site.venue_state,
        scorer=scorer,
        rng=rng,
        counts=counts,
        stage_key="final_4_placeholder",
    )[0]


def _sample_round(
    *,
    entrants: list[TournamentEntrant],
    scheduled_times: tuple[datetime, ...],
    venue_city: str | None,
    venue_state: str | None,
    scorer: TournamentBracketScorer,
    rng: Random,
    counts: dict[str, dict[str, int]],
    stage_key: str,
) -> list[TournamentEntrant]:
    winners: list[TournamentEntrant] = []
    for index, scheduled_time in enumerate(scheduled_times, start=1):
        del index
        home = entrants[(len(winners)) * 2]
        away = entrants[(len(winners) * 2) + 1]
        winner = _sample_winner(
            home=home,
            away=away,
            scheduled_time=scheduled_time,
            venue_city=venue_city,
            venue_state=venue_state,
            scorer=scorer,
            rng=rng,
        )
        if stage_key != "final_4_placeholder":
            counts[winner.team.team_name][stage_key] += 1
        winners.append(winner)
    return winners


def _sample_winner(
    *,
    home: TournamentEntrant,
    away: TournamentEntrant,
    scheduled_time: datetime,
    venue_city: str | None,
    venue_state: str | None,
    scorer: TournamentBracketScorer,
    rng: Random,
) -> TournamentEntrant:
    evaluation = scorer.evaluate(
        team_a=home,
        team_b=away,
        scheduled_time=scheduled_time,
        venue_city=venue_city,
        venue_state=venue_state,
    )
    return home if rng.random() <= evaluation.team_a_probability else away


def _team_requires_play_in(
    *, bracket: TournamentBracketSpec, entrant: TournamentEntrant
) -> bool:
    for play_in in bracket.play_in_games:
        if entrant.region != play_in.region or entrant.seed != play_in.seed:
            continue
        if entrant.team.team_name in play_in.teams:
            return True
    return False


def _all_entrants(
    *,
    bracket: TournamentBracketSpec,
    scorer: TournamentBracketScorer,
) -> dict[str, TournamentEntrant]:
    entrants: dict[str, TournamentEntrant] = {}
    for play_in in bracket.play_in_games:
        for team_name in play_in.teams:
            entrants.setdefault(
                team_name,
                scorer.entrant(
                    team_name=team_name,
                    seed=play_in.seed,
                    region=play_in.region,
                ),
            )
    for region in bracket.regions:
        for game in region.round_of_64_games:
            for participant in (game.home, game.away):
                if participant.team_name is None:
                    continue
                entrants.setdefault(
                    participant.team_name,
                    scorer.entrant(
                        team_name=participant.team_name,
                        seed=participant.seed,
                        region=region.name,
                    ),
                )
    return entrants


def _artifact_training_seasons(artifact: ModelArtifact) -> tuple[int, ...]:
    """Return the artifact's closed training window as an ordered season tuple."""
    return tuple(
        range(artifact.metrics.start_season, artifact.metrics.end_season + 1)
    )


def _train_tournament_synthetic_artifact(
    *,
    game_records: list[GameOddsRecord],
    seasons: Sequence[int],
    config: LogisticRegressionConfig,
) -> ModelArtifact | None:
    """Train a marketless fallback used only for synthetic bracket rows."""
    ordered_seasons = tuple(sorted(set(seasons)))
    if not ordered_seasons:
        return None

    all_examples = build_training_examples(
        game_records=game_records,
        market="moneyline",
        target_seasons=set(ordered_seasons),
    )
    trainable_examples = training_examples_only(all_examples)
    if len(trainable_examples) < config.min_examples:
        return None

    fitted_model, probabilities, labels = _fit_probability_model(
        trainable_examples=trainable_examples,
        feature_names=TOURNAMENT_SYNTHETIC_FEATURE_NAMES,
        market="moneyline",
        model_family="logistic",
        config=config,
    )
    return ModelArtifact(
        market="moneyline",
        model_family=fitted_model.model_family,
        feature_names=TOURNAMENT_SYNTHETIC_FEATURE_NAMES,
        means=fitted_model.means,
        scales=fitted_model.scales,
        weights=fitted_model.weights,
        bias=fitted_model.bias,
        metrics=_build_training_metrics(
            examples=all_examples,
            trainable_examples=trainable_examples,
            probabilities=probabilities,
            labels=labels,
            feature_names=TOURNAMENT_SYNTHETIC_FEATURE_NAMES,
            start_season=min(ordered_seasons),
            end_season=max(ordered_seasons),
        ),
        platt_scale=fitted_model.platt_scale,
        platt_bias=fitted_model.platt_bias,
        market_blend_weight=fitted_model.market_blend_weight,
        max_market_probability_delta=fitted_model.max_market_probability_delta,
        moneyline_segment_calibrations=fitted_model.moneyline_segment_calibrations,
    )


def _tournament_scoring_artifact_for_record(
    *,
    record: GameOddsRecord,
    artifact: ModelArtifact,
    synthetic_artifact: ModelArtifact | None,
) -> ModelArtifact:
    """Choose the scoring artifact for one tournament matchup record."""
    if (
        synthetic_artifact is not None
        and record.home_h2h_price is None
        and record.away_h2h_price is None
    ):
        return synthetic_artifact
    return artifact


def _build_team_lookup(
    *,
    completed_records: list[GameOddsRecord],
    live_records: list[GameOddsRecord],
) -> dict[str, TournamentTeamInfo]:
    teams: dict[str, TournamentTeamInfo] = {}
    for record in [*completed_records, *live_records]:
        teams.setdefault(
            record.home_team_name,
            TournamentTeamInfo(
                team_id=record.home_team_id,
                team_name=record.home_team_name,
                team_key=record.home_team_key,
                conference_key=record.home_conference_key,
                conference_name=record.home_conference_name,
            ),
        )
        teams.setdefault(
            record.away_team_name,
            TournamentTeamInfo(
                team_id=record.away_team_id,
                team_name=record.away_team_name,
                team_key=record.away_team_key,
                conference_key=record.away_conference_key,
                conference_name=record.away_conference_name,
            ),
        )
    return teams


def _team_aliases_by_id(
    teams_by_name: dict[str, TournamentTeamInfo],
) -> dict[int, frozenset[str]]:
    aliases_by_id: dict[int, frozenset[str]] = {}
    for team in teams_by_name.values():
        aliases_by_id.setdefault(team.team_id, build_team_aliases(team.team_name))
    return aliases_by_id


def _load_team_aliases_from_database(
    *,
    database_url: str | None,
    teams_by_name: dict[str, TournamentTeamInfo],
) -> dict[int, frozenset[str]]:
    aliases_by_id = _team_aliases_by_id(teams_by_name)
    engine = get_engine(database_url)
    with engine.connect() as connection:
        catalog = load_team_catalog_from_database(connection)
    if catalog is None:
        return aliases_by_id

    for team in teams_by_name.values():
        if team.team_key is None:
            continue
        catalog_team = catalog.teams_by_key.get(team.team_key)
        if catalog_team is None:
            continue
        expanded_aliases = set(aliases_by_id[team.team_id])
        for alias_name in catalog_team.alias_names:
            expanded_aliases.update(build_team_aliases(alias_name))
        aliases_by_id[team.team_id] = frozenset(expanded_aliases)
    return aliases_by_id


def _resolve_team_info(
    *,
    team_name: str,
    teams_by_name: dict[str, TournamentTeamInfo],
    team_aliases_by_id: dict[int, frozenset[str]],
) -> TournamentTeamInfo:
    exact_match = teams_by_name.get(team_name)
    if exact_match is not None:
        return exact_match

    requested_aliases = build_team_aliases(team_name)
    scored_matches: list[tuple[int, str, TournamentTeamInfo]] = []
    seen_team_ids: set[int] = set()
    for candidate in teams_by_name.values():
        if candidate.team_id in seen_team_ids:
            continue
        seen_team_ids.add(candidate.team_id)
        alias_score = best_alias_score(
            requested_aliases,
            team_aliases_by_id[candidate.team_id],
        )
        if alias_score > 0:
            scored_matches.append((alias_score, candidate.team_name, candidate))

    if not scored_matches:
        raise ValueError(f"Unknown tournament team name: {team_name}")

    scored_matches.sort(key=lambda item: (-item[0], item[1]))
    best_score = scored_matches[0][0]
    best_matches = [
        candidate for score, _, candidate in scored_matches if score == best_score
    ]
    if len(best_matches) != 1:
        raise ValueError(f"Ambiguous tournament team name: {team_name}")
    return best_matches[0]


def _records_by_team_pair(
    records: Sequence[GameOddsRecord],
) -> dict[frozenset[int], list[GameOddsRecord]]:
    records_by_pair: dict[frozenset[int], list[GameOddsRecord]] = defaultdict(list)
    for record in records:
        records_by_pair[frozenset((record.home_team_id, record.away_team_id))].append(
            record
        )
    return records_by_pair


def _match_record_for_pair(
    *,
    records_by_pair: dict[frozenset[int], list[GameOddsRecord]],
    team_a_id: int,
    team_b_id: int,
    scheduled_time: datetime,
) -> GameOddsRecord | None:
    records = records_by_pair.get(frozenset((team_a_id, team_b_id)), [])
    if not records:
        return None
    return min(
        records,
        key=lambda record: abs((record.commence_time - scheduled_time).total_seconds()),
    )


def _tournament_anchor_time(bracket: TournamentBracketSpec) -> datetime:
    scheduled_times = [game.scheduled_time for game in bracket.play_in_games]
    scheduled_times.extend(
        game.scheduled_time
        for region in bracket.regions
        for game in region.round_of_64_games
    )
    if not scheduled_times:
        raise ValueError("Tournament bracket must include at least one scheduled game")
    return min(scheduled_times) - timedelta(minutes=1)


def _load_known_tournament_records_at_anchor(
    *,
    bracket: TournamentBracketSpec,
    season_records: list[GameOddsRecord],
    teams_by_name: dict[str, TournamentTeamInfo],
    team_aliases_by_id: dict[int, frozenset[str]],
    anchor_time: datetime,
) -> list[GameOddsRecord]:
    records_by_pair = _records_by_team_pair(season_records)
    known_records: list[GameOddsRecord] = []

    for play_in in bracket.play_in_games:
        home = _resolve_team_info(
            team_name=play_in.teams[0],
            teams_by_name=teams_by_name,
            team_aliases_by_id=team_aliases_by_id,
        )
        away = _resolve_team_info(
            team_name=play_in.teams[1],
            teams_by_name=teams_by_name,
            team_aliases_by_id=team_aliases_by_id,
        )
        record = _match_record_for_pair(
            records_by_pair=records_by_pair,
            team_a_id=home.team_id,
            team_b_id=away.team_id,
            scheduled_time=play_in.scheduled_time,
        )
        if record is None:
            raise ValueError(
                f"Could not find stored First Four record for {play_in.teams[0]} vs "
                f"{play_in.teams[1]}"
            )
        known_records.append(
            _prediction_view_of_record(
                derive_game_record_at_observation_time(
                    record,
                    observation_time=anchor_time,
                ),
                venue_city=play_in.venue_city,
                venue_state=play_in.venue_state,
            )
        )

    for region in bracket.regions:
        for game in region.round_of_64_games:
            if game.home.team_name is None or game.away.team_name is None:
                continue
            home = _resolve_team_info(
                team_name=game.home.team_name,
                teams_by_name=teams_by_name,
                team_aliases_by_id=team_aliases_by_id,
            )
            away = _resolve_team_info(
                team_name=game.away.team_name,
                teams_by_name=teams_by_name,
                team_aliases_by_id=team_aliases_by_id,
            )
            record = _match_record_for_pair(
                records_by_pair=records_by_pair,
                team_a_id=home.team_id,
                team_b_id=away.team_id,
                scheduled_time=game.scheduled_time,
            )
            if record is None:
                if game.actual_winner_team_name is not None:
                    continue
                raise ValueError(
                    f"Could not find stored round-of-64 record for "
                    f"{game.home.team_name} vs {game.away.team_name}"
                )
            known_records.append(
                _prediction_view_of_record(
                    derive_game_record_at_observation_time(
                        record,
                        observation_time=anchor_time,
                    ),
                    venue_city=game.venue_city,
                    venue_state=game.venue_state,
                )
            )
    return known_records


def _prediction_view_of_record(
    record: GameOddsRecord,
    *,
    venue_city: str | None,
    venue_state: str | None,
) -> GameOddsRecord:
    return replace(
        record,
        completed=False,
        home_score=None,
        away_score=None,
        last_score_update=None,
        neutral_site=True,
        venue_city=venue_city or record.venue_city,
        venue_state=venue_state or record.venue_state,
    )


def _tournament_champion_pick_from_picks(
    picks: Sequence[TournamentGamePick],
) -> TournamentGamePick | None:
    for pick in reversed(picks):
        if pick.round_label == "Championship":
            return pick
    return None


def _tournament_final_four_teams(picks: Sequence[TournamentGamePick]) -> set[str]:
    return {
        pick.winner_name for pick in picks if pick.round_label == "Elite 8"
    }


def _round_label_order(picks: Sequence[TournamentGamePick]) -> list[str]:
    round_labels: list[str] = []
    for pick in picks:
        if pick.round_label not in round_labels:
            round_labels.append(pick.round_label)
    return round_labels


def _swap_game_record(record: GameOddsRecord) -> GameOddsRecord:
    return GameOddsRecord(
        game_id=record.game_id,
        season=record.season,
        game_date=record.game_date,
        commence_time=record.commence_time,
        completed=record.completed,
        home_score=record.away_score,
        away_score=record.home_score,
        home_team_id=record.away_team_id,
        home_team_name=record.away_team_name,
        away_team_id=record.home_team_id,
        away_team_name=record.home_team_name,
        home_h2h_price=record.away_h2h_price,
        away_h2h_price=record.home_h2h_price,
        home_spread_line=record.away_spread_line,
        away_spread_line=record.home_spread_line,
        home_spread_price=record.away_spread_price,
        away_spread_price=record.home_spread_price,
        total_points=record.total_points,
        h2h_open=_swap_market_aggregate(record.h2h_open),
        h2h_close=_swap_market_aggregate(record.h2h_close),
        spread_open=_swap_market_aggregate(record.spread_open),
        spread_close=_swap_market_aggregate(record.spread_close),
        total_open=record.total_open,
        total_close=record.total_close,
        home_conference_key=record.away_conference_key,
        home_conference_name=record.away_conference_name,
        away_conference_key=record.home_conference_key,
        away_conference_name=record.home_conference_name,
        observation_time=record.observation_time,
        snapshots=tuple(_swap_snapshot(snapshot) for snapshot in record.snapshots),
        current_h2h_quotes=tuple(
            _swap_snapshot(snapshot) for snapshot in record.current_h2h_quotes
        ),
        current_spread_quotes=tuple(
            _swap_snapshot(snapshot) for snapshot in record.current_spread_quotes
        ),
        home_team_key=record.away_team_key,
        away_team_key=record.home_team_key,
        neutral_site=record.neutral_site,
        venue_name=record.venue_name,
        venue_city=record.venue_city,
        venue_state=record.venue_state,
        last_score_update=record.last_score_update,
    )


def _swap_market_aggregate(
    aggregate: MarketSnapshotAggregate | None,
) -> MarketSnapshotAggregate | None:
    if aggregate is None:
        return None
    return MarketSnapshotAggregate(
        bookmaker_count=aggregate.bookmaker_count,
        team1_price=aggregate.team2_price,
        team2_price=aggregate.team1_price,
        team1_point=aggregate.team2_point,
        team2_point=aggregate.team1_point,
        total_points=aggregate.total_points,
        team1_implied_probability=aggregate.team2_implied_probability,
        team2_implied_probability=aggregate.team1_implied_probability,
        team1_probability_range=aggregate.team2_probability_range,
        team2_probability_range=aggregate.team1_probability_range,
        team1_point_range=aggregate.team2_point_range,
        team2_point_range=aggregate.team1_point_range,
        total_points_range=aggregate.total_points_range,
    )


def _swap_snapshot(snapshot: OddsSnapshotRecord) -> OddsSnapshotRecord:
    return OddsSnapshotRecord(
        game_id=snapshot.game_id,
        bookmaker_key=snapshot.bookmaker_key,
        market_key=snapshot.market_key,
        captured_at=snapshot.captured_at,
        is_closing_line=snapshot.is_closing_line,
        team1_price=snapshot.team2_price,
        team2_price=snapshot.team1_price,
        team1_point=snapshot.team2_point,
        team2_point=snapshot.team1_point,
        total_points=snapshot.total_points,
    )


__all__ = [
    "ACTUAL_MATCHUP_SOURCE",
    "DEFAULT_TOURNAMENT_BRACKET_DIR",
    "DEFAULT_TOURNAMENT_BRACKET_PATH",
    "TournamentBacktestOptions",
    "TournamentBacktestPickSeedRoleSummary",
    "TournamentBacktestRoundSummary",
    "TournamentBacktestSeasonSummary",
    "TournamentBacktestSourceSummary",
    "TournamentBacktestSummary",
    "TournamentGamePick",
    "TournamentOptions",
    "TournamentSummary",
    "TournamentTeamAdvancement",
    "backtest_tournament_model",
    "load_tournament_bracket",
    "load_tournament_brackets",
    "predict_tournament_bracket",
    "summarize_tournament_backtest",
    "summarize_tournament_backtest_season",
]
