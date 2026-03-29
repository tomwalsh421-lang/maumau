from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from cbb.modeling.artifacts import ModelArtifact, TrainingMetrics
from cbb.modeling.dataset import GameOddsRecord
from cbb.modeling.tournament import (
    DEFAULT_TOURNAMENT_BRACKET_DIR,
    DEFAULT_TOURNAMENT_BRACKET_PATH,
    LIVE_MARKET_ARTIFACT_SOURCE,
    LIVE_MATCHUP_SOURCE,
    SYNTHETIC_FALLBACK_ARTIFACT_SOURCE,
    SYNTHETIC_MATCHUP_SOURCE,
    MatchupEvaluation,
    TournamentBacktestRoundSummary,
    TournamentEntrant,
    TournamentTeamInfo,
    _evaluate_pick,
    _tournament_scoring_artifact_for_record,
    build_deterministic_bracket,
    load_tournament_bracket,
    load_tournament_brackets,
    simulate_tournament,
    summarize_tournament_backtest,
    summarize_tournament_backtest_season,
)


class FakeScorer:
    def __init__(self) -> None:
        self._teams_by_name: dict[str, TournamentTeamInfo] = {}
        self._next_team_id = 1

    def entrant(self, *, team_name: str, seed: int, region: str) -> TournamentEntrant:
        team = self._teams_by_name.get(team_name)
        if team is None:
            team = TournamentTeamInfo(
                team_id=self._next_team_id,
                team_name=team_name,
                team_key=None,
                conference_key=None,
                conference_name=None,
            )
            self._teams_by_name[team_name] = team
            self._next_team_id += 1
        return TournamentEntrant(team=team, seed=seed, region=region)

    def evaluate(
        self,
        *,
        team_a: TournamentEntrant,
        team_b: TournamentEntrant,
        scheduled_time,
        venue_city,
        venue_state,
    ) -> MatchupEvaluation:
        del venue_city, venue_state
        if team_a.seed == team_b.seed:
            probability = (
                0.55
                if team_a.team.team_name < team_b.team.team_name
                else 0.45
            )
        else:
            probability = max(
                0.05,
                min(0.95, 0.5 + (team_b.seed - team_a.seed) * 0.035),
            )
        return MatchupEvaluation(
            team_a_probability=probability,
            source=LIVE_MATCHUP_SOURCE,
            scoring_source="moneyline_market_artifact",
            live_game_id=None,
            scheduled_time=scheduled_time.isoformat(),
        )


def _artifact(name: str) -> ModelArtifact:
    return ModelArtifact(
        market="moneyline",
        model_family="logistic",
        feature_names=("home_side",),
        means=(0.0,),
        scales=(1.0,),
        weights=(0.0,),
        bias=0.0,
        metrics=TrainingMetrics(
            examples=1,
            priced_examples=1,
            training_examples=1,
            feature_names=("home_side",),
            log_loss=0.0,
            brier_score=0.0,
            accuracy=0.0,
            start_season=2025,
            end_season=2025,
            trained_at=name,
        ),
    )


def _record(
    game_id: int,
    *,
    home_h2h_price: float | None = None,
    away_h2h_price: float | None = None,
) -> GameOddsRecord:
    return GameOddsRecord(
        game_id=game_id,
        season=2026,
        game_date="2026-03-18",
        commence_time=datetime(2026, 3, 18, 18, 0, tzinfo=UTC),
        completed=False,
        home_score=None,
        away_score=None,
        home_team_id=1,
        home_team_name="Home",
        away_team_id=2,
        away_team_name="Away",
        home_h2h_price=home_h2h_price,
        away_h2h_price=away_h2h_price,
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
    )


def test_load_tournament_bracket_parses_2026_bracket_file() -> None:
    bracket = load_tournament_bracket(DEFAULT_TOURNAMENT_BRACKET_PATH)

    assert bracket.tournament_key == "ncaa-men-2026"
    assert bracket.season == 2026
    assert len(bracket.play_in_games) == 2
    assert [region.name for region in bracket.regions] == [
        "East",
        "West",
        "South",
        "Midwest",
    ]
    assert bracket.final_four.pairings == (
        ("East", "West"),
        ("South", "Midwest"),
    )


def test_load_tournament_brackets_includes_historical_specs() -> None:
    brackets = load_tournament_brackets(DEFAULT_TOURNAMENT_BRACKET_DIR)

    assert [bracket.season for bracket in brackets] == [
        2021,
        2022,
        2023,
        2024,
        2025,
        2026,
    ]


def test_load_tournament_bracket_parses_actual_winner_override() -> None:
    bracket = load_tournament_bracket(
        DEFAULT_TOURNAMENT_BRACKET_DIR / "ncaa_men_2021.json"
    )

    west_region = next(region for region in bracket.regions if region.name == "West")
    walkover_game = next(
        game for game in west_region.round_of_64_games if game.game_key == "west-r64-7"
    )

    assert walkover_game.actual_winner_team_name == "Oregon Ducks"


def test_build_deterministic_bracket_returns_picks_for_all_games() -> None:
    bracket = load_tournament_bracket(DEFAULT_TOURNAMENT_BRACKET_PATH)

    picks = build_deterministic_bracket(
        bracket=bracket,
        scorer=FakeScorer(),
    )

    assert len(picks) == 65
    assert picks[0].round_label == "First Four"
    assert picks[-1].round_label == "Championship"
    assert picks[-1].winner_seed == 1
    assert {pick.source for pick in picks} == {LIVE_MATCHUP_SOURCE}


def test_simulate_tournament_tracks_play_in_and_advancement_probabilities() -> None:
    bracket = load_tournament_bracket(DEFAULT_TOURNAMENT_BRACKET_PATH)

    advancement = simulate_tournament(
        bracket=bracket,
        scorer=FakeScorer(),
        simulations=200,
        random_seed=7,
    )

    by_team = {item.team_name: item for item in advancement}
    assert len(by_team) == 66
    assert by_team["Duke Blue Devils"].round_of_64_probability == pytest.approx(1.0)
    assert (
        by_team["Lehigh Mountain Hawks"].round_of_64_probability
        + by_team["Prairie View A&M Panthers"].round_of_64_probability
        == pytest.approx(1.0, abs=0.05)
    )
    assert 0.0 <= by_team["Florida Gators"].title_probability <= 1.0
    assert 0.0 <= by_team["Michigan Wolverines"].championship_probability <= 1.0


def test_summarize_tournament_backtest_season_reports_perfect_accuracy() -> None:
    bracket = load_tournament_bracket(DEFAULT_TOURNAMENT_BRACKET_PATH)
    predicted_picks = build_deterministic_bracket(
        bracket=bracket,
        scorer=FakeScorer(),
    )
    actual_picks = build_deterministic_bracket(
        bracket=bracket,
        scorer=FakeScorer(),
    )

    summary = summarize_tournament_backtest_season(
        bracket=bracket,
        training_seasons=(2024, 2025, 2026),
        predicted_picks=predicted_picks,
        actual_picks=actual_picks,
    )

    assert summary.games == 65
    assert summary.correct_picks == 65
    assert summary.accuracy == pytest.approx(1.0)
    assert summary.average_actual_winner_probability > 0.5
    assert summary.champion_correct is True
    assert summary.final_four_teams_correct == 4
    assert summary.round_summaries[0].round_label == "First Four"
    assert summary.round_summaries[0].source_summaries[0].source == (
        "moneyline_market_artifact"
    )
    assert summary.round_summaries[0].source_summaries[0].games == 2
    assert summary.round_summaries[0].average_actual_winner_probability > 0.5
    assert (
        summary.round_summaries[0].source_summaries[0].accuracy
        == pytest.approx(1.0)
    )
    assert (
        summary.round_summaries[0].source_summaries[0].average_actual_winner_probability
        > 0.5
    )
    assert summary.source_summaries[0].source == "moneyline_market_artifact"
    assert summary.source_summaries[0].games == 65
    assert summary.source_summaries[0].accuracy == pytest.approx(1.0)
    assert summary.source_summaries[0].average_actual_winner_probability > 0.5
    assert sum(item.games for item in summary.pick_seed_role_summaries) == summary.games
    assert sum(item.games for item in summary.pick_seed_gap_summaries) == summary.games
    assert (
        sum(item.games for item in summary.synthetic_upset_probability_summaries)
        <= summary.games
    )
    assert all(
        item.accuracy == pytest.approx(1.0)
        for item in summary.pick_seed_role_summaries
    )
    assert all(
        item.accuracy == pytest.approx(1.0)
        for item in summary.pick_seed_gap_summaries
    )
    assert all(
        item.average_actual_winner_probability > 0.5
        for item in summary.pick_seed_role_summaries
    )
    assert all(
        item.average_actual_winner_probability > 0.5
        for item in summary.pick_seed_gap_summaries
    )
    assert all(
        round_summary.accuracy == pytest.approx(1.0)
        for round_summary in summary.round_summaries
    )


def test_summarize_tournament_backtest_aggregates_seasons() -> None:
    season_summary = summarize_tournament_backtest_season(
        bracket=load_tournament_bracket(DEFAULT_TOURNAMENT_BRACKET_PATH),
        training_seasons=(2024, 2025, 2026),
        predicted_picks=build_deterministic_bracket(
            bracket=load_tournament_bracket(DEFAULT_TOURNAMENT_BRACKET_PATH),
            scorer=FakeScorer(),
        ),
        actual_picks=build_deterministic_bracket(
            bracket=load_tournament_bracket(DEFAULT_TOURNAMENT_BRACKET_PATH),
            scorer=FakeScorer(),
        ),
    )
    adjusted = replace(
        season_summary,
        season=2025,
        round_summaries=[
            TournamentBacktestRoundSummary(
                round_label=item.round_label,
                games=item.games,
                correct_picks=item.correct_picks,
                accuracy=item.accuracy,
                average_actual_winner_probability=item.average_actual_winner_probability,
                source_summaries=item.source_summaries,
            )
            for item in season_summary.round_summaries
        ],
    )

    summary = summarize_tournament_backtest(
        generated_at=datetime(2026, 3, 18, 20, 0, tzinfo=UTC),
        season_summaries=[season_summary, adjusted],
    )

    assert summary.games == 130
    assert summary.correct_picks == 130
    assert summary.accuracy == pytest.approx(1.0)
    assert summary.champion_hits == 2
    assert summary.round_summaries[0].round_label == "First Four"
    assert summary.round_summaries[0].source_summaries[0].source == (
        "moneyline_market_artifact"
    )
    assert summary.round_summaries[0].source_summaries[0].games == 4
    assert summary.round_summaries[0].average_actual_winner_probability > 0.5
    assert summary.source_summaries[0].source == "moneyline_market_artifact"
    assert summary.source_summaries[0].games == 130
    assert summary.source_summaries[0].average_actual_winner_probability > 0.5
    assert sum(item.games for item in summary.pick_seed_role_summaries) == summary.games
    assert sum(item.games for item in summary.pick_seed_gap_summaries) == summary.games
    assert (
        sum(item.games for item in summary.synthetic_upset_probability_summaries)
        <= summary.games
    )
    assert all(
        item.average_actual_winner_probability > 0.5
        for item in summary.pick_seed_role_summaries
    )
    assert all(
        item.average_actual_winner_probability > 0.5
        for item in summary.pick_seed_gap_summaries
    )


def test_marketless_tournament_rows_use_synthetic_artifact() -> None:
    live_artifact = _artifact("live")
    synthetic_artifact = _artifact("synthetic")

    assert (
        _tournament_scoring_artifact_for_record(
            record=_record(game_id=123, home_h2h_price=-140.0, away_h2h_price=120.0),
            artifact=live_artifact,
            synthetic_artifact=synthetic_artifact,
        )
        is live_artifact
    )


def test_evaluate_pick_flips_low_confidence_synthetic_upset_to_favorite() -> None:
    class LowConfidenceSyntheticUpsetScorer(FakeScorer):
        def evaluate(
            self,
            *,
            team_a: TournamentEntrant,
            team_b: TournamentEntrant,
            scheduled_time,
            venue_city,
            venue_state,
        ) -> MatchupEvaluation:
            del team_a, team_b, venue_city, venue_state
            return MatchupEvaluation(
                team_a_probability=0.55,
                source=SYNTHETIC_MATCHUP_SOURCE,
                scoring_source=SYNTHETIC_FALLBACK_ARTIFACT_SOURCE,
                live_game_id=None,
                scheduled_time=scheduled_time.isoformat(),
            )

    scorer = LowConfidenceSyntheticUpsetScorer()
    home = scorer.entrant(team_name="Twelve Seed", seed=12, region="West")
    away = scorer.entrant(team_name="Five Seed", seed=5, region="West")

    winner, pick = _evaluate_pick(
        game_key="west-r64-1",
        round_label="Round of 64",
        region="West",
        home=home,
        away=away,
        scheduled_time=datetime(2026, 3, 20, 16, 0, tzinfo=UTC),
        venue_city=None,
        venue_state=None,
        scorer=scorer,
        pick_winner=True,
    )

    assert winner.team.team_name == "Five Seed"
    assert pick.winner_name == "Five Seed"
    assert pick.winner_seed == 5
    assert pick.winner_probability == pytest.approx(0.55)


def test_evaluate_pick_keeps_confident_synthetic_upset() -> None:
    class HighConfidenceSyntheticUpsetScorer(FakeScorer):
        def evaluate(
            self,
            *,
            team_a: TournamentEntrant,
            team_b: TournamentEntrant,
            scheduled_time,
            venue_city,
            venue_state,
        ) -> MatchupEvaluation:
            del team_a, team_b, venue_city, venue_state
            return MatchupEvaluation(
                team_a_probability=0.63,
                source=SYNTHETIC_MATCHUP_SOURCE,
                scoring_source=SYNTHETIC_FALLBACK_ARTIFACT_SOURCE,
                live_game_id=None,
                scheduled_time=scheduled_time.isoformat(),
            )

    scorer = HighConfidenceSyntheticUpsetScorer()
    home = scorer.entrant(team_name="Twelve Seed", seed=12, region="West")
    away = scorer.entrant(team_name="Five Seed", seed=5, region="West")

    winner, pick = _evaluate_pick(
        game_key="west-r64-1",
        round_label="Round of 64",
        region="West",
        home=home,
        away=away,
        scheduled_time=datetime(2026, 3, 20, 16, 0, tzinfo=UTC),
        venue_city=None,
        venue_state=None,
        scorer=scorer,
        pick_winner=True,
    )

    assert winner.team.team_name == "Twelve Seed"
    assert pick.winner_name == "Twelve Seed"
    assert pick.winner_seed == 12
    assert pick.winner_probability == pytest.approx(0.63)


def test_evaluate_pick_leaves_priced_upsets_unchanged() -> None:
    class PricedUpsetScorer(FakeScorer):
        def evaluate(
            self,
            *,
            team_a: TournamentEntrant,
            team_b: TournamentEntrant,
            scheduled_time,
            venue_city,
            venue_state,
        ) -> MatchupEvaluation:
            del team_a, team_b, venue_city, venue_state
            return MatchupEvaluation(
                team_a_probability=0.55,
                source=LIVE_MATCHUP_SOURCE,
                scoring_source=LIVE_MARKET_ARTIFACT_SOURCE,
                live_game_id=123,
                scheduled_time=scheduled_time.isoformat(),
            )

    scorer = PricedUpsetScorer()
    home = scorer.entrant(team_name="Twelve Seed", seed=12, region="West")
    away = scorer.entrant(team_name="Five Seed", seed=5, region="West")

    winner, pick = _evaluate_pick(
        game_key="west-r64-1",
        round_label="Round of 64",
        region="West",
        home=home,
        away=away,
        scheduled_time=datetime(2026, 3, 20, 16, 0, tzinfo=UTC),
        venue_city=None,
        venue_state=None,
        scorer=scorer,
        pick_winner=True,
    )

    assert winner.team.team_name == "Twelve Seed"
    assert pick.winner_name == "Twelve Seed"
    assert pick.winner_probability == pytest.approx(0.55)
