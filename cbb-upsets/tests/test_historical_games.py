import sqlite3
from datetime import date

from cbb.ingest import (
    DEFAULT_CBB_SPORT,
    HistoricalIngestOptions,
    HistoricalIngestSummary,
    build_historical_game,
    ingest_historical_games,
)
from tests.support import make_team_catalog


def create_historical_test_db(path) -> None:
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
        self.requested_dates: list[date] = []

    def get_scoreboard(
        self, game_date: date, **_kwargs: object
    ) -> list[dict[str, object]]:
        self.requested_dates.append(game_date)
        return self.payloads.get(game_date, [])


def sample_espn_event(
    *,
    event_id: str,
    event_date: str,
    home_team: str,
    away_team: str,
    home_score: str,
    away_score: str,
    completed: bool = True,
) -> dict[str, object]:
    return {
        "id": event_id,
        "date": event_date,
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


def test_build_historical_game_maps_espn_event() -> None:
    prepared_game = build_historical_game(
        sample_espn_event(
            event_id="401",
            event_date="2025-03-01T18:00Z",
            home_team="Kentucky Wildcats",
            away_team="Auburn Tigers",
            home_score="78",
            away_score="73",
        )
    )

    assert prepared_game.home_team_name == "Kentucky Wildcats"
    assert prepared_game.away_team_name == "Auburn Tigers"
    assert prepared_game.payload["source_event_id"] == "401"
    assert prepared_game.payload["sport_key"] == DEFAULT_CBB_SPORT
    assert prepared_game.payload["season"] == 2025
    assert prepared_game.payload["result"] == "W"
    assert prepared_game.payload["completed"] is True
    assert prepared_game.payload["home_score"] == 78
    assert prepared_game.payload["away_score"] == 73


def test_ingest_historical_games_skips_checkpointed_dates_and_existing_games(
    tmp_path,
) -> None:
    db_path = tmp_path / "historical.sqlite"
    create_historical_test_db(db_path)
    connection = sqlite3.connect(db_path)
    connection.execute(
        """
        INSERT INTO ingest_checkpoints (source_name, sport_key, game_date)
        VALUES (?, ?, ?)
        """,
        ("espn_scoreboard", DEFAULT_CBB_SPORT, "2025-03-01"),
    )
    connection.execute(
        """
        INSERT INTO teams (team_id, team_key, name)
        VALUES (1, 'duke-blue-devils', 'Duke Blue Devils'),
               (2, 'north-carolina-tar-heels', 'North Carolina Tar Heels')
        """
    )
    connection.execute(
        """
        INSERT INTO games (
            game_id, season, date, commence_time, team1_id, team2_id,
            source_event_id, sport_key, sport_title, result, completed,
            home_score, away_score, last_score_update
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            1,
            2025,
            "2025-03-02",
            "2025-03-02T20:00:00+00:00",
            1,
            2,
            "401-existing",
            DEFAULT_CBB_SPORT,
            "NCAAM",
            "W",
            1,
            80,
            70,
            "2025-03-02T22:00:00+00:00",
        ),
    )
    connection.commit()
    connection.close()

    fake_client = FakeEspnClient(
        {
            date(2025, 3, 2): [
                sample_espn_event(
                    event_id="401-existing",
                    event_date="2025-03-02T20:00Z",
                    home_team="Duke Blue Devils",
                    away_team="North Carolina Tar Heels",
                    home_score="80",
                    away_score="70",
                ),
                sample_espn_event(
                    event_id="401-new",
                    event_date="2025-03-02T23:00Z",
                    home_team="Kansas Jayhawks",
                    away_team="Baylor Bears",
                    home_score="72",
                    away_score="68",
                ),
            ]
        }
    )

    summary = ingest_historical_games(
        options=HistoricalIngestOptions(
            start_date=date(2025, 3, 1),
            end_date=date(2025, 3, 2),
        ),
        database_url=f"sqlite+pysqlite:///{db_path}",
        client=fake_client,
        team_catalog=make_team_catalog(
            [
                ("Duke", "Duke Blue Devils", None),
                ("North Carolina", "North Carolina Tar Heels", None),
                ("Kansas", "Kansas Jayhawks", None),
                ("Baylor", "Baylor Bears", None),
            ]
        ),
    )

    assert summary == HistoricalIngestSummary(
        sport=DEFAULT_CBB_SPORT,
        start_date="2025-03-01",
        end_date="2025-03-02",
        dates_requested=1,
        dates_skipped=1,
        dates_completed=1,
        teams_seen=2,
        games_seen=2,
        games_inserted=1,
        games_skipped=0,
    )
    assert fake_client.requested_dates == [date(2025, 3, 2)]

    connection = sqlite3.connect(db_path)
    games = connection.execute(
        """
        SELECT source_event_id, home_score, away_score
        FROM games
        ORDER BY source_event_id
        """
    ).fetchall()
    checkpoints = connection.execute(
        """
        SELECT game_date
        FROM ingest_checkpoints
        ORDER BY game_date
        """
    ).fetchall()
    connection.close()

    assert games == [("401-existing", 80, 70), ("401-new", 72, 68)]
    assert checkpoints == [("2025-03-01",), ("2025-03-02",)]


def test_ingest_historical_games_force_refresh_updates_existing_source_game(
    tmp_path,
) -> None:
    db_path = tmp_path / "historical_refresh.sqlite"
    create_historical_test_db(db_path)
    connection = sqlite3.connect(db_path)
    connection.execute(
        """
        INSERT INTO teams (team_id, team_key, name)
        VALUES (1, 'kentucky-wildcats', 'Kentucky Wildcats'),
               (2, 'auburn-tigers', 'Auburn Tigers')
        """
    )
    connection.execute(
        """
        INSERT INTO games (
            game_id, season, date, commence_time, team1_id, team2_id,
            source_event_id, sport_key, sport_title, result, completed,
            home_score, away_score, last_score_update
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            1,
            2025,
            "2025-03-03",
            "2025-03-03T20:00:00+00:00",
            1,
            2,
            "401-refresh",
            DEFAULT_CBB_SPORT,
            "NCAAM",
            None,
            0,
            0,
            0,
            None,
        ),
    )
    connection.commit()
    connection.close()

    fake_client = FakeEspnClient(
        {
            date(2025, 3, 3): [
                sample_espn_event(
                    event_id="401-refresh",
                    event_date="2025-03-03T20:00Z",
                    home_team="Kentucky Wildcats",
                    away_team="Auburn Tigers",
                    home_score="78",
                    away_score="73",
                    completed=True,
                )
            ]
        }
    )

    summary = ingest_historical_games(
        options=HistoricalIngestOptions(
            start_date=date(2025, 3, 3),
            end_date=date(2025, 3, 3),
            force_refresh=True,
        ),
        database_url=f"sqlite+pysqlite:///{db_path}",
        client=fake_client,
        team_catalog=make_team_catalog(
            [
                ("Kentucky", "Kentucky Wildcats", None),
                ("Auburn", "Auburn Tigers", None),
            ]
        ),
    )

    assert summary.games_seen == 1
    assert summary.games_inserted == 1
    assert summary.games_skipped == 0

    connection = sqlite3.connect(db_path)
    game = connection.execute(
        """
        SELECT completed, home_score, away_score, result
        FROM games
        WHERE source_event_id = '401-refresh'
        """
    ).fetchone()
    connection.close()

    assert game == (1, 78, 73, "W")
