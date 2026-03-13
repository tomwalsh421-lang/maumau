import sqlite3
from pathlib import Path

from cbb.db import (
    AvailabilityGameSideShadow,
    AvailabilityShadowStatusCount,
    AvailabilityShadowSummary,
    get_availability_game_side_shadows,
)
from cbb.modeling.backtest import (
    BacktestSummary,
    ClosingLineValueSummary,
    SpreadSegmentAttribution,
    SpreadSegmentSummary,
)
from cbb.modeling.policy import BetPolicy, PlacedBet
from cbb.modeling.report import (
    BestBacktestReportOptions,
    build_best_backtest_report,
    generate_best_backtest_report,
)


def test_generate_best_backtest_report_writes_markdown(
    monkeypatch,
    tmp_path: Path,
) -> None:
    progress_messages: list[str] = []

    monkeypatch.setattr(
        "cbb.modeling.report.get_available_seasons",
        lambda _database_url=None: [2024, 2025, 2026],
    )

    def fake_backtest_betting_model(options) -> BacktestSummary:
        assert options.market == "best"
        assert options.spread_model_family == "logistic"
        assert options.use_timing_layer is False
        if options.evaluation_season == 2024:
            return BacktestSummary(
                market="best",
                start_season=2024,
                end_season=2024,
                evaluation_season=2024,
                blocks=3,
                candidates_considered=20,
                bets_placed=10,
                wins=6,
                losses=4,
                pushes=0,
                total_staked=200.0,
                profit=-20.0,
                roi=-0.10,
                units_won=-0.80,
                starting_bankroll=1000.0,
                ending_bankroll=980.0,
                max_drawdown=0.08,
                sample_bets=[],
                clv=ClosingLineValueSummary(
                    bets_evaluated=2,
                    positive_bets=1,
                    negative_bets=1,
                    neutral_bets=0,
                    spread_bets_evaluated=2,
                    total_spread_line_delta=1.0,
                    spread_price_bets_evaluated=2,
                    total_spread_price_probability_delta=0.03,
                    spread_no_vig_bets_evaluated=2,
                    total_spread_no_vig_probability_delta=0.02,
                    spread_closing_ev_bets_evaluated=2,
                    total_spread_closing_expected_value=0.10,
                ),
                final_policy=BetPolicy(
                    min_edge=0.02,
                    min_probability_edge=0.015,
                    min_games_played=8,
                    min_positive_ev_books=2,
                    min_median_expected_value=0.01,
                    max_spread_abs_line=10.0,
                ),
            )
        if options.evaluation_season == 2025:
            return BacktestSummary(
                market="best",
                start_season=2024,
                end_season=2025,
                evaluation_season=2025,
                blocks=3,
                candidates_considered=4,
                bets_placed=0,
                wins=0,
                losses=0,
                pushes=0,
                total_staked=0.0,
                profit=0.0,
                roi=0.0,
                units_won=0.0,
                starting_bankroll=1000.0,
                ending_bankroll=1000.0,
                max_drawdown=0.0,
                sample_bets=[],
                final_policy=None,
            )
        return BacktestSummary(
            market="best",
            start_season=2024,
            end_season=2026,
            evaluation_season=2026,
            blocks=3,
            candidates_considered=8,
            bets_placed=5,
            wins=4,
            losses=1,
            pushes=0,
            total_staked=100.0,
            profit=15.0,
            roi=0.15,
            units_won=0.60,
            starting_bankroll=1000.0,
            ending_bankroll=1015.0,
            max_drawdown=0.02,
            sample_bets=[],
            clv=ClosingLineValueSummary(
                bets_evaluated=1,
                positive_bets=1,
                negative_bets=0,
                neutral_bets=0,
                moneyline_bets_evaluated=1,
                total_moneyline_probability_delta=0.01,
            ),
            final_policy=BetPolicy(
                min_edge=0.02,
                min_probability_edge=0.015,
                min_games_played=8,
                min_positive_ev_books=2,
                min_median_expected_value=0.01,
                max_spread_abs_line=10.0,
            ),
        )

    monkeypatch.setattr(
        "cbb.modeling.report.backtest_betting_model",
        fake_backtest_betting_model,
    )

    report = generate_best_backtest_report(
        BestBacktestReportOptions(
            output_path=tmp_path / "best-model-report.md",
            seasons=3,
            max_season=2026,
        ),
        progress=progress_messages.append,
    )

    assert report.selected_seasons == (2024, 2025, 2026)
    assert report.aggregate_bets == 15
    assert report.aggregate_profit == -5.0
    assert report.zero_bet_seasons == (2025,)
    assert report.generated_at
    assert report.output_path.exists()
    assert report.history_output_path is not None
    assert report.history_output_path.exists()
    assert "Best Model Backtest Report" in report.markdown
    assert "History Copy:" in report.markdown
    assert "Spread model family: `logistic`" in report.markdown
    assert "Auto-tuned spread policy: `disabled`" in report.markdown
    assert "Timing layer: `disabled`" in report.markdown
    assert "min_positive_ev_books=2" in report.markdown
    assert "max_bets_per_day=none" in report.markdown
    assert "min_median_expected_value=0.010" in report.markdown
    assert "Avg Spread Price CLV" in report.markdown
    assert "Avg Spread No-Vig Close Delta" in report.markdown
    assert "Avg Spread Closing EV" in report.markdown
    assert "+1.50 pp" in report.markdown
    assert "+1.00 pp" in report.markdown
    assert "+0.050" in report.markdown
    assert "## Decision Snapshot" in report.markdown
    assert "Strongest evidence:" in report.markdown
    assert "Main risk:" in report.markdown
    assert "Next action:" in report.markdown
    assert "## Close-Market Coverage" in report.markdown
    assert "2/2 (+100.00%)" in report.markdown
    assert "Spread closing EV" in report.markdown
    assert "## Closing-Line Value" in report.markdown
    assert "Aggregate CLV:" in report.markdown
    assert "Close-market coverage:" in report.markdown
    assert "`2024`" in report.markdown
    assert "`2025`" in report.markdown
    assert "`2026`" in report.markdown
    assert "`-20.00%`" not in report.markdown
    assert (
        "The current deployable path is positive in the latest season"
        in report.markdown
    )
    assert progress_messages[0] == "Backtesting season 2024..."
    assert (
        progress_messages[-1]
        == "Finished season 2026: bets=5, profit=+$15.00, roi=+15.00%"
    )


def test_generate_best_backtest_report_rejects_empty_window(monkeypatch) -> None:
    monkeypatch.setattr(
        "cbb.modeling.report.get_available_seasons",
        lambda _database_url=None: [2024, 2025, 2026],
    )

    try:
        generate_best_backtest_report(
            BestBacktestReportOptions(
                seasons=3,
                max_season=2023,
            )
        )
    except ValueError as exc:
        assert "No completed seasons match" in str(exc)
    else:
        raise AssertionError("Expected a ValueError for an empty season window")


def test_build_best_backtest_report_does_not_write_output(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "cbb.modeling.report.get_available_seasons",
        lambda _database_url=None: [2026],
    )

    monkeypatch.setattr(
        "cbb.modeling.report.backtest_betting_model",
        lambda _options: BacktestSummary(
            market="best",
            start_season=2024,
            end_season=2026,
            evaluation_season=2026,
            blocks=1,
            candidates_considered=4,
            bets_placed=1,
            wins=1,
            losses=0,
            pushes=0,
            total_staked=20.0,
            profit=5.0,
            roi=0.25,
            units_won=0.20,
            starting_bankroll=1000.0,
            ending_bankroll=1005.0,
            max_drawdown=0.0,
            sample_bets=[],
        ),
    )

    report = build_best_backtest_report(
        BestBacktestReportOptions(
            output_path=tmp_path / "report.md",
            seasons=1,
            max_season=2026,
        )
    )

    assert report.output_path == tmp_path / "report.md"
    assert report.history_output_path is not None
    assert not report.output_path.exists()
    assert not report.history_output_path.exists()


def test_get_availability_game_side_shadows_tracks_latest_report_rows(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "availability.sqlite"
    _create_availability_shadow_test_db(db_path)

    rows = get_availability_game_side_shadows(
        f"sqlite+pysqlite:///{db_path}",
    )

    assert [row.side for row in rows] == ["home", "away"]

    home_row = rows[0]
    assert home_row.team_name == "Duke Blue Devils"
    assert home_row.has_official_report is True
    assert home_row.team_any_out is True
    assert home_row.team_any_questionable is True
    assert home_row.team_out_count == 1
    assert home_row.team_questionable_count == 1
    assert home_row.matched_row_count == 2
    assert home_row.unmatched_row_count == 1
    assert home_row.opponent_has_official_report is True
    assert home_row.opponent_any_out is True
    assert home_row.opponent_out_count == 1
    assert home_row.latest_update_at == "2026-03-15T18:00:00+00:00"
    assert home_row.latest_minutes_before_tip == 60.0

    away_row = rows[1]
    assert away_row.team_name == "North Carolina Tar Heels"
    assert away_row.team_out_count == 1
    assert away_row.latest_minutes_before_tip == 90.0


def test_generate_best_backtest_report_renders_availability_evaluation_slices(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "cbb.modeling.report.get_available_seasons",
        lambda _database_url=None: [2026],
    )
    monkeypatch.setattr(
        "cbb.modeling.report.get_availability_shadow_summary",
        lambda _database_url=None: AvailabilityShadowSummary(
            reports_loaded=7,
            player_rows_loaded=19,
            games_covered=5,
            matched_player_rows=14,
            unmatched_player_rows=5,
        ),
    )
    monkeypatch.setattr(
        "cbb.modeling.report.get_availability_game_side_shadows",
        lambda _database_url=None: (
            AvailabilityGameSideShadow(
                game_id=1,
                season=2026,
                commence_time="2026-03-11T19:00:00+00:00",
                side="home",
                team_id=1,
                team_name="Team 1",
                opponent_team_id=101,
                opponent_name="Opponent 1",
                source_name="the_american_mbb_player_availability",
                has_official_report=True,
                opponent_has_official_report=True,
                team_any_out=True,
                team_any_questionable=False,
                opponent_any_out=False,
                opponent_any_questionable=False,
                team_out_count=1,
                team_questionable_count=0,
                opponent_out_count=0,
                opponent_questionable_count=0,
                matched_row_count=2,
                unmatched_row_count=1,
                latest_update_at="2026-03-11T17:30:00+00:00",
                latest_minutes_before_tip=90.0,
            ),
            AvailabilityGameSideShadow(
                game_id=2,
                season=2026,
                commence_time="2026-03-12T19:00:00+00:00",
                side="home",
                team_id=2,
                team_name="Team 2",
                opponent_team_id=102,
                opponent_name="Opponent 2",
                source_name="the_american_mbb_player_availability",
                has_official_report=True,
                opponent_has_official_report=True,
                team_any_out=False,
                team_any_questionable=True,
                opponent_any_out=True,
                opponent_any_questionable=False,
                team_out_count=0,
                team_questionable_count=1,
                opponent_out_count=1,
                opponent_questionable_count=0,
                matched_row_count=2,
                unmatched_row_count=0,
                latest_update_at="2026-03-12T16:00:00+00:00",
                latest_minutes_before_tip=180.0,
            ),
            AvailabilityGameSideShadow(
                game_id=3,
                season=2026,
                commence_time="2026-03-13T19:00:00+00:00",
                side="away",
                team_id=3,
                team_name="Team 3",
                opponent_team_id=103,
                opponent_name="Opponent 3",
                source_name="the_american_mbb_player_availability",
                has_official_report=True,
                opponent_has_official_report=False,
                team_any_out=True,
                team_any_questionable=False,
                opponent_any_out=False,
                opponent_any_questionable=False,
                team_out_count=1,
                team_questionable_count=0,
                opponent_out_count=0,
                opponent_questionable_count=0,
                matched_row_count=1,
                unmatched_row_count=0,
                latest_update_at="2026-03-13T11:00:00+00:00",
                latest_minutes_before_tip=480.0,
            ),
            AvailabilityGameSideShadow(
                game_id=4,
                season=2026,
                commence_time="2026-03-14T19:00:00+00:00",
                side="away",
                team_id=4,
                team_name="Team 4",
                opponent_team_id=104,
                opponent_name="Opponent 4",
                source_name="the_american_mbb_player_availability",
                has_official_report=True,
                opponent_has_official_report=True,
                team_any_out=False,
                team_any_questionable=True,
                opponent_any_out=True,
                opponent_any_questionable=False,
                team_out_count=0,
                team_questionable_count=1,
                opponent_out_count=1,
                opponent_questionable_count=0,
                matched_row_count=2,
                unmatched_row_count=0,
                latest_update_at="2026-03-14T19:05:00+00:00",
                latest_minutes_before_tip=-5.0,
            ),
            AvailabilityGameSideShadow(
                game_id=5,
                season=2026,
                commence_time="2026-03-15T19:00:00+00:00",
                side="home",
                team_id=5,
                team_name="Team 5",
                opponent_team_id=105,
                opponent_name="Opponent 5",
                source_name="the_american_mbb_player_availability",
                has_official_report=True,
                opponent_has_official_report=True,
                team_any_out=False,
                team_any_questionable=False,
                opponent_any_out=False,
                opponent_any_questionable=True,
                team_out_count=0,
                team_questionable_count=0,
                opponent_out_count=0,
                opponent_questionable_count=1,
                matched_row_count=2,
                unmatched_row_count=0,
                latest_update_at="2026-03-15T18:15:00+00:00",
                latest_minutes_before_tip=45.0,
            ),
        ),
    )
    monkeypatch.setattr(
        "cbb.modeling.report.backtest_betting_model",
        lambda _options: BacktestSummary(
            market="best",
            start_season=2024,
            end_season=2026,
            evaluation_season=2026,
            blocks=1,
            candidates_considered=12,
            bets_placed=6,
            wins=4,
            losses=2,
            pushes=0,
            total_staked=120.0,
            profit=18.0,
            roi=0.15,
            units_won=0.72,
            starting_bankroll=1000.0,
            ending_bankroll=1018.0,
            max_drawdown=0.03,
            sample_bets=[],
            placed_bets=[
                _placed_bet(game_id=1, side="home", settlement="win"),
                _placed_bet(game_id=2, side="home", settlement="loss"),
                _placed_bet(game_id=3, side="away", settlement="win"),
                _placed_bet(game_id=4, side="away", settlement="loss"),
                _placed_bet(game_id=5, side="home", settlement="win"),
                _placed_bet(game_id=6, side="away", settlement="win"),
            ],
        ),
    )

    report = build_best_backtest_report(
        BestBacktestReportOptions(
            output_path=tmp_path / "report.md",
            seasons=1,
            max_season=2026,
        )
    )

    assert "## Availability Evaluation Slices" in report.markdown
    assert "Rows with fewer than `5` settled bets" in report.markdown
    assert "### Coverage" in report.markdown
    assert "| Covered side report | 5 | 3-2-0 |" in report.markdown
    assert "| Uncovered side report | 1 | 1-0-0 |" in report.markdown
    assert "### Status Flags" in report.markdown
    assert "Side has any out" in report.markdown
    assert "Opponent has any out" in report.markdown
    assert "### Latest Update Timing" in report.markdown
    assert "insufficient sample" in report.markdown


def test_generate_best_backtest_report_renders_availability_shadow_section(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "cbb.modeling.report.get_available_seasons",
        lambda _database_url=None: [2026],
    )
    monkeypatch.setattr(
        "cbb.modeling.report.get_availability_shadow_summary",
        lambda _database_url=None: AvailabilityShadowSummary(
            reports_loaded=3,
            player_rows_loaded=11,
            games_covered=2,
            matched_player_rows=9,
            unmatched_player_rows=2,
            latest_update_at="2026-03-11T18:05:00+00:00",
            latest_minutes_before_tip=85.0,
            seasons=(2026,),
            scope_labels=("postseason",),
            source_labels=("ncaa",),
            status_counts=(
                AvailabilityShadowStatusCount(status="available", row_count=6),
                AvailabilityShadowStatusCount(status="out", row_count=3),
            ),
        ),
    )
    monkeypatch.setattr(
        "cbb.modeling.report.backtest_betting_model",
        lambda _options: BacktestSummary(
            market="best",
            start_season=2024,
            end_season=2026,
            evaluation_season=2026,
            blocks=1,
            candidates_considered=4,
            bets_placed=1,
            wins=1,
            losses=0,
            pushes=0,
            total_staked=20.0,
            profit=5.0,
            roi=0.25,
            units_won=0.20,
            starting_bankroll=1000.0,
            ending_bankroll=1005.0,
            max_drawdown=0.0,
            sample_bets=[],
        ),
    )

    report = build_best_backtest_report(
        BestBacktestReportOptions(
            output_path=tmp_path / "report.md",
            seasons=1,
            max_season=2026,
        )
    )

    assert report.availability_shadow_summary.games_covered == 2
    assert "## Official Availability Shadow" in report.markdown
    assert "Stored official availability data is shadow-only" in report.markdown
    assert "Availability shadow data:" in report.markdown
    assert "`2` games, `11` status rows, `2` unmatched" in report.markdown
    assert "| Covered games | `2` |" in report.markdown
    assert "| Status mix | `available` 6, `out` 3 |" in report.markdown
    assert (
        "not used by the live prediction, backtest, or betting-policy paths yet"
        in report.markdown
    )
    assert (
        "The current deployable path is positive in every season where it "
        "actually placed bets."
        in report.markdown
    )


def test_generate_best_backtest_report_renders_empty_availability_shadow_state(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "cbb.modeling.report.get_available_seasons",
        lambda _database_url=None: [2026],
    )
    monkeypatch.setattr(
        "cbb.modeling.report.get_availability_shadow_summary",
        lambda _database_url=None: AvailabilityShadowSummary(),
    )
    monkeypatch.setattr(
        "cbb.modeling.report.backtest_betting_model",
        lambda _options: BacktestSummary(
            market="best",
            start_season=2024,
            end_season=2026,
            evaluation_season=2026,
            blocks=1,
            candidates_considered=4,
            bets_placed=1,
            wins=1,
            losses=0,
            pushes=0,
            total_staked=20.0,
            profit=5.0,
            roi=0.25,
            units_won=0.20,
            starting_bankroll=1000.0,
            ending_bankroll=1005.0,
            max_drawdown=0.0,
            sample_bets=[],
        ),
    )

    report = build_best_backtest_report(
        BestBacktestReportOptions(
            output_path=tmp_path / "report.md",
            seasons=1,
            max_season=2026,
        )
    )

    assert "## Official Availability Shadow" in report.markdown
    assert "| Shadow data | `not loaded` |" in report.markdown
    assert (
        "No official availability shadow data is currently loaded."
        in report.markdown
    )


def _create_availability_shadow_test_db(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE teams (
            team_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL
        );

        CREATE TABLE games (
            game_id INTEGER PRIMARY KEY,
            season INTEGER NOT NULL,
            commence_time TEXT,
            team1_id INTEGER NOT NULL,
            team2_id INTEGER NOT NULL
        );

        CREATE TABLE ncaa_tournament_availability_reports (
            availability_report_id INTEGER PRIMARY KEY,
            source_name TEXT NOT NULL,
            reported_at TEXT,
            captured_at TEXT,
            updated_at TEXT,
            created_at TEXT,
            game_id INTEGER,
            team_id INTEGER
        );

        CREATE TABLE ncaa_tournament_availability_player_statuses (
            availability_player_status_id INTEGER PRIMARY KEY,
            availability_report_id INTEGER NOT NULL,
            team_id INTEGER,
            status_key TEXT
        );
        """
    )
    connection.executemany(
        "INSERT INTO teams (team_id, name) VALUES (?, ?)",
        [
            (1, "Duke Blue Devils"),
            (2, "North Carolina Tar Heels"),
        ],
    )
    connection.execute(
        """
        INSERT INTO games (game_id, season, commence_time, team1_id, team2_id)
        VALUES (?, ?, ?, ?, ?)
        """,
        (101, 2026, "2026-03-15T19:00:00+00:00", 1, 2),
    )
    connection.executemany(
        """
        INSERT INTO ncaa_tournament_availability_reports (
            availability_report_id,
            source_name,
            reported_at,
            captured_at,
            updated_at,
            created_at,
            game_id,
            team_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                1,
                "the_american_mbb_player_availability",
                "2026-03-15T16:00:00+00:00",
                "2026-03-15T16:05:00+00:00",
                "2026-03-15T16:05:00+00:00",
                "2026-03-15T16:05:00+00:00",
                101,
                1,
            ),
            (
                2,
                "the_american_mbb_player_availability",
                "2026-03-15T18:00:00+00:00",
                "2026-03-15T18:02:00+00:00",
                "2026-03-15T18:02:00+00:00",
                "2026-03-15T18:02:00+00:00",
                101,
                1,
            ),
            (
                3,
                "the_american_mbb_player_availability",
                "2026-03-15T17:30:00+00:00",
                "2026-03-15T17:31:00+00:00",
                "2026-03-15T17:31:00+00:00",
                "2026-03-15T17:31:00+00:00",
                101,
                2,
            ),
        ],
    )
    connection.executemany(
        """
        INSERT INTO ncaa_tournament_availability_player_statuses (
            availability_player_status_id,
            availability_report_id,
            team_id,
            status_key
        )
        VALUES (?, ?, ?, ?)
        """,
        [
            (1, 1, 1, "out"),
            (2, 2, 1, "out"),
            (3, 2, 1, "questionable"),
            (4, 2, None, "out"),
            (5, 3, 2, "out"),
        ],
    )
    connection.commit()
    connection.close()


def _placed_bet(
    *,
    game_id: int,
    side: str,
    settlement: str,
    stake_amount: float = 20.0,
) -> PlacedBet:
    return PlacedBet(
        game_id=game_id,
        commence_time="2026-03-15T19:00:00+00:00",
        market="spread",
        team_name=f"Team {game_id}",
        opponent_name=f"Opponent {game_id}",
        side=side,
        market_price=-110.0,
        line_value=-4.5,
        model_probability=0.55,
        implied_probability=0.50,
        probability_edge=0.05,
        expected_value=0.04,
        stake_fraction=0.02,
        stake_amount=stake_amount,
        settlement=settlement,
    )


def test_generate_best_backtest_report_calls_out_stake_profile(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "cbb.modeling.report.get_available_seasons",
        lambda _database_url=None: [2026],
    )

    def fake_backtest_betting_model(_options) -> BacktestSummary:
        bets = [
            _placed_bet(game_id=1, side="home", settlement="win", stake_amount=10.0),
            _placed_bet(game_id=2, side="away", settlement="loss", stake_amount=25.0),
            _placed_bet(game_id=3, side="home", settlement="win", stake_amount=60.0),
        ]
        return BacktestSummary(
            market="best",
            start_season=2024,
            end_season=2026,
            evaluation_season=2026,
            blocks=3,
            candidates_considered=20,
            bets_placed=3,
            wins=2,
            losses=1,
            pushes=0,
            total_staked=95.0,
            profit=18.0,
            roi=18.0 / 95.0,
            units_won=0.72,
            starting_bankroll=3750.0,
            ending_bankroll=3768.0,
            max_drawdown=0.03,
            sample_bets=bets[:1],
            placed_bets=bets,
        )

    monkeypatch.setattr(
        "cbb.modeling.report.backtest_betting_model",
        fake_backtest_betting_model,
    )

    report = generate_best_backtest_report(
        BestBacktestReportOptions(
            output_path=tmp_path / "best-model-report.md",
            seasons=1,
            max_season=2026,
        )
    )

    assert "Stake profile: typical settled bet `+$25.00`" in report.markdown
    assert "Stake sizing: average `+$31.67`, median `+$25.00`" in report.markdown
    assert "smallest `+$10.00`, largest `+$60.00`" in report.markdown


def test_generate_best_backtest_report_renders_spread_segment_attribution(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "cbb.modeling.report.get_available_seasons",
        lambda _database_url=None: [2026],
    )

    def fake_backtest_betting_model(options) -> BacktestSummary:
        _ = options
        return BacktestSummary(
            market="best",
            start_season=2024,
            end_season=2026,
            evaluation_season=2026,
            blocks=3,
            candidates_considered=20,
            bets_placed=10,
            wins=6,
            losses=4,
            pushes=0,
            total_staked=200.0,
            profit=15.0,
            roi=0.075,
            units_won=0.60,
            starting_bankroll=1000.0,
            ending_bankroll=1015.0,
            max_drawdown=0.03,
            sample_bets=[],
            spread_segment_attribution=(
                SpreadSegmentAttribution(
                    dimension="expected_value_bucket",
                    segments=(
                        SpreadSegmentSummary(
                            value="ev_4_to_6",
                            bets=7,
                            total_staked=140.0,
                            profit=9.0,
                            roi=0.0642857143,
                            share_of_bets=0.70,
                            clv=ClosingLineValueSummary(
                                bets_evaluated=7,
                                positive_bets=3,
                                negative_bets=4,
                                neutral_bets=0,
                                spread_closing_ev_bets_evaluated=7,
                                total_spread_closing_expected_value=0.28,
                            ),
                        ),
                        SpreadSegmentSummary(
                            value="ev_6_to_8",
                            bets=3,
                            total_staked=60.0,
                            profit=6.0,
                            roi=0.10,
                            share_of_bets=0.30,
                            clv=ClosingLineValueSummary(
                                bets_evaluated=3,
                                positive_bets=2,
                                negative_bets=1,
                                neutral_bets=0,
                                spread_closing_ev_bets_evaluated=3,
                                total_spread_closing_expected_value=0.15,
                            ),
                        ),
                    ),
                ),
                SpreadSegmentAttribution(
                    dimension="season_phase",
                    segments=(
                        SpreadSegmentSummary(
                            value="early",
                            bets=4,
                            total_staked=80.0,
                            profit=-8.0,
                            roi=-0.10,
                            share_of_bets=0.40,
                            clv=ClosingLineValueSummary(
                                bets_evaluated=4,
                                positive_bets=1,
                                negative_bets=3,
                                neutral_bets=0,
                                spread_closing_ev_bets_evaluated=4,
                                total_spread_closing_expected_value=-0.08,
                            ),
                        ),
                        SpreadSegmentSummary(
                            value="established",
                            bets=6,
                            total_staked=120.0,
                            profit=23.0,
                            roi=0.1916666667,
                            share_of_bets=0.60,
                            clv=ClosingLineValueSummary(
                                bets_evaluated=6,
                                positive_bets=4,
                                negative_bets=2,
                                neutral_bets=0,
                                spread_closing_ev_bets_evaluated=6,
                                total_spread_closing_expected_value=0.18,
                            ),
                        ),
                    ),
                ),
            ),
        )

    monkeypatch.setattr(
        "cbb.modeling.report.backtest_betting_model",
        fake_backtest_betting_model,
    )

    report = generate_best_backtest_report(
        BestBacktestReportOptions(
            output_path=tmp_path / "best-model-report.md",
            seasons=1,
            max_season=2026,
        )
    )

    assert "## Spread Segment Attribution" in report.markdown
    assert "### Expected Value Bucket" in report.markdown
    assert "| `4% to 6%` | 7 | +70.00% | +$9.00 | +6.43% | +0.040 |" in report.markdown
    assert "### Season Phase" in report.markdown
    assert "| `Early` | 4 | +40.00% | -$8.00 | -10.00% | -0.020 |" in report.markdown
    assert (
        "| `Established` | 6 | +60.00% | +$23.00 | +19.17% | +0.030 |"
        in report.markdown
    )
