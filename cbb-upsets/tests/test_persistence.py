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
            neutral_site INTEGER,
            conference_competition INTEGER,
            season_type INTEGER,
            season_type_slug TEXT,
            tournament_id TEXT,
            event_note_headline TEXT,
            venue_id TEXT,
            venue_name TEXT,
            venue_city TEXT,
            venue_state TEXT,
            venue_indoor INTEGER,
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
    neutral_site: bool = False,
    conference_competition: bool = False,
    season_type: int = 2,
    season_type_slug: str = "regular-season",
    tournament_id: str | None = None,
    event_note_headline: str | None = None,
    venue_id: str | None = None,
    venue_name: str | None = None,
    venue_city: str | None = None,
    venue_state: str | None = None,
    venue_indoor: bool | None = None,
) -> dict[str, object]:
    notes: list[dict[str, str]] = []
    if event_note_headline is not None:
        notes.append({"headline": event_note_headline})

    competition: dict[str, object] = {
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
        "neutralSite": neutral_site,
        "conferenceCompetition": conference_competition,
        "notes": notes,
    }
    if tournament_id is not None:
        competition["tournamentId"] = tournament_id
    if (
        venue_id is not None
        or venue_name is not None
        or venue_city is not None
        or venue_state is not None
        or venue_indoor is not None
    ):
        venue: dict[str, object] = {}
        if venue_id is not None:
            venue["id"] = venue_id
        if venue_name is not None:
            venue["fullName"] = venue_name
        address: dict[str, str] = {}
        if venue_city is not None:
            address["city"] = venue_city
        if venue_state is not None:
            address["state"] = venue_state
        if address:
            venue["address"] = address
        if venue_indoor is not None:
            venue["indoor"] = venue_indoor
        competition["venue"] = venue

    return {
        "id": event_id,
        "date": "2026-03-07T19:00:00Z",
        "season": {"year": 2026, "type": season_type, "slug": season_type_slug},
        "status": {"type": {"completed": completed}},
        "competitions": [competition],
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
                        neutral_site=True,
                        season_type=3,
                        season_type_slug="post-season",
                        tournament_id="555",
                        event_note_headline="ACC Tournament - Final",
                        venue_id="321",
                        venue_name="Spectrum Center",
                        venue_city="Charlotte",
                        venue_state="NC",
                        venue_indoor=True,
                    )
                ]
            }
        ),
        team_catalog=team_catalog,
    )

    connection = sqlite3.connect(db_path)
    rows = connection.execute(
        """
        SELECT
            source_event_id,
            neutral_site,
            season_type,
            season_type_slug,
            tournament_id,
            event_note_headline,
            venue_name
        FROM games
        ORDER BY game_id
        """
    ).fetchall()
    connection.close()

    assert rows == [
        (
            "401820788",
            1,
            3,
            "post-season",
            "555",
            "ACC Tournament - Final",
            "Spectrum Center",
        )
    ]


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
