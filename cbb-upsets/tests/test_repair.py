import sqlite3

from cbb.repair import RepairSummary, repair_database
from tests.support import make_team_catalog


def create_repair_test_db(path) -> None:
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
    connection.commit()
    connection.close()


def test_repair_database_merges_alias_teams_and_drops_non_d1_games(tmp_path) -> None:
    db_path = tmp_path / "repair.sqlite"
    create_repair_test_db(db_path)

    connection = sqlite3.connect(db_path)
    connection.executemany(
        "INSERT INTO teams (team_id, team_key, name) VALUES (?, ?, ?)",
        [
            (1, "michigan-st-spartans", "Michigan St Spartans"),
            (2, "indiana-hoosiers", "Indiana Hoosiers"),
            (3, "michigan-state-spartans", "Michigan State Spartans"),
            (4, "pacific-tigers", "Pacific Tigers"),
            (5, "blackburn-beavers", "Blackburn Beavers"),
            (6, "seattle-redhawks", "Seattle Redhawks"),
        ],
    )
    connection.executemany(
        """
        INSERT INTO games (
            game_id,
            season,
            date,
            commence_time,
            team1_id,
            team2_id,
            source_event_id,
            sport_key,
            sport_title,
            result,
            completed,
            home_score,
            away_score,
            last_score_update
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                10,
                2025,
                "2025-03-05",
                "2025-03-05T19:00:00+00:00",
                1,
                2,
                "espn-a",
                "basketball_ncaab",
                "NCAAM",
                "W",
                1,
                80,
                70,
                "2025-03-05T21:00:00+00:00",
            ),
            (
                11,
                2025,
                "2025-03-05",
                "2025-03-05T19:00:00+00:00",
                3,
                2,
                None,
                "basketball_ncaab",
                "NCAAM",
                "W",
                1,
                80,
                70,
                "2025-03-05T21:05:00+00:00",
            ),
            (
                12,
                2025,
                "2025-11-12",
                "2025-11-12T01:00:00+00:00",
                4,
                5,
                "espn-b",
                "basketball_ncaab",
                "NCAAM",
                None,
                0,
                None,
                None,
                None,
            ),
        ],
    )
    connection.executemany(
        """
        INSERT INTO odds_snapshots (
            game_id,
            bookmaker_key,
            bookmaker_title,
            market_key,
            captured_at,
            is_closing_line,
            team1_price,
            team2_price,
            payload
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                10,
                "draftkings",
                "DraftKings",
                "h2h",
                "2025-03-05T18:55:00+00:00",
                0,
                -120,
                100,
                '{"key":"h2h"}',
            ),
            (
                11,
                "fanduel",
                "FanDuel",
                "h2h",
                "2025-03-05T18:57:00+00:00",
                1,
                -118,
                102,
                '{"key":"h2h"}',
            ),
            (
                12,
                "draftkings",
                "DraftKings",
                "h2h",
                "2025-11-12T00:55:00+00:00",
                0,
                -200,
                160,
                '{"key":"h2h"}',
            ),
        ],
    )
    connection.commit()
    connection.close()

    summary = repair_database(
        database_url=f"sqlite+pysqlite:///{db_path}",
        catalog=make_team_catalog(
            [
                ("Michigan State", "Michigan State Spartans", None),
                ("Indiana", "Indiana Hoosiers", None),
                ("Pacific", "Pacific Tigers", None),
                ("Seattle U", "Seattle U Redhawks", None),
            ]
        ),
    )

    assert summary == RepairSummary(
        canonical_teams=4,
        teams_resolved=2,
        teams_unresolved=1,
        teams_deleted=3,
        games_deleted=1,
        games_merged=1,
        odds_snapshots_merged=1,
    )

    connection = sqlite3.connect(db_path)
    teams = connection.execute("SELECT name FROM teams ORDER BY name").fetchall()
    games = connection.execute(
        "SELECT game_id, team1_id, team2_id, source_event_id "
        "FROM games ORDER BY game_id"
    ).fetchall()
    snapshots = connection.execute(
        "SELECT game_id, bookmaker_key, is_closing_line "
        "FROM odds_snapshots ORDER BY bookmaker_key"
    ).fetchall()
    connection.close()

    assert teams == [
        ("Indiana Hoosiers",),
        ("Michigan State Spartans",),
        ("Pacific Tigers",),
        ("Seattle U Redhawks",),
    ]
    assert games == [(10, 3, 2, "espn-a")]
    assert snapshots == [(10, "draftkings", 0), (10, "fanduel", 1)]
