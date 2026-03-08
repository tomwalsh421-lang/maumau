from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from cbb.modeling import (
    BacktestOptions,
    BetPolicy,
    LogisticRegressionConfig,
    PredictionOptions,
    TrainingOptions,
    backtest_betting_model,
    load_artifact,
    predict_best_bets,
    train_betting_model,
)


def test_train_betting_model_saves_moneyline_artifact(tmp_path: Path) -> None:
    database_url, artifacts_dir = _create_model_test_environment(tmp_path)

    summary = train_betting_model(
        TrainingOptions(
            market="moneyline",
            seasons_back=2,
            max_season=2026,
            artifact_name="unit_test",
            database_url=database_url,
            artifacts_dir=artifacts_dir,
            config=LogisticRegressionConfig(
                epochs=250,
                min_examples=8,
            ),
        )
    )

    artifact = load_artifact(
        market="moneyline",
        artifact_name="unit_test",
        artifacts_dir=artifacts_dir,
    )
    latest_artifact = load_artifact(
        market="moneyline",
        artifact_name="latest",
        artifacts_dir=artifacts_dir,
    )

    assert summary.market == "moneyline"
    assert summary.start_season == 2025
    assert summary.end_season == 2026
    assert summary.training_examples >= 8
    assert summary.priced_examples >= 8
    assert summary.artifact_path.exists()
    assert artifact.market == "moneyline"
    assert artifact.metrics.training_examples == summary.training_examples
    assert latest_artifact.metrics.training_examples == summary.training_examples


def test_train_betting_model_supports_spread_artifact(tmp_path: Path) -> None:
    database_url, artifacts_dir = _create_model_test_environment(tmp_path)

    summary = train_betting_model(
        TrainingOptions(
            market="spread",
            seasons_back=2,
            max_season=2026,
            artifact_name="spread_test",
            database_url=database_url,
            artifacts_dir=artifacts_dir,
            config=LogisticRegressionConfig(
                epochs=250,
                min_examples=8,
            ),
        )
    )

    artifact = load_artifact(
        market="spread",
        artifact_name="spread_test",
        artifacts_dir=artifacts_dir,
    )

    assert summary.market == "spread"
    assert summary.training_examples >= 8
    assert artifact.market == "spread"
    assert len(artifact.weights) == len(artifact.feature_names)


def test_backtest_betting_model_reports_bankroll_metrics(tmp_path: Path) -> None:
    database_url, _ = _create_model_test_environment(tmp_path)

    summary = backtest_betting_model(
        BacktestOptions(
            market="moneyline",
            seasons_back=2,
            evaluation_season=2026,
            starting_bankroll=1000.0,
            unit_size=25.0,
            retrain_days=30,
            database_url=database_url,
            policy=BetPolicy(
                min_edge=-1.0,
                min_confidence=0.0,
                kelly_fraction=0.25,
                max_bet_fraction=0.05,
                max_daily_exposure_fraction=0.20,
            ),
            config=LogisticRegressionConfig(
                epochs=250,
                min_examples=4,
            ),
        )
    )

    assert summary.market == "moneyline"
    assert summary.evaluation_season == 2026
    assert summary.blocks >= 1
    assert summary.candidates_considered >= 1
    assert summary.bets_placed >= 1
    assert summary.total_staked > 0
    assert summary.ending_bankroll > 0


def test_predict_best_bets_uses_trained_artifact(tmp_path: Path) -> None:
    database_url, artifacts_dir = _create_model_test_environment(tmp_path)
    train_betting_model(
        TrainingOptions(
            market="moneyline",
            seasons_back=2,
            max_season=2026,
            artifact_name="predict_test",
            database_url=database_url,
            artifacts_dir=artifacts_dir,
            config=LogisticRegressionConfig(
                epochs=250,
                min_examples=8,
            ),
        )
    )

    summary = predict_best_bets(
        PredictionOptions(
            market="best",
            artifact_name="predict_test",
            bankroll=1000.0,
            limit=5,
            database_url=database_url,
            artifacts_dir=artifacts_dir,
            now=datetime(2026, 3, 9, 18, 45, tzinfo=UTC),
            policy=BetPolicy(
                min_edge=-1.0,
                min_confidence=0.0,
                kelly_fraction=0.25,
                max_bet_fraction=0.05,
                max_daily_exposure_fraction=0.20,
            ),
        )
    )

    assert summary.market == "best"
    assert summary.available_games == 2
    assert summary.candidates_considered >= 1
    assert summary.bets_placed >= 1
    assert summary.recommendations[0].market == "moneyline"
    assert summary.recommendations[0].stake_amount > 0


def _create_model_test_environment(tmp_path: Path) -> tuple[str, Path]:
    database_path = tmp_path / "modeling.sqlite"
    artifacts_dir = tmp_path / "artifacts"
    _create_model_test_db(database_path)
    return f"sqlite:///{database_path}", artifacts_dir


def _create_model_test_db(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE teams (
            team_id INTEGER PRIMARY KEY,
            team_key TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL
        );

        CREATE TABLE games (
            game_id INTEGER PRIMARY KEY,
            season INTEGER NOT NULL,
            date TEXT NOT NULL,
            commence_time TEXT,
            team1_id INTEGER NOT NULL,
            team2_id INTEGER NOT NULL,
            result TEXT,
            completed INTEGER NOT NULL DEFAULT 0,
            home_score INTEGER,
            away_score INTEGER,
            source_event_id TEXT UNIQUE
        );

        CREATE TABLE odds_snapshots (
            odds_id INTEGER PRIMARY KEY,
            game_id INTEGER NOT NULL,
            bookmaker_key TEXT NOT NULL,
            bookmaker_title TEXT NOT NULL,
            market_key TEXT NOT NULL,
            captured_at TEXT NOT NULL,
            is_closing_line INTEGER NOT NULL DEFAULT 0,
            team1_price REAL,
            team2_price REAL,
            team1_point REAL,
            team2_point REAL,
            total_points REAL,
            payload TEXT NOT NULL
        );
        """
    )
    connection.executemany(
        "INSERT INTO teams (team_id, team_key, name) VALUES (?, ?, ?)",
        [
            (1, "alpha-aces", "Alpha Aces"),
            (2, "beta-bruins", "Beta Bruins"),
            (3, "gamma-gulls", "Gamma Gulls"),
            (4, "delta-dogs", "Delta Dogs"),
        ],
    )
    connection.executemany(
        """
        INSERT INTO games (
            game_id, season, date, commence_time, team1_id, team2_id,
            result, completed, home_score, away_score, source_event_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                1,
                2025,
                "2024-11-05",
                "2024-11-05T19:00:00+00:00",
                1,
                4,
                "W",
                1,
                80,
                60,
                "evt-1",
            ),
            (
                2,
                2025,
                "2024-11-10",
                "2024-11-10T20:00:00+00:00",
                2,
                3,
                "W",
                1,
                75,
                67,
                "evt-2",
            ),
            (
                3,
                2025,
                "2025-01-15",
                "2025-01-15T19:00:00+00:00",
                3,
                1,
                "L",
                1,
                65,
                79,
                "evt-3",
            ),
            (
                4,
                2025,
                "2025-01-20",
                "2025-01-20T19:00:00+00:00",
                4,
                2,
                "L",
                1,
                64,
                72,
                "evt-4",
            ),
            (
                5,
                2026,
                "2025-11-05",
                "2025-11-05T19:00:00+00:00",
                1,
                3,
                "W",
                1,
                81,
                70,
                "evt-5",
            ),
            (
                6,
                2026,
                "2025-11-10",
                "2025-11-10T20:00:00+00:00",
                2,
                4,
                "W",
                1,
                77,
                68,
                "evt-6",
            ),
            (
                7,
                2026,
                "2026-02-20",
                "2026-02-20T19:00:00+00:00",
                4,
                1,
                "L",
                1,
                69,
                82,
                "evt-7",
            ),
            (
                8,
                2026,
                "2026-02-25",
                "2026-02-25T20:00:00+00:00",
                3,
                2,
                "L",
                1,
                66,
                74,
                "evt-8",
            ),
            (
                9,
                2026,
                "2026-03-09",
                "2026-03-09T19:00:00+00:00",
                1,
                2,
                None,
                0,
                None,
                None,
                "evt-9",
            ),
            (
                10,
                2026,
                "2026-03-10",
                "2026-03-10T20:00:00+00:00",
                4,
                3,
                None,
                0,
                None,
                None,
                "evt-10",
            )
        ],
    )
    connection.executemany(
        """
        INSERT INTO odds_snapshots (
            odds_id, game_id, bookmaker_key, bookmaker_title, market_key,
            captured_at, is_closing_line, team1_price, team2_price,
            team1_point, team2_point, total_points, payload
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        _odds_snapshot_rows(),
    )
    connection.commit()
    connection.close()


def _odds_snapshot_rows() -> list[tuple[object, ...]]:
    rows: list[tuple[object, ...]] = []
    odds_id = 1
    game_lines = [
        (1, "2024-11-05T18:30:00+00:00", -130.0, 110.0, -3.5, 3.5, 146.5),
        (2, "2024-11-10T19:30:00+00:00", -125.0, 105.0, -2.5, 2.5, 142.5),
        (3, "2025-01-15T18:30:00+00:00", 145.0, -165.0, 4.5, -4.5, 144.5),
        (4, "2025-01-20T18:30:00+00:00", 135.0, -155.0, 3.5, -3.5, 141.5),
        (5, "2025-11-05T18:30:00+00:00", -120.0, 100.0, -2.5, 2.5, 145.5),
        (6, "2025-11-10T19:30:00+00:00", -110.0, -110.0, -1.5, 1.5, 143.5),
        (7, "2026-02-20T18:30:00+00:00", 145.0, -165.0, 4.5, -4.5, 147.5),
        (8, "2026-02-25T19:30:00+00:00", 140.0, -160.0, 4.0, -4.0, 144.0),
        (9, "2026-03-09T18:30:00+00:00", -115.0, -105.0, -1.5, 1.5, 145.0),
        (10, "2026-03-10T19:30:00+00:00", 105.0, -125.0, 1.5, -1.5, 140.5),
    ]
    for (
        game_id,
        captured_at,
        home_price,
        away_price,
        home_spread,
        away_spread,
        total,
    ) in game_lines:
        rows.append(
            (
                odds_id,
                game_id,
                "draftkings",
                "DraftKings",
                "h2h",
                captured_at,
                1,
                home_price,
                away_price,
                None,
                None,
                None,
                "{}",
            )
        )
        odds_id += 1
        rows.append(
            (
                odds_id,
                game_id,
                "draftkings",
                "DraftKings",
                "spreads",
                captured_at,
                1,
                -110.0,
                -110.0,
                home_spread,
                away_spread,
                None,
                "{}",
            )
        )
        odds_id += 1
        rows.append(
            (
                odds_id,
                game_id,
                "draftkings",
                "DraftKings",
                "totals",
                captured_at,
                1,
                -110.0,
                -110.0,
                None,
                None,
                total,
                "{}",
            )
        )
        odds_id += 1
    return rows
