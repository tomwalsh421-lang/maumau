import sqlite3
from datetime import UTC, date, datetime

from cbb.ingest import (
    ApiQuota,
    ClosingOddsIngestOptions,
    ClosingOddsIngestSummary,
    TeamPairCandidate,
    build_team_aliases,
    ingest_closing_odds,
    match_team_pair,
)
from cbb.ingest.models import HistoricalOddsResponse


def create_closing_lines_test_db(path) -> None:
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

        CREATE TABLE historical_odds_checkpoints (
            historical_odds_checkpoint_id INTEGER PRIMARY KEY,
            source_name TEXT NOT NULL,
            sport_key TEXT NOT NULL,
            market_key TEXT NOT NULL,
            filters_key TEXT NOT NULL,
            snapshot_time TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(source_name, sport_key, market_key, filters_key, snapshot_time)
        );
        """
    )
    connection.commit()
    connection.close()


class FakeHistoricalOddsClient:
    def __init__(self, payloads: dict[datetime, HistoricalOddsResponse]) -> None:
        self.payloads = payloads
        self.requested_times: list[datetime] = []
        self.request_kwargs: list[dict[str, object]] = []

    def get_historical_odds(
        self,
        *,
        date: datetime,
        **kwargs: object,
    ) -> HistoricalOddsResponse:
        self.requested_times.append(date)
        self.request_kwargs.append(kwargs)
        return self.payloads[date]


def insert_team(connection: sqlite3.Connection, team_id: int, name: str) -> None:
    connection.execute(
        """
        INSERT INTO teams (team_id, team_key, name)
        VALUES (?, ?, ?)
        """,
        (team_id, name.lower().replace(" ", "-"), name),
    )


def insert_game(
    connection: sqlite3.Connection,
    *,
    game_id: int,
    commence_time: str,
    home_team_id: int,
    away_team_id: int,
    source_event_id: str,
) -> None:
    connection.execute(
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
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            game_id,
            2025,
            commence_time[:10],
            commence_time,
            home_team_id,
            away_team_id,
            source_event_id,
            "basketball_ncaab",
            "NCAAM",
            "W",
            1,
            75,
            70,
            commence_time,
        ),
    )


def historical_response(
    *,
    timestamp: str,
    events: list[dict[str, object]],
    last_cost: int = 10,
) -> HistoricalOddsResponse:
    return HistoricalOddsResponse(
        timestamp=timestamp,
        previous_timestamp=None,
        next_timestamp=None,
        data=events,
        quota=ApiQuota(remaining=2000 - last_cost, used=last_cost, last_cost=last_cost),
    )


def sample_historical_event(
    *,
    event_id: str,
    commence_time: str,
    home_team: str,
    away_team: str,
    include_spreads: bool = False,
    include_totals: bool = False,
) -> dict[str, object]:
    markets: list[dict[str, object]] = [
        {
            "key": "h2h",
            "last_update": commence_time,
            "outcomes": [
                {"name": home_team, "price": -135},
                {"name": away_team, "price": 115},
            ],
        }
    ]
    if include_spreads:
        markets.append(
            {
                "key": "spreads",
                "last_update": commence_time,
                "outcomes": [
                    {"name": home_team, "price": -110, "point": -4.5},
                    {"name": away_team, "price": -110, "point": 4.5},
                ],
            }
        )
    if include_totals:
        markets.append(
            {
                "key": "totals",
                "last_update": commence_time,
                "outcomes": [
                    {"name": "Over", "price": -108, "point": 139.5},
                    {"name": "Under", "price": -112, "point": 139.5},
                ],
            }
        )
    return {
        "id": event_id,
        "commence_time": commence_time,
        "home_team": home_team,
        "away_team": away_team,
        "bookmakers": [
            {
                "key": "draftkings",
                "title": "DraftKings",
                "last_update": commence_time,
                "markets": markets,
            }
        ],
    }


def test_team_name_matching_handles_provider_variants() -> None:
    assert "michigan state" in build_team_aliases("Michigan St Spartans")
    assert "seattle" in build_team_aliases("Seattle U Redhawks")

    matched_id = match_team_pair(
        home_team_name="Michigan St Spartans",
        away_team_name="Indiana Hoosiers",
        candidates=[
            TeamPairCandidate(
                candidate_id=11,
                home_team_name="Michigan State Spartans",
                away_team_name="Indiana Hoosiers",
            ),
            TeamPairCandidate(
                candidate_id=12,
                home_team_name="Ohio State Buckeyes",
                away_team_name="Wisconsin Badgers",
            ),
        ],
    )

    assert matched_id == 11


def test_ingest_closing_odds_only_fetches_missing_games_and_marks_closing_lines(
    tmp_path,
) -> None:
    db_path = tmp_path / "closing.sqlite"
    create_closing_lines_test_db(db_path)
    connection = sqlite3.connect(db_path)

    teams = [
        (1, "Michigan State Spartans"),
        (2, "Indiana Hoosiers"),
        (3, "Gonzaga Bulldogs"),
        (4, "Saint Mary's Gaels"),
        (5, "Kansas Jayhawks"),
        (6, "Baylor Bears"),
        (7, "Duke Blue Devils"),
        (8, "North Carolina Tar Heels"),
    ]
    for team_id, name in teams:
        insert_team(connection, team_id, name)

    insert_game(
        connection,
        game_id=1,
        commence_time="2025-03-05T19:00:00+00:00",
        home_team_id=1,
        away_team_id=2,
        source_event_id="espn-1",
    )
    insert_game(
        connection,
        game_id=2,
        commence_time="2025-03-05T19:00:00+00:00",
        home_team_id=3,
        away_team_id=4,
        source_event_id="espn-2",
    )
    insert_game(
        connection,
        game_id=3,
        commence_time="2025-03-05T20:00:00+00:00",
        home_team_id=5,
        away_team_id=6,
        source_event_id="espn-3",
    )
    insert_game(
        connection,
        game_id=4,
        commence_time="2025-03-05T21:00:00+00:00",
        home_team_id=7,
        away_team_id=8,
        source_event_id="espn-4",
    )

    connection.execute(
        """
        INSERT INTO historical_odds_checkpoints (
            source_name, sport_key, market_key, filters_key, snapshot_time
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (
            "odds_api_historical_close",
            "basketball_ncaab",
            "h2h",
            "regions:us",
            "2025-03-05T20:00:00+00:00",
        ),
    )
    connection.execute(
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
        (
            4,
            "draftkings",
            "DraftKings",
            "h2h",
            "2025-03-05T20:55:00+00:00",
            1,
            -120.0,
            100.0,
            '{"key":"h2h"}',
        ),
    )
    connection.commit()
    connection.close()

    snapshot_time = datetime(2025, 3, 5, 19, 0, tzinfo=UTC)
    fake_client = FakeHistoricalOddsClient(
        {
            snapshot_time: historical_response(
                timestamp="2025-03-05T19:00:00Z",
                events=[
                    sample_historical_event(
                        event_id="odds-1",
                        commence_time="2025-03-05T19:00:00Z",
                        home_team="Michigan St Spartans",
                        away_team="Indiana Hoosiers",
                    )
                ],
            )
        }
    )

    summary = ingest_closing_odds(
        options=ClosingOddsIngestOptions(
            start_date=date(2025, 3, 5),
            end_date=date(2025, 3, 5),
        ),
        database_url=f"sqlite+pysqlite:///{db_path}",
        client=fake_client,
    )

    assert summary == ClosingOddsIngestSummary(
        sport="basketball_ncaab",
        market="h2h",
        start_date="2025-03-05",
        end_date="2025-03-05",
        snapshot_slots_found=2,
        snapshot_slots_requested=1,
        snapshot_slots_skipped=1,
        snapshot_slots_deferred=0,
        games_considered=3,
        games_matched=1,
        games_unmatched=1,
        odds_snapshots_upserted=1,
        credits_spent=10,
        quota=ApiQuota(remaining=1990, used=10, last_cost=10),
    )
    assert fake_client.requested_times == [snapshot_time]

    connection = sqlite3.connect(db_path)
    inserted_snapshot = connection.execute(
        """
        SELECT bookmaker_key, market_key, is_closing_line, team1_price, team2_price
        FROM odds_snapshots
        WHERE game_id = 1
        """
    ).fetchone()
    checkpoints = connection.execute(
        """
        SELECT snapshot_time
        FROM historical_odds_checkpoints
        ORDER BY snapshot_time
        """
    ).fetchall()
    connection.close()

    assert inserted_snapshot == ("draftkings", "h2h", 1, -135.0, 115.0)
    assert checkpoints == [
        ("2025-03-05T19:00:00+00:00",),
        ("2025-03-05T20:00:00+00:00",),
    ]


def test_ingest_closing_odds_can_revisit_checkpointed_missing_slots(
    tmp_path,
) -> None:
    db_path = tmp_path / "closing.sqlite"
    create_closing_lines_test_db(db_path)
    connection = sqlite3.connect(db_path)

    teams = [
        (1, "Michigan State Spartans"),
        (2, "Indiana Hoosiers"),
        (3, "Gonzaga Bulldogs"),
        (4, "Saint Mary's Gaels"),
        (5, "Kansas Jayhawks"),
        (6, "Baylor Bears"),
        (7, "Duke Blue Devils"),
        (8, "North Carolina Tar Heels"),
    ]
    for team_id, name in teams:
        insert_team(connection, team_id, name)

    insert_game(
        connection,
        game_id=1,
        commence_time="2025-03-05T19:00:00+00:00",
        home_team_id=1,
        away_team_id=2,
        source_event_id="espn-1",
    )
    insert_game(
        connection,
        game_id=2,
        commence_time="2025-03-05T19:00:00+00:00",
        home_team_id=3,
        away_team_id=4,
        source_event_id="espn-2",
    )
    insert_game(
        connection,
        game_id=3,
        commence_time="2025-03-05T20:00:00+00:00",
        home_team_id=5,
        away_team_id=6,
        source_event_id="espn-3",
    )
    insert_game(
        connection,
        game_id=4,
        commence_time="2025-03-05T21:00:00+00:00",
        home_team_id=7,
        away_team_id=8,
        source_event_id="espn-4",
    )

    connection.execute(
        """
        INSERT INTO historical_odds_checkpoints (
            source_name, sport_key, market_key, filters_key, snapshot_time
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (
            "odds_api_historical_close",
            "basketball_ncaab",
            "h2h",
            "regions:us",
            "2025-03-05T20:00:00+00:00",
        ),
    )
    connection.execute(
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
        (
            4,
            "draftkings",
            "DraftKings",
            "h2h",
            "2025-03-05T20:55:00+00:00",
            1,
            -120.0,
            100.0,
            '{"key":"h2h"}',
        ),
    )
    connection.commit()
    connection.close()

    first_snapshot_time = datetime(2025, 3, 5, 19, 0, tzinfo=UTC)
    second_snapshot_time = datetime(2025, 3, 5, 20, 0, tzinfo=UTC)
    fake_client = FakeHistoricalOddsClient(
        {
            first_snapshot_time: historical_response(
                timestamp="2025-03-05T19:00:00Z",
                events=[
                    sample_historical_event(
                        event_id="odds-1",
                        commence_time="2025-03-05T19:00:00Z",
                        home_team="Michigan St Spartans",
                        away_team="Indiana Hoosiers",
                    )
                ],
            ),
            second_snapshot_time: historical_response(
                timestamp="2025-03-05T20:00:00Z",
                events=[
                    sample_historical_event(
                        event_id="odds-3",
                        commence_time="2025-03-05T20:00:00Z",
                        home_team="Kansas Jayhawks",
                        away_team="Baylor Bears",
                    )
                ],
            ),
        }
    )

    summary = ingest_closing_odds(
        options=ClosingOddsIngestOptions(
            start_date=date(2025, 3, 5),
            end_date=date(2025, 3, 5),
            ignore_checkpoints=True,
        ),
        database_url=f"sqlite+pysqlite:///{db_path}",
        client=fake_client,
    )

    assert summary == ClosingOddsIngestSummary(
        sport="basketball_ncaab",
        market="h2h",
        start_date="2025-03-05",
        end_date="2025-03-05",
        snapshot_slots_found=2,
        snapshot_slots_requested=2,
        snapshot_slots_skipped=0,
        snapshot_slots_deferred=0,
        games_considered=3,
        games_matched=2,
        games_unmatched=1,
        odds_snapshots_upserted=2,
        credits_spent=20,
        quota=ApiQuota(remaining=1990, used=10, last_cost=10),
    )
    assert fake_client.requested_times == [
        first_snapshot_time,
        second_snapshot_time,
    ]

    connection = sqlite3.connect(db_path)
    inserted_snapshots = connection.execute(
        """
        SELECT game_id, team1_price, team2_price
        FROM odds_snapshots
        WHERE game_id IN (1, 3)
        ORDER BY game_id
        """
    ).fetchall()
    connection.close()

    assert inserted_snapshots == [
        (1, -135.0, 115.0),
        (3, -135.0, 115.0),
    ]


def test_ingest_closing_odds_passes_bookmaker_filter_to_client(tmp_path) -> None:
    db_path = tmp_path / "closing.sqlite"
    create_closing_lines_test_db(db_path)
    connection = sqlite3.connect(db_path)
    insert_team(connection, 1, "Michigan State Spartans")
    insert_team(connection, 2, "Indiana Hoosiers")
    insert_game(
        connection,
        game_id=1,
        commence_time="2025-03-05T19:00:00+00:00",
        home_team_id=1,
        away_team_id=2,
        source_event_id="espn-1",
    )
    connection.commit()
    connection.close()

    snapshot_time = datetime(2025, 3, 5, 19, 0, tzinfo=UTC)
    fake_client = FakeHistoricalOddsClient(
        {
            snapshot_time: historical_response(
                timestamp="2025-03-05T19:00:00Z",
                events=[
                    sample_historical_event(
                        event_id="odds-1",
                        commence_time="2025-03-05T19:00:00Z",
                        home_team="Michigan St Spartans",
                        away_team="Indiana Hoosiers",
                    )
                ],
            )
        }
    )

    ingest_closing_odds(
        options=ClosingOddsIngestOptions(
            start_date=date(2025, 3, 5),
            end_date=date(2025, 3, 5),
            market="spreads",
            regions="us,uk",
            bookmakers="draftkings,fanduel,pinnacle",
        ),
        database_url=f"sqlite+pysqlite:///{db_path}",
        client=fake_client,
    )

    assert fake_client.request_kwargs == [
        {
            "sport": "basketball_ncaab",
            "regions": "us,uk",
            "markets": "spreads",
            "bookmakers": "draftkings,fanduel,pinnacle",
            "odds_format": "american",
        }
    ]


def test_ingest_closing_odds_matches_historical_event_with_time_drift(tmp_path) -> None:
    db_path = tmp_path / "closing.sqlite"
    create_closing_lines_test_db(db_path)
    connection = sqlite3.connect(db_path)
    insert_team(connection, 1, "UNLV Rebels")
    insert_team(connection, 2, "Air Force Falcons")
    insert_game(
        connection,
        game_id=1,
        commence_time="2025-03-05T19:00:00+00:00",
        home_team_id=1,
        away_team_id=2,
        source_event_id="espn-1",
    )
    connection.commit()
    connection.close()

    snapshot_time = datetime(2025, 3, 5, 19, 0, tzinfo=UTC)
    fake_client = FakeHistoricalOddsClient(
        {
            snapshot_time: historical_response(
                timestamp="2025-03-05T19:00:00Z",
                events=[
                    sample_historical_event(
                        event_id="odds-1",
                        commence_time="2025-03-05T19:10:00Z",
                        home_team="UNLV Rebels",
                        away_team="Air Force Falcons",
                    )
                ],
            )
        }
    )

    summary = ingest_closing_odds(
        options=ClosingOddsIngestOptions(
            start_date=date(2025, 3, 5),
            end_date=date(2025, 3, 5),
        ),
        database_url=f"sqlite+pysqlite:///{db_path}",
        client=fake_client,
    )

    assert summary.games_matched == 1
    assert summary.odds_snapshots_upserted == 1


def test_ingest_closing_odds_retries_previous_snapshot_for_unmatched_slot(
    tmp_path,
) -> None:
    db_path = tmp_path / "closing.sqlite"
    create_closing_lines_test_db(db_path)
    connection = sqlite3.connect(db_path)
    insert_team(connection, 1, "Baylor Bears")
    insert_team(connection, 2, "Oregon State Beavers")
    insert_game(
        connection,
        game_id=1,
        commence_time="2025-03-05T19:00:00+00:00",
        home_team_id=1,
        away_team_id=2,
        source_event_id="espn-1",
    )
    connection.commit()
    connection.close()

    snapshot_time = datetime(2025, 3, 5, 19, 0, tzinfo=UTC)
    previous_snapshot_time = datetime(2025, 3, 5, 18, 55, tzinfo=UTC)
    fake_client = FakeHistoricalOddsClient(
        {
            snapshot_time: HistoricalOddsResponse(
                timestamp="2025-03-05T19:00:00Z",
                previous_timestamp="2025-03-05T18:55:00Z",
                next_timestamp=None,
                data=[],
                quota=ApiQuota(remaining=1990, used=10, last_cost=10),
            ),
            previous_snapshot_time: historical_response(
                timestamp="2025-03-05T18:55:00Z",
                events=[
                    sample_historical_event(
                        event_id="odds-1",
                        commence_time="2025-03-05T19:00:00Z",
                        home_team="Baylor Bears",
                        away_team="Oregon State Beavers",
                    )
                ],
            ),
        }
    )

    summary = ingest_closing_odds(
        options=ClosingOddsIngestOptions(
            start_date=date(2025, 3, 5),
            end_date=date(2025, 3, 5),
        ),
        database_url=f"sqlite+pysqlite:///{db_path}",
        client=fake_client,
    )

    assert summary.games_matched == 1
    assert summary.games_unmatched == 0
    assert summary.odds_snapshots_upserted == 1
    assert summary.credits_spent == 20
    assert fake_client.requested_times == [snapshot_time, previous_snapshot_time]


def test_ingest_closing_odds_multi_market_repairs_any_missing_requested_market(
    tmp_path,
) -> None:
    db_path = tmp_path / "closing.sqlite"
    create_closing_lines_test_db(db_path)
    connection = sqlite3.connect(db_path)
    insert_team(connection, 1, "Baylor Bears")
    insert_team(connection, 2, "Oregon State Beavers")
    insert_game(
        connection,
        game_id=1,
        commence_time="2025-03-05T19:00:00+00:00",
        home_team_id=1,
        away_team_id=2,
        source_event_id="espn-1",
    )
    connection.execute(
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
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            1,
            "draftkings",
            "DraftKings",
            "h2h",
            "2025-03-05T19:00:00+00:00",
            1,
            -130.0,
            110.0,
            "{}",
        ),
    )
    connection.commit()
    connection.close()

    snapshot_time = datetime(2025, 3, 5, 19, 0, tzinfo=UTC)
    fake_client = FakeHistoricalOddsClient(
        {
            snapshot_time: historical_response(
                timestamp="2025-03-05T19:00:00Z",
                events=[
                    sample_historical_event(
                        event_id="odds-1",
                        commence_time="2025-03-05T19:00:00Z",
                        home_team="Baylor Bears",
                        away_team="Oregon State Beavers",
                        include_spreads=True,
                        include_totals=True,
                    )
                ],
                last_cost=30,
            )
        }
    )

    summary = ingest_closing_odds(
        options=ClosingOddsIngestOptions(
            start_date=date(2025, 3, 5),
            end_date=date(2025, 3, 5),
            market="h2h,spreads,totals",
        ),
        database_url=f"sqlite+pysqlite:///{db_path}",
        client=fake_client,
    )

    assert summary.market == "h2h,spreads,totals"
    assert summary.games_matched == 1
    assert summary.credits_spent == 30
    assert fake_client.request_kwargs == [
        {
            "sport": "basketball_ncaab",
            "regions": "us",
            "markets": "h2h,spreads,totals",
            "bookmakers": None,
            "odds_format": "american",
        }
    ]

    connection = sqlite3.connect(db_path)
    rows = connection.execute(
        """
        SELECT market_key
        FROM odds_snapshots
        WHERE game_id = 1 AND is_closing_line = 1
        ORDER BY market_key
        """
    ).fetchall()
    connection.close()

    assert rows == [("h2h",), ("spreads",), ("totals",)]


def test_ingest_closing_odds_skips_malformed_historical_event(tmp_path) -> None:
    db_path = tmp_path / "closing.sqlite"
    create_closing_lines_test_db(db_path)
    connection = sqlite3.connect(db_path)
    insert_team(connection, 1, "Duke Blue Devils")
    insert_team(connection, 2, "Virginia Cavaliers")
    insert_game(
        connection,
        game_id=1,
        commence_time="2025-03-05T19:00:00+00:00",
        home_team_id=1,
        away_team_id=2,
        source_event_id="espn-1",
    )
    connection.commit()
    connection.close()

    snapshot_time = datetime(2025, 3, 5, 19, 0, tzinfo=UTC)
    fake_client = FakeHistoricalOddsClient(
        {
            snapshot_time: historical_response(
                timestamp="2025-03-05T19:00:00Z",
                events=[
                    {
                        "id": "bad-event",
                        "commence_time": "2025-03-05T19:00:00Z",
                        "away_team": "Virginia Cavaliers",
                        "bookmakers": [],
                    },
                    sample_historical_event(
                        event_id="odds-1",
                        commence_time="2025-03-05T19:00:00Z",
                        home_team="Duke Blue Devils",
                        away_team="Virginia Cavaliers",
                    ),
                ],
            )
        }
    )

    summary = ingest_closing_odds(
        options=ClosingOddsIngestOptions(
            start_date=date(2025, 3, 5),
            end_date=date(2025, 3, 5),
        ),
        database_url=f"sqlite+pysqlite:///{db_path}",
        client=fake_client,
    )

    assert summary.games_matched == 1
    assert summary.games_unmatched == 0


def test_ingest_closing_odds_matches_reversed_home_away_event(tmp_path) -> None:
    db_path = tmp_path / "closing.sqlite"
    create_closing_lines_test_db(db_path)
    connection = sqlite3.connect(db_path)
    insert_team(connection, 1, "Michigan State Spartans")
    insert_team(connection, 2, "Indiana Hoosiers")
    insert_game(
        connection,
        game_id=1,
        commence_time="2025-03-05T19:00:00+00:00",
        home_team_id=1,
        away_team_id=2,
        source_event_id="espn-1",
    )
    connection.commit()
    connection.close()

    snapshot_time = datetime(2025, 3, 5, 19, 0, tzinfo=UTC)
    fake_client = FakeHistoricalOddsClient(
        {
            snapshot_time: historical_response(
                timestamp="2025-03-05T19:00:00Z",
                events=[
                    sample_historical_event(
                        event_id="odds-1",
                        commence_time="2025-03-05T19:00:00Z",
                        home_team="Indiana Hoosiers",
                        away_team="Michigan St Spartans",
                    )
                ],
            )
        }
    )

    summary = ingest_closing_odds(
        options=ClosingOddsIngestOptions(
            start_date=date(2025, 3, 5),
            end_date=date(2025, 3, 5),
        ),
        database_url=f"sqlite+pysqlite:///{db_path}",
        client=fake_client,
    )

    connection = sqlite3.connect(db_path)
    inserted_snapshot = connection.execute(
        """
        SELECT team1_price, team2_price
        FROM odds_snapshots
        WHERE game_id = 1
        """
    ).fetchone()
    connection.close()

    assert summary.games_matched == 1
    assert inserted_snapshot == (115.0, -135.0)
