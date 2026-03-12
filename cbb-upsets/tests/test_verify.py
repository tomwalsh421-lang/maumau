import sqlite3
from datetime import date

from cbb.verify import GameVerificationSummary, VerificationOptions, verify_games
from tests.support import make_team_catalog


def create_verify_test_db(path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE teams (
            team_id INTEGER PRIMARY KEY,
            team_key TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL
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
    status_payload = {"completed": completed}
    if status_name is not None:
        status_payload["name"] = status_name

    notes: list[dict[str, str]] = []
    if event_note_headline is not None:
        notes.append({"headline": event_note_headline})

    competition: dict[str, object] = {
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
        "season": {"year": 2026, "type": season_type, "slug": season_type_slug},
        "status": {"type": status_payload},
        "competitions": [competition],
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
            last_score_update,
            neutral_site,
            conference_competition,
            season_type,
            season_type_slug,
            tournament_id,
            event_note_headline,
            venue_id,
            venue_name,
            venue_city,
            venue_state,
            venue_indoor
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?
        )
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
                0,
                1,
                2,
                "regular-season",
                None,
                None,
                "2171",
                "Cameron Indoor Stadium",
                "Durham",
                "NC",
                1,
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
                1,
                0,
                3,
                "post-season",
                "333",
                "WCC Tournament - Quarterfinal",
                "500",
                "Orleans Arena",
                "Las Vegas",
                "NV",
                1,
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
                0,
                1,
                2,
                "regular-season",
                None,
                None,
                "200",
                "McKale Center",
                "Tucson",
                "AZ",
                1,
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
                    conference_competition=True,
                    venue_id="2171",
                    venue_name="Cameron Indoor Stadium",
                    venue_city="Durham",
                    venue_state="NC",
                    venue_indoor=True,
                ),
                sample_espn_event(
                    event_id="evt-missing",
                    event_date="2026-01-10T21:00Z",
                    home_team="Kansas Jayhawks",
                    away_team="Baylor Bears",
                    home_score="73",
                    away_score="68",
                    conference_competition=True,
                    venue_name="Allen Fieldhouse",
                    venue_city="Lawrence",
                    venue_state="KS",
                    venue_indoor=True,
                ),
                sample_espn_event(
                    event_id="evt-stale",
                    event_date="2026-01-10T22:00Z",
                    home_team="Gonzaga Bulldogs",
                    away_team="Saint Mary's Gaels",
                    home_score="75",
                    away_score="71",
                    neutral_site=True,
                    season_type=3,
                    season_type_slug="post-season",
                    tournament_id="333",
                    event_note_headline="WCC Tournament - Quarterfinal",
                    venue_id="500",
                    venue_name="Orleans Arena",
                    venue_city="Las Vegas",
                    venue_state="NV",
                    venue_indoor=True,
                ),
                sample_espn_event(
                    event_id="evt-score",
                    event_date="2026-01-10T23:00Z",
                    home_team="Arizona Wildcats",
                    away_team="Houston Cougars",
                    home_score="72",
                    away_score="60",
                    conference_competition=True,
                    venue_id="200",
                    venue_name="McKale Center",
                    venue_city="Tucson",
                    venue_state="AZ",
                    venue_indoor=True,
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
        context_mismatches=0,
        sample_missing_games=("evt-missing Kansas Jayhawks vs Baylor Bears",),
        sample_status_mismatches=("evt-stale Gonzaga Bulldogs vs Saint Mary's Gaels",),
        sample_score_mismatches=("evt-score Arizona Wildcats vs Houston Cougars",),
        sample_context_mismatches=(),
    )
    assert fake_client.requested_dates == [date(2026, 1, 10)]


def test_verify_games_flags_context_mismatches(tmp_path) -> None:
    db_path = tmp_path / "verify_context.sqlite"
    create_verify_test_db(db_path)

    connection = sqlite3.connect(db_path)
    connection.executemany(
        """
        INSERT INTO teams (team_id, team_key, name)
        VALUES (?, ?, ?)
        """,
        [
            (1, "duke-blue-devils", "Duke Blue Devils"),
            (2, "north-carolina-tar-heels", "North Carolina Tar Heels"),
        ],
    )
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
            last_score_update,
            neutral_site,
            conference_competition,
            season_type,
            season_type_slug,
            tournament_id,
            event_note_headline,
            venue_id,
            venue_name,
            venue_city,
            venue_state,
            venue_indoor
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?
        )
        """,
        (
            1,
            2026,
            "2026-03-14",
            "2026-03-14T18:00:00+00:00",
            1,
            2,
            "evt-context",
            "basketball_ncaab",
            "NCAAM",
            "W",
            1,
            80,
            70,
            "2026-03-14T20:00:00+00:00",
            0,
            1,
            2,
            "regular-season",
            None,
            None,
            "123",
            "Cameron Indoor Stadium",
            "Durham",
            "NC",
            1,
        ),
    )
    connection.commit()
    connection.close()

    fake_client = FakeEspnClient(
        {
            date(2026, 3, 14): [
                sample_espn_event(
                    event_id="evt-context",
                    event_date="2026-03-14T18:00Z",
                    home_team="Duke Blue Devils",
                    away_team="North Carolina Tar Heels",
                    home_score="80",
                    away_score="70",
                    neutral_site=True,
                    conference_competition=False,
                    season_type=3,
                    season_type_slug="post-season",
                    tournament_id="777",
                    event_note_headline="ACC Tournament - Semifinal",
                    venue_id="456",
                    venue_name="Spectrum Center",
                    venue_city="Charlotte",
                    venue_state="NC",
                    venue_indoor=True,
                )
            ]
        }
    )

    summary = verify_games(
        options=VerificationOptions(
            start_date=date(2026, 3, 14),
            end_date=date(2026, 3, 14),
        ),
        database_url=f"sqlite+pysqlite:///{db_path}",
        client=fake_client,
        team_catalog=make_team_catalog(
            [
                ("Duke", "Duke Blue Devils", None),
                ("North Carolina", "North Carolina Tar Heels", None),
            ]
        ),
    )

    assert summary.games_present == 1
    assert summary.games_verified == 0
    assert summary.context_mismatches == 1
    assert summary.sample_context_mismatches == (
        "evt-context Duke Blue Devils vs North Carolina Tar Heels",
    )


def test_verify_games_falls_back_to_matchup_when_source_event_id_changes(
    tmp_path,
) -> None:
    db_path = tmp_path / "verify.sqlite"
    create_verify_test_db(db_path)

    connection = sqlite3.connect(db_path)
    connection.executemany(
        """
        INSERT INTO teams (team_id, team_key, name)
        VALUES (?, ?, ?)
        """,
        [
            (1, "duke-blue-devils", "Duke Blue Devils"),
            (2, "north-carolina-tar-heels", "North Carolina Tar Heels"),
        ],
    )
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
            last_score_update,
            neutral_site,
            conference_competition,
            season_type,
            season_type_slug,
            tournament_id,
            event_note_headline,
            venue_id,
            venue_name,
            venue_city,
            venue_state,
            venue_indoor
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?
        )
        """,
        (
            1,
            2026,
            "2026-01-10",
            "2026-01-10T20:00:00+00:00",
            1,
            2,
            "evt-old-id",
            "basketball_ncaab",
            "NCAAM",
            "W",
            1,
            81,
            77,
            "2026-01-10T22:00:00+00:00",
            0,
            1,
            2,
            "regular-season",
            None,
            None,
            "2171",
            "Cameron Indoor Stadium",
            "Durham",
            "NC",
            1,
        ),
    )
    connection.commit()
    connection.close()

    fake_client = FakeEspnClient(
        {
            date(2026, 1, 10): [
                sample_espn_event(
                    event_id="evt-new-id",
                    event_date="2026-01-10T20:00Z",
                    home_team="Duke Blue Devils",
                    away_team="North Carolina Tar Heels",
                    home_score="81",
                    away_score="77",
                    conference_competition=True,
                    venue_id="2171",
                    venue_name="Cameron Indoor Stadium",
                    venue_city="Durham",
                    venue_state="NC",
                    venue_indoor=True,
                )
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
            ]
        ),
    )

    assert summary.games_present == 1
    assert summary.games_verified == 1
    assert summary.games_missing == 0
    assert summary.status_mismatches == 0
    assert summary.score_mismatches == 0
    assert summary.context_mismatches == 0
