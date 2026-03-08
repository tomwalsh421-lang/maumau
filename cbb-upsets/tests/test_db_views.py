import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from cbb.db import TeamView, get_team_view, get_upcoming_games


def create_view_test_db(path: Path) -> None:
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

        CREATE TABLE team_aliases (
            team_alias_id INTEGER PRIMARY KEY,
            team_id INTEGER NOT NULL,
            alias_key TEXT NOT NULL UNIQUE,
            alias_name TEXT NOT NULL,
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
            is_closing_line INTEGER NOT NULL DEFAULT 0,
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
            (3, "kansas-jayhawks", "Kansas Jayhawks"),
            (4, "baylor-bears", "Baylor Bears"),
            (5, "michigan-state-spartans", "Michigan State Spartans"),
            (6, "indiana-hoosiers", "Indiana Hoosiers"),
        ],
    )
    connection.executemany(
        """
        INSERT INTO team_aliases (team_alias_id, team_id, alias_key, alias_name)
        VALUES (?, ?, ?, ?)
        """,
        [
            (1, 1, "duke", "Duke"),
            (2, 5, "michigan-st-spartans", "Michigan St Spartans"),
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
                "2026-03-07",
                "2026-03-07T23:30:00+00:00",
                1,
                2,
                "evt-1",
                "basketball_ncaab",
                "NCAAB",
                "W",
                1,
                76,
                61,
            ),
            (
                2,
                2026,
                "2026-03-05",
                "2026-03-05T20:00:00+00:00",
                3,
                1,
                "evt-2",
                "basketball_ncaab",
                "NCAAB",
                "L",
                1,
                70,
                74,
            ),
            (
                3,
                2026,
                "2026-03-03",
                "2026-03-03T21:00:00+00:00",
                1,
                4,
                "evt-3",
                "basketball_ncaab",
                "NCAAB",
                "W",
                1,
                88,
                73,
            ),
            (
                4,
                2026,
                "2026-03-01",
                "2026-03-01T19:00:00+00:00",
                6,
                1,
                "evt-4",
                "basketball_ncaab",
                "NCAAB",
                "W",
                1,
                80,
                77,
            ),
            (
                5,
                2026,
                "2026-02-27",
                "2026-02-27T19:30:00+00:00",
                1,
                5,
                "evt-5",
                "basketball_ncaab",
                "NCAAB",
                "L",
                1,
                65,
                70,
            ),
            (
                6,
                2026,
                "2026-02-24",
                "2026-02-24T20:00:00+00:00",
                2,
                1,
                "evt-6",
                "basketball_ncaab",
                "NCAAB",
                "L",
                1,
                60,
                66,
            ),
            (
                7,
                2026,
                "2026-03-08",
                "2026-03-08T18:00:00+00:00",
                1,
                4,
                "evt-7",
                "basketball_ncaab",
                "NCAAB",
                None,
                0,
                54,
                49,
            ),
            (
                8,
                2026,
                "2026-03-08",
                "2026-03-08T21:00:00+00:00",
                3,
                2,
                "evt-8",
                "basketball_ncaab",
                "NCAAB",
                None,
                0,
                None,
                None,
            ),
            (
                11,
                2026,
                "2026-03-08",
                "2026-03-08T19:00:00+00:00",
                5,
                6,
                "evt-11",
                "basketball_ncaab",
                "NCAAB",
                None,
                0,
                44,
                40,
            ),
            (
                9,
                2026,
                "2026-03-07",
                "2026-03-07T12:00:00+00:00",
                5,
                6,
                "evt-9",
                "basketball_ncaab",
                "NCAAB",
                None,
                0,
                None,
                None,
            ),
            (
                10,
                2026,
                "2026-03-20",
                "2026-03-20T18:00:00+00:00",
                5,
                2,
                "evt-10",
                "basketball_ncaab",
                "NCAAB",
                None,
                0,
                None,
                None,
            ),
        ],
    )
    connection.executemany(
        """
        INSERT INTO odds_snapshots (
            odds_id,
            game_id,
            bookmaker_key,
            bookmaker_title,
            market_key,
            captured_at,
            is_closing_line,
            team1_price,
            team2_price,
            payload
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                1,
                7,
                "draftkings",
                "DraftKings",
                "h2h",
                "2026-03-08T17:55:00+00:00",
                0,
                -140.0,
                120.0,
                "{}",
            ),
            (
                2,
                8,
                "draftkings",
                "DraftKings",
                "h2h",
                "2026-03-08T20:55:00+00:00",
                0,
                -125.0,
                105.0,
                "{}",
            ),
            (
                3,
                11,
                "fanduel",
                "FanDuel",
                "h2h",
                "2026-03-08T18:50:00+00:00",
                0,
                -110.0,
                -110.0,
                "{}",
            ),
        ],
    )
    connection.commit()
    connection.close()


def test_get_team_view_returns_recent_results_for_alias_match(tmp_path: Path) -> None:
    db_path = tmp_path / "views.sqlite"
    create_view_test_db(db_path)
    current_time = datetime(2026, 3, 8, 20, 0, tzinfo=UTC)

    view = get_team_view("Duke", f"sqlite+pysqlite:///{db_path}", now=current_time)

    assert isinstance(view, TeamView)
    assert view.team_name == "Duke Blue Devils"
    assert view.scheduled_games[0].home_team == "Duke Blue Devils"
    assert view.scheduled_games[0].status == "in_progress"
    assert view.scheduled_games[0].home_score == 54
    assert view.scheduled_games[0].away_score == 49
    assert view.scheduled_games[0].home_pregame_moneyline == -140.0
    assert view.scheduled_games[0].away_pregame_moneyline == 120.0
    assert len(view.recent_results) == 5
    assert view.recent_results[0].opponent_name == "North Carolina Tar Heels"
    assert view.recent_results[0].result == "W"
    assert view.recent_results[1].venue_label == "at"
    assert view.recent_results[1].result == "W"
    assert view.suggestions == []


def test_get_team_view_returns_suggestions_for_non_exact_name(tmp_path: Path) -> None:
    db_path = tmp_path / "views.sqlite"
    create_view_test_db(db_path)

    view = get_team_view("Duk Blu", f"sqlite+pysqlite:///{db_path}")

    assert view.team_name is None
    assert view.scheduled_games == []
    assert view.recent_results == []
    assert "Duke Blue Devils" in view.suggestions


def test_get_upcoming_games_returns_current_window_only(tmp_path: Path) -> None:
    db_path = tmp_path / "views.sqlite"
    create_view_test_db(db_path)
    current_time = datetime(2026, 3, 8, 20, 0, tzinfo=UTC)

    games = get_upcoming_games(
        f"sqlite+pysqlite:///{db_path}",
        limit=1,
        now=current_time,
    )

    assert [(game.home_team, game.away_team, game.status) for game in games] == [
        ("Duke Blue Devils", "Baylor Bears", "in_progress"),
        ("Michigan State Spartans", "Indiana Hoosiers", "in_progress"),
        ("Kansas Jayhawks", "North Carolina Tar Heels", "upcoming"),
    ]
    assert games[0].home_score == 54
    assert games[0].away_score == 49
    assert games[0].home_pregame_moneyline == -140.0
    assert games[0].away_pregame_moneyline == 120.0
    assert games[1].home_pregame_moneyline == -110.0
    assert games[2].home_pregame_moneyline == -125.0
