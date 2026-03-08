import sqlite3
from datetime import date

from cbb.ingest import (
    ApiQuota,
    HistoricalIngestOptions,
    OddsPersistenceInput,
    ingest_historical_games,
    persist_odds_data,
)
from tests.support import make_team_catalog


def create_persistence_test_db(path) -> None:
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

        CREATE TABLE ingest_checkpoints (
            ingest_checkpoint_id INTEGER PRIMARY KEY,
            source_name TEXT NOT NULL,
            sport_key TEXT NOT NULL,
            game_date TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(source_name, sport_key, game_date)
        );
        """
    )
    connection.commit()
    connection.close()


class FakeEspnClient:
    def __init__(self, payloads: dict[date, list[dict[str, object]]]) -> None:
        self.payloads = payloads

    def get_scoreboard(
        self, game_date: date, **_kwargs: object
    ) -> list[dict[str, object]]:
        return self.payloads.get(game_date, [])


def sample_espn_event(
    *,
    event_id: str,
    home_team: str,
    away_team: str,
    home_score: str,
    away_score: str,
    completed: bool = True,
) -> dict[str, object]:
    return {
        "id": event_id,
        "date": "2026-03-07T19:00:00Z",
        "status": {"type": {"completed": completed}},
        "competitions": [
            {
                "status": {"type": {"completed": completed}},
                "competitors": [
                    {
                        "homeAway": "home",
                        "score": home_score,
                        "team": {"displayName": home_team},
                    },
                    {
                        "homeAway": "away",
                        "score": away_score,
                        "team": {"displayName": away_team},
                    },
                ],
            }
        ],
    }


def sample_odds_event(event_id: str) -> dict[str, object]:
    return {
        "id": event_id,
        "sport_key": "basketball_ncaab",
        "sport_title": "NCAAB",
        "commence_time": "2026-03-07T19:00:00Z",
        "home_team": "Duke Blue Devils",
        "away_team": "North Carolina Tar Heels",
        "bookmakers": [
            {
                "key": "draftkings",
                "title": "DraftKings",
                "last_update": "2026-03-07T18:55:00Z",
                "markets": [
                    {
                        "key": "h2h",
                        "last_update": "2026-03-07T18:55:00Z",
                        "outcomes": [
                            {"name": "Duke Blue Devils", "price": -140},
                            {"name": "North Carolina Tar Heels", "price": 120},
                        ],
                    }
                ],
            }
        ],
    }


def sample_score_event(event_id: str) -> dict[str, object]:
    return {
        "id": event_id,
        "sport_key": "basketball_ncaab",
        "sport_title": "NCAAB",
        "commence_time": "2026-03-07T19:00:00Z",
        "home_team": "Duke Blue Devils",
        "away_team": "North Carolina Tar Heels",
        "completed": True,
        "scores": [
            {"name": "Duke Blue Devils", "score": "81"},
            {"name": "North Carolina Tar Heels", "score": "77"},
        ],
        "last_update": "2026-03-07T21:00:00Z",
    }


def sample_bad_score_event(event_id: str) -> dict[str, object]:
    return {
        "id": event_id,
        "sport_key": "basketball_ncaab",
        "sport_title": "NCAAB",
        "commence_time": "2026-03-07T19:00:00Z",
        "home_team": "Duke Blue Devils",
        "away_team": "North Carolina Tar Heels",
        "completed": True,
        "scores": [
            {"name": "Duke Blue Devils", "score": "81"},
            {"name": "North Carolina Tar Heels", "score": "20"},
        ],
        "last_update": "2026-03-07T21:00:00Z",
    }


def test_historical_ingest_replaces_synthetic_source_event_id(tmp_path) -> None:
    db_path = tmp_path / "replace_source_id.sqlite"
    create_persistence_test_db(db_path)
    team_catalog = make_team_catalog(
        [
            ("Duke", "Duke Blue Devils", None),
            ("North Carolina", "North Carolina Tar Heels", None),
        ]
    )

    persist_odds_data(
        payload=OddsPersistenceInput(
            sport="basketball_ncaab",
            odds_events=[sample_odds_event("synthetic-evt")],
            score_events=[sample_score_event("synthetic-evt")],
            odds_quota=ApiQuota(None, None, None),
            scores_quota=ApiQuota(None, None, None),
        ),
        database_url=f"sqlite+pysqlite:///{db_path}",
        team_catalog=team_catalog,
    )

    ingest_historical_games(
        options=HistoricalIngestOptions(
            start_date=date(2026, 3, 7),
            end_date=date(2026, 3, 7),
            force_refresh=True,
        ),
        database_url=f"sqlite+pysqlite:///{db_path}",
        client=FakeEspnClient(
            {
                date(2026, 3, 7): [
                    sample_espn_event(
                        event_id="401820788",
                        home_team="Duke Blue Devils",
                        away_team="North Carolina Tar Heels",
                        home_score="81",
                        away_score="77",
                    )
                ]
            }
        ),
        team_catalog=team_catalog,
    )

    connection = sqlite3.connect(db_path)
    rows = connection.execute(
        "SELECT source_event_id FROM games ORDER BY game_id"
    ).fetchall()
    connection.close()

    assert rows == [("401820788",)]


def test_odds_ingest_preserves_existing_espn_source_event_id(tmp_path) -> None:
    db_path = tmp_path / "preserve_source_id.sqlite"
    create_persistence_test_db(db_path)
    team_catalog = make_team_catalog(
        [
            ("Duke", "Duke Blue Devils", None),
            ("North Carolina", "North Carolina Tar Heels", None),
        ]
    )

    ingest_historical_games(
        options=HistoricalIngestOptions(
            start_date=date(2026, 3, 7),
            end_date=date(2026, 3, 7),
            force_refresh=True,
        ),
        database_url=f"sqlite+pysqlite:///{db_path}",
        client=FakeEspnClient(
            {
                date(2026, 3, 7): [
                    sample_espn_event(
                        event_id="401820788",
                        home_team="Duke Blue Devils",
                        away_team="North Carolina Tar Heels",
                        home_score="81",
                        away_score="77",
                    )
                ]
            }
        ),
        team_catalog=team_catalog,
    )

    persist_odds_data(
        payload=OddsPersistenceInput(
            sport="basketball_ncaab",
            odds_events=[sample_odds_event("synthetic-evt")],
            score_events=[sample_score_event("synthetic-evt")],
            odds_quota=ApiQuota(None, None, None),
            scores_quota=ApiQuota(None, None, None),
        ),
        database_url=f"sqlite+pysqlite:///{db_path}",
        team_catalog=team_catalog,
    )

    connection = sqlite3.connect(db_path)
    rows = connection.execute(
        "SELECT source_event_id FROM games ORDER BY game_id"
    ).fetchall()
    connection.close()

    assert rows == [("401820788",)]


def test_odds_ingest_preserves_existing_completed_scores(tmp_path) -> None:
    db_path = tmp_path / "preserve_completed_scores.sqlite"
    create_persistence_test_db(db_path)
    team_catalog = make_team_catalog(
        [
            ("Duke", "Duke Blue Devils", None),
            ("North Carolina", "North Carolina Tar Heels", None),
        ]
    )

    ingest_historical_games(
        options=HistoricalIngestOptions(
            start_date=date(2026, 3, 7),
            end_date=date(2026, 3, 7),
            force_refresh=True,
        ),
        database_url=f"sqlite+pysqlite:///{db_path}",
        client=FakeEspnClient(
            {
                date(2026, 3, 7): [
                    sample_espn_event(
                        event_id="401820788",
                        home_team="Duke Blue Devils",
                        away_team="North Carolina Tar Heels",
                        home_score="81",
                        away_score="77",
                    )
                ]
            }
        ),
        team_catalog=team_catalog,
    )

    persist_odds_data(
        payload=OddsPersistenceInput(
            sport="basketball_ncaab",
            odds_events=[sample_odds_event("synthetic-evt")],
            score_events=[sample_bad_score_event("synthetic-evt")],
            odds_quota=ApiQuota(None, None, None),
            scores_quota=ApiQuota(None, None, None),
        ),
        database_url=f"sqlite+pysqlite:///{db_path}",
        team_catalog=team_catalog,
    )

    connection = sqlite3.connect(db_path)
    rows = connection.execute(
        "SELECT source_event_id, home_score, away_score, completed FROM games"
    ).fetchall()
    connection.close()

    assert rows == [("401820788", 81, 77, 1)]


def test_historical_ingest_replaces_old_espn_event_id_on_reschedule(tmp_path) -> None:
    db_path = tmp_path / "replace_old_espn_source_id.sqlite"
    create_persistence_test_db(db_path)
    team_catalog = make_team_catalog(
        [
            ("Prairie View A&M", "Prairie View A&M Panthers", None),
            ("Alabama A&M", "Alabama A&M Bulldogs", None),
        ]
    )

    ingest_historical_games(
        options=HistoricalIngestOptions(
            start_date=date(2026, 1, 26),
            end_date=date(2026, 1, 26),
            force_refresh=True,
        ),
        database_url=f"sqlite+pysqlite:///{db_path}",
        client=FakeEspnClient(
            {
                date(2026, 1, 26): [
                    sample_espn_event(
                        event_id="401827053",
                        home_team="Prairie View A&M Panthers",
                        away_team="Alabama A&M Bulldogs",
                        home_score="0",
                        away_score="0",
                        completed=False,
                    )
                ]
            }
        ),
        team_catalog=team_catalog,
    )

    ingest_historical_games(
        options=HistoricalIngestOptions(
            start_date=date(2026, 1, 26),
            end_date=date(2026, 1, 26),
            force_refresh=True,
        ),
        database_url=f"sqlite+pysqlite:///{db_path}",
        client=FakeEspnClient(
            {
                date(2026, 1, 26): [
                    sample_espn_event(
                        event_id="401858319",
                        home_team="Prairie View A&M Panthers",
                        away_team="Alabama A&M Bulldogs",
                        home_score="60",
                        away_score="80",
                    )
                ]
            }
        ),
        team_catalog=team_catalog,
    )

    connection = sqlite3.connect(db_path)
    rows = connection.execute(
        "SELECT source_event_id, completed, home_score, away_score FROM games"
    ).fetchall()
    connection.close()

    assert rows == [("401858319", 1, 60, 80)]
