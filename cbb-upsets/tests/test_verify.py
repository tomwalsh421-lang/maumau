import sqlite3
from datetime import date

from cbb.verify import GameVerificationSummary, VerificationOptions, verify_games
from tests.support import make_team_catalog


def create_verify_test_db(path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
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
    status_name: str | None = None,
) -> dict[str, object]:
    status_payload = {"completed": completed}
    if status_name is not None:
        status_payload["name"] = status_name

    return {
        "id": event_id,
        "date": event_date,
        "status": {"type": status_payload},
        "competitions": [
            {
                "status": {"type": status_payload},
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


def test_verify_games_flags_missing_status_and_score_issues(tmp_path) -> None:
    db_path = tmp_path / "verify.sqlite"
    create_verify_test_db(db_path)

    connection = sqlite3.connect(db_path)
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
                1,
                2026,
                "2026-01-10",
                "2026-01-10T20:00:00+00:00",
                1,
                2,
                "evt-correct",
                "basketball_ncaab",
                "NCAAM",
                "W",
                1,
                81,
                77,
                "2026-01-10T22:00:00+00:00",
            ),
            (
                2,
                2026,
                "2026-01-10",
                "2026-01-10T22:00:00+00:00",
                3,
                4,
                "evt-stale",
                "basketball_ncaab",
                "NCAAM",
                None,
                0,
                0,
                0,
                None,
            ),
            (
                3,
                2026,
                "2026-01-10",
                "2026-01-10T23:00:00+00:00",
                5,
                6,
                "evt-score",
                "basketball_ncaab",
                "NCAAM",
                "W",
                1,
                70,
                60,
                "2026-01-11T01:00:00+00:00",
            ),
        ],
    )
    connection.commit()
    connection.close()

    fake_client = FakeEspnClient(
        {
            date(2026, 1, 10): [
                sample_espn_event(
                    event_id="evt-correct",
                    event_date="2026-01-10T20:00Z",
                    home_team="Duke Blue Devils",
                    away_team="North Carolina Tar Heels",
                    home_score="81",
                    away_score="77",
                ),
                sample_espn_event(
                    event_id="evt-missing",
                    event_date="2026-01-10T21:00Z",
                    home_team="Kansas Jayhawks",
                    away_team="Baylor Bears",
                    home_score="73",
                    away_score="68",
                ),
                sample_espn_event(
                    event_id="evt-stale",
                    event_date="2026-01-10T22:00Z",
                    home_team="Gonzaga Bulldogs",
                    away_team="Saint Mary's Gaels",
                    home_score="75",
                    away_score="71",
                ),
                sample_espn_event(
                    event_id="evt-score",
                    event_date="2026-01-10T23:00Z",
                    home_team="Arizona Wildcats",
                    away_team="Houston Cougars",
                    home_score="72",
                    away_score="60",
                ),
                sample_espn_event(
                    event_id="evt-skipped",
                    event_date="2026-01-10T23:30Z",
                    home_team="Pacific Tigers",
                    away_team="Blackburn Beavers",
                    home_score="88",
                    away_score="40",
                ),
                sample_espn_event(
                    event_id="evt-postponed",
                    event_date="2026-01-10T23:45Z",
                    home_team="Duke Blue Devils",
                    away_team="North Carolina Tar Heels",
                    home_score="0",
                    away_score="0",
                    completed=False,
                    status_name="STATUS_POSTPONED",
                ),
            ]
        }
    )

    summary = verify_games(
        options=VerificationOptions(
            start_date=date(2026, 1, 10),
            end_date=date(2026, 1, 10),
        ),
        database_url=f"sqlite+pysqlite:///{db_path}",
        client=fake_client,
        team_catalog=make_team_catalog(
            [
                ("Duke", "Duke Blue Devils", None),
                ("North Carolina", "North Carolina Tar Heels", None),
                ("Kansas", "Kansas Jayhawks", None),
                ("Baylor", "Baylor Bears", None),
                ("Gonzaga", "Gonzaga Bulldogs", None),
                ("Saint Mary's", "Saint Mary's Gaels", None),
                ("Arizona", "Arizona Wildcats", None),
                ("Houston", "Houston Cougars", None),
                ("Pacific", "Pacific Tigers", None),
            ]
        ),
    )

    assert summary == GameVerificationSummary(
        sport="basketball_ncaab",
        start_date="2026-01-10",
        end_date="2026-01-10",
        dates_checked=1,
        upstream_games_seen=4,
        upstream_games_skipped=2,
        completed_games_seen=4,
        games_present=3,
        games_verified=1,
        games_missing=1,
        status_mismatches=1,
        score_mismatches=1,
        sample_missing_games=("evt-missing Kansas Jayhawks vs Baylor Bears",),
        sample_status_mismatches=("evt-stale Gonzaga Bulldogs vs Saint Mary's Gaels",),
        sample_score_mismatches=("evt-score Arizona Wildcats vs Houston Cougars",),
    )
    assert fake_client.requested_dates == [date(2026, 1, 10)]
