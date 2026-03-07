import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from cbb.cli import app
from cbb.config import get_settings
from cbb.db import get_database_summary


runner = CliRunner()


def create_summary_test_db(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE teams (
            team_id INTEGER PRIMARY KEY,
            team_key TEXT NOT NULL UNIQUE,
            ncaa_team_code TEXT UNIQUE,
            name TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE games (
            game_id INTEGER PRIMARY KEY,
            season INTEGER NOT NULL,
            date TEXT NOT NULL,
            commence_time TEXT,
            team1_id INTEGER NOT NULL,
            team2_id INTEGER NOT NULL,
            round TEXT,
            ncaa_game_code TEXT UNIQUE,
            source_event_id TEXT UNIQUE,
            sport_key TEXT,
            sport_title TEXT,
            result TEXT,
            completed INTEGER NOT NULL DEFAULT 0,
            home_score INTEGER,
            away_score INTEGER,
            last_score_update TEXT,
            UNIQUE (season, date, team1_id, team2_id)
        );

        CREATE TABLE odds_snapshots (
            odds_id INTEGER PRIMARY KEY,
            game_id INTEGER NOT NULL,
            bookmaker_key TEXT NOT NULL,
            bookmaker_title TEXT NOT NULL,
            market_key TEXT NOT NULL,
            captured_at TEXT NOT NULL,
            team1_price REAL,
            team2_price REAL,
            team1_point REAL,
            team2_point REAL,
            over_price REAL,
            under_price REAL,
            total_points REAL,
            payload TEXT NOT NULL,
            UNIQUE(game_id, bookmaker_key, market_key, captured_at)
        );
        """
    )
    connection.executemany(
        "INSERT INTO teams (team_id, team_key, name) VALUES (?, ?, ?)",
        [
            (1, "duke-blue-devils", "Duke Blue Devils"),
            (2, "north-carolina-tar-heels", "North Carolina Tar Heels"),
            (3, "baylor-bears", "Baylor Bears"),
            (4, "kansas-jayhawks", "Kansas Jayhawks"),
        ],
    )
    connection.executemany(
        """
        INSERT INTO games (
            game_id, season, date, commence_time, team1_id, team2_id,
            source_event_id, sport_key, sport_title, result, completed,
            home_score, away_score
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                1,
                2026,
                "2026-03-06",
                "2026-03-06T20:00:00+00:00",
                1,
                2,
                "evt-1",
                "basketball_ncaab",
                "NCAAB",
                "W",
                1,
                81,
                75,
            ),
            (
                2,
                2026,
                "2026-03-07",
                "2026-03-07T20:00:00+00:00",
                3,
                4,
                "evt-2",
                "basketball_ncaab",
                "NCAAB",
                None,
                0,
                None,
                None,
            ),
        ],
    )
    connection.execute(
        """
        INSERT INTO odds_snapshots (
            game_id, bookmaker_key, bookmaker_title, market_key, captured_at,
            team1_price, team2_price, total_points, payload
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            2,
            "fanduel",
            "FanDuel",
            "h2h",
            "2026-03-07T19:55:00+00:00",
            -140,
            120,
            151.5,
            "{}",
        ),
    )
    connection.commit()
    connection.close()


def test_get_database_summary_returns_expected_counts_and_samples(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "summary.sqlite"
    create_summary_test_db(db_path)

    summary = get_database_summary(f"sqlite+pysqlite:///{db_path}")

    assert summary.teams == 4
    assert summary.games == 2
    assert summary.completed_games == 1
    assert summary.upcoming_games == 1
    assert summary.odds_snapshots == 1
    assert summary.first_game_time == "2026-03-06T20:00:00+00:00"
    assert summary.last_game_time == "2026-03-07T20:00:00+00:00"
    assert summary.completed_samples[0].home_team == "Duke Blue Devils"
    assert summary.upcoming_samples[0].away_team == "Kansas Jayhawks"
    assert summary.odds_samples[0].bookmaker_key == "fanduel"


def test_db_summary_command_prints_loaded_data(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "summary.sqlite"
    create_summary_test_db(db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db_path}")
    get_settings.cache_clear()

    result = runner.invoke(app, ["db-summary"])

    assert result.exit_code == 0
    assert "Counts" in result.stdout
    assert "teams: 4" in result.stdout
    assert "Duke Blue Devils vs North Carolina Tar Heels" in result.stdout
    assert "fanduel/h2h" in result.stdout
