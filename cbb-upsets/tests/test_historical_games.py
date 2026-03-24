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
        "date": event_date,
        "season": {"year": 2025, "type": season_type, "slug": season_type_slug},
        "status": {"type": {"completed": completed}},
        "competitions": [competition],
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
            neutral_site=True,
            season_type=3,
            season_type_slug="post-season",
            tournament_id="401",
            event_note_headline=(
                "Men's Basketball Championship - South Region - 1st Round"
            ),
            venue_id="3373",
            venue_name="INTRUST Bank Arena",
            venue_city="Wichita",
            venue_state="KS",
            venue_indoor=True,
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
    assert prepared_game.payload["neutral_site"] is True
    assert prepared_game.payload["conference_competition"] is False
    assert prepared_game.payload["season_type"] == 3
    assert prepared_game.payload["season_type_slug"] == "post-season"
    assert prepared_game.payload["tournament_id"] == "401"
    assert (
        prepared_game.payload["event_note_headline"]
        == "Men's Basketball Championship - South Region - 1st Round"
    )
    assert prepared_game.payload["venue_id"] == "3373"
    assert prepared_game.payload["venue_name"] == "INTRUST Bank Arena"
    assert prepared_game.payload["venue_city"] == "Wichita"
    assert prepared_game.payload["venue_state"] == "KS"
    assert prepared_game.payload["venue_indoor"] is True


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
                    neutral_site=True,
                    season_type=3,
                    season_type_slug="post-season",
                    tournament_id="847",
                    event_note_headline="SEC Tournament - Quarterfinal",
                    venue_id="999",
                    venue_name="Bridgestone Arena",
                    venue_city="Nashville",
                    venue_state="TN",
                    venue_indoor=True,
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
        SELECT
            completed,
            home_score,
            away_score,
            result,
            neutral_site,
            season_type,
            season_type_slug,
            tournament_id,
            event_note_headline,
            venue_name,
            venue_city,
            venue_state,
            venue_indoor
        FROM games
        WHERE source_event_id = '401-refresh'
        """
    ).fetchone()
    connection.close()

    assert game == (
        1,
        78,
        73,
        "W",
        1,
        3,
        "post-season",
        "847",
        "SEC Tournament - Quarterfinal",
        "Bridgestone Arena",
        "Nashville",
        "TN",
        1,
    )


def test_ingest_historical_games_uses_stored_team_catalog_before_espn_directory(
    tmp_path,
) -> None:
    db_path = tmp_path / "historical_catalog_fallback.sqlite"
    create_historical_test_db(db_path)
    connection = sqlite3.connect(db_path)
    connection.execute("ALTER TABLE teams ADD COLUMN conference_key TEXT")
    connection.execute("ALTER TABLE teams ADD COLUMN conference_name TEXT")
    connection.execute(
        """
        CREATE TABLE team_aliases (
            team_alias_id INTEGER PRIMARY KEY,
            team_id INTEGER NOT NULL,
            alias_key TEXT NOT NULL UNIQUE,
            alias_name TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        INSERT INTO teams (
            team_id, team_key, name, conference_key, conference_name
        ) VALUES
            (1, 'duke-blue-devils', 'Duke Blue Devils', 'acc', 'ACC'),
            (2, 'north-carolina-tar-heels', 'North Carolina Tar Heels', 'acc', 'ACC')
        """
    )
    connection.execute(
        """
        INSERT INTO team_aliases (team_id, alias_key, alias_name)
        VALUES
            (1, 'duke', 'Duke'),
            (2, 'north-carolina', 'North Carolina')
        """
    )
    connection.commit()
    connection.close()

    class CatalogFallbackClient(FakeEspnClient):
        def get_teams(self, **_kwargs: object) -> list[dict[str, object]]:
            raise AssertionError("historical ingest should reuse the stored catalog")

    fake_client = CatalogFallbackClient(
        {
            date(2025, 3, 4): [
                sample_espn_event(
                    event_id="401-fallback",
                    event_date="2025-03-04T20:00Z",
                    home_team="Duke Blue Devils",
                    away_team="North Carolina Tar Heels",
                    home_score="81",
                    away_score="75",
                )
            ]
        }
    )

    summary = ingest_historical_games(
        options=HistoricalIngestOptions(
            start_date=date(2025, 3, 4),
            end_date=date(2025, 3, 4),
        ),
        database_url=f"sqlite+pysqlite:///{db_path}",
        client=fake_client,
    )

    assert summary.games_seen == 1
    assert summary.games_inserted == 1
    assert fake_client.requested_dates == [date(2025, 3, 4)]

    connection = sqlite3.connect(db_path)
    stored_game = connection.execute(
        """
        SELECT source_event_id, team1_id, team2_id, home_score, away_score
        FROM games
        WHERE source_event_id = '401-fallback'
        """
    ).fetchone()
    connection.close()

    assert stored_game == ("401-fallback", 1, 2, 81, 75)
