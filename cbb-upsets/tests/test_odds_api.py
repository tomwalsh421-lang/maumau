import json
import sqlite3

from typer.testing import CliRunner

from cbb.cli import app
from cbb.ingest import (
    ApiQuota,
    HistoricalOddsResponse,
    OddsIngestSummary,
    OddsPersistenceInput,
    derive_cbb_season,
    normalize_team_key,
    persist_odds_data,
)
from cbb.ingest.clients.odds_api import OddsApiClient
from tests.support import make_team_catalog

runner = CliRunner()


def create_ingest_test_db(path) -> None:
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
        """
    )
    connection.commit()
    connection.close()


def sample_odds_events() -> list[dict[str, object]]:
    return [
        {
            "id": "evt-1",
            "sport_key": "basketball_ncaab",
            "sport_title": "NCAAB",
            "commence_time": "2026-03-07T19:00:00Z",
            "home_team": "Duke Blue Devils",
            "away_team": "North Carolina Tar Heels",
            "bookmakers": [
                {
                    "key": "fanduel",
                    "title": "FanDuel",
                    "last_update": "2026-03-07T18:55:00Z",
                    "markets": [
                        {
                            "key": "h2h",
                            "last_update": "2026-03-07T18:55:00Z",
                            "outcomes": [
                                {"name": "Duke Blue Devils", "price": -140},
                                {"name": "North Carolina Tar Heels", "price": 120},
                            ],
                        },
                        {
                            "key": "spreads",
                            "last_update": "2026-03-07T18:55:00Z",
                            "outcomes": [
                                {
                                    "name": "Duke Blue Devils",
                                    "price": -110,
                                    "point": -2.5,
                                },
                                {
                                    "name": "North Carolina Tar Heels",
                                    "price": -110,
                                    "point": 2.5,
                                },
                            ],
                        },
                        {
                            "key": "totals",
                            "last_update": "2026-03-07T18:55:00Z",
                            "outcomes": [
                                {"name": "Over", "price": -108, "point": 151.5},
                                {"name": "Under", "price": -112, "point": 151.5},
                            ],
                        },
                    ],
                }
            ],
        }
    ]


def sample_score_events() -> list[dict[str, object]]:
    return [
        {
            "id": "evt-1",
            "sport_key": "basketball_ncaab",
            "sport_title": "NCAAB",
            "commence_time": "2026-03-07T19:00:00Z",
            "home_team": "Duke Blue Devils",
            "away_team": "North Carolina Tar Heels",
            "completed": False,
            "scores": [
                {"name": "Duke Blue Devils", "score": "41"},
                {"name": "North Carolina Tar Heels", "score": "37"},
            ],
            "last_update": "2026-03-07T19:40:00Z",
        },
        {
            "id": "evt-2",
            "sport_key": "basketball_ncaab",
            "sport_title": "NCAAB",
            "commence_time": "2026-03-06T21:00:00Z",
            "home_team": "Kansas Jayhawks",
            "away_team": "Baylor Bears",
            "completed": True,
            "scores": [
                {"name": "Kansas Jayhawks", "score": "72"},
                {"name": "Baylor Bears", "score": "68"},
            ],
            "last_update": "2026-03-06T23:00:00Z",
        },
    ]


def test_persist_odds_data_loads_teams_games_and_snapshots(tmp_path) -> None:
    db_path = tmp_path / "odds.sqlite"
    create_ingest_test_db(db_path)

    summary = persist_odds_data(
        payload=OddsPersistenceInput(
            sport="basketball_ncaab",
            odds_events=sample_odds_events(),
            score_events=sample_score_events(),
            odds_quota=ApiQuota(remaining=97, used=3, last_cost=3),
            scores_quota=ApiQuota(remaining=96, used=4, last_cost=1),
        ),
        database_url=f"sqlite+pysqlite:///{db_path}",
        team_catalog=make_team_catalog(
            [
                ("Duke", "Duke Blue Devils", None),
                ("North Carolina", "North Carolina Tar Heels", None),
                ("Kansas", "Kansas Jayhawks", None),
                ("Baylor", "Baylor Bears", None),
            ]
        ),
    )

    assert summary == OddsIngestSummary(
        sport="basketball_ncaab",
        teams_seen=4,
        games_upserted=2,
        games_skipped=0,
        odds_snapshots_upserted=3,
        completed_games_updated=1,
        odds_quota=ApiQuota(remaining=97, used=3, last_cost=3),
        scores_quota=ApiQuota(remaining=96, used=4, last_cost=1),
    )

    connection = sqlite3.connect(db_path)
    teams = connection.execute(
        "SELECT team_key, name FROM teams ORDER BY team_key"
    ).fetchall()
    games = connection.execute(
        "SELECT source_event_id, season, result, completed, home_score, away_score "
        "FROM games ORDER BY source_event_id"
    ).fetchall()
    snapshots = connection.execute(
        "SELECT market_key, bookmaker_key, is_closing_line, team1_price, "
        "team2_price, total_points, payload "
        "FROM odds_snapshots ORDER BY market_key"
    ).fetchall()
    connection.close()

    assert teams == [
        ("baylor-bears", "Baylor Bears"),
        ("duke-blue-devils", "Duke Blue Devils"),
        ("kansas-jayhawks", "Kansas Jayhawks"),
        ("north-carolina-tar-heels", "North Carolina Tar Heels"),
    ]
    assert games == [
        ("evt-1", 2026, None, 0, 41, 37),
        ("evt-2", 2026, "W", 1, 72, 68),
    ]
    assert len(snapshots) == 3
    assert snapshots[0][:6] == ("h2h", "fanduel", 0, -140.0, 120.0, None)
    assert json.loads(snapshots[0][6])["key"] == "h2h"


def test_team_key_and_season_helpers() -> None:
    assert normalize_team_key("Saint Mary's Gaels") == "saint-mary-s-gaels"
    assert derive_cbb_season("2025-11-15T20:00:00Z") == 2026
    assert derive_cbb_season("2026-03-07T20:00:00Z") == 2026


def test_ingest_odds_command_reports_summary(monkeypatch) -> None:
    def fake_ingest_current_odds(**_kwargs: object) -> OddsIngestSummary:
        return OddsIngestSummary(
            sport="basketball_ncaab",
            teams_seen=8,
            games_upserted=4,
            games_skipped=1,
            odds_snapshots_upserted=12,
            completed_games_updated=2,
            odds_quota=ApiQuota(remaining=90, used=10, last_cost=3),
            scores_quota=ApiQuota(remaining=89, used=11, last_cost=1),
        )

    monkeypatch.setattr("cbb.cli.ingest_current_odds", fake_ingest_current_odds)

    result = runner.invoke(app, ["ingest", "odds"])

    assert result.exit_code == 0
    assert (
        "teams=8, games=4, games_skipped=1, completed_games=2, odds_snapshots=12"
        in result.stdout
    )
    assert "Odds quota: used=10, remaining=90, last_cost=3" in result.stdout
    assert "Scores quota: used=11, remaining=89, last_cost=1" in result.stdout


class FakeResponse:
    def __init__(
        self,
        *,
        status_code: int,
        payload: bytes,
        headers: dict[str, str],
    ) -> None:
        self.status_code = status_code
        self.content = payload
        self.headers = headers
        self.text = payload.decode("utf-8")

    def raise_for_status(self) -> None:
        return None


class FakeSession:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.calls: list[tuple[str, dict[str, object], int]] = []

    def get(
        self,
        url: str,
        *,
        params: dict[str, object],
        timeout: int,
    ) -> FakeResponse:
        self.calls.append((url, params, timeout))
        return self.response


def test_get_historical_odds_parses_snapshot_response() -> None:
    session = FakeSession(
        FakeResponse(
            status_code=200,
            payload=json.dumps(
                {
                    "timestamp": "2025-03-05T19:00:00Z",
                    "previous_timestamp": "2025-03-05T18:55:00Z",
                    "next_timestamp": "2025-03-05T19:05:00Z",
                    "data": [
                        {
                            "id": "evt-1",
                            "commence_time": "2025-03-05T19:00:00Z",
                            "home_team": "Michigan St Spartans",
                            "away_team": "Indiana Hoosiers",
                            "bookmakers": [],
                        }
                    ],
                }
            ).encode("utf-8"),
            headers={
                "x-requests-remaining": "1990",
                "x-requests-used": "10",
                "x-requests-last": "10",
            },
        )
    )
    client = OddsApiClient(
        api_key="test-key",
        base_url="https://example.com/v4",
        session=session,
    )

    response = client.get_historical_odds(
        date=derive_historical_snapshot_datetime(),
        sport="basketball_ncaab",
        markets="h2h",
    )

    assert response == HistoricalOddsResponse(
        timestamp="2025-03-05T19:00:00Z",
        previous_timestamp="2025-03-05T18:55:00Z",
        next_timestamp="2025-03-05T19:05:00Z",
        data=[
            {
                "id": "evt-1",
                "commence_time": "2025-03-05T19:00:00Z",
                "home_team": "Michigan St Spartans",
                "away_team": "Indiana Hoosiers",
                "bookmakers": [],
            }
        ],
        quota=ApiQuota(remaining=1990, used=10, last_cost=10),
    )
    assert (
        session.calls[0][0]
        == "https://example.com/v4/historical/sports/basketball_ncaab/odds"
    )
    assert session.calls[0][1]["markets"] == "h2h"


def derive_historical_snapshot_datetime():
    from datetime import UTC, datetime

    return datetime(2025, 3, 5, 19, 0, tzinfo=UTC)
