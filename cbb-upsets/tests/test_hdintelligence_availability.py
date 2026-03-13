import sqlite3
from pathlib import Path

from sqlalchemy import create_engine, text

from cbb.db import get_availability_shadow_summary
from cbb.ingest.availability import ingest_official_availability_reports
from cbb.ingest.clients.availability_loader import load_official_availability_captures

FIXTURE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "availability"
    / "big12_mbb_availability_archive_capture.json"
)


def create_archive_import_test_db(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE teams (
            team_id INTEGER PRIMARY KEY,
            team_key TEXT NOT NULL UNIQUE,
            ncaa_team_code TEXT,
            name TEXT NOT NULL
        );

        CREATE TABLE team_aliases (
            team_alias_id INTEGER PRIMARY KEY,
            team_id INTEGER NOT NULL,
            alias_key TEXT NOT NULL UNIQUE,
            alias_name TEXT NOT NULL
        );

        CREATE TABLE games (
            game_id INTEGER PRIMARY KEY,
            season INTEGER NOT NULL,
            date TEXT NOT NULL,
            commence_time TEXT,
            team1_id INTEGER NOT NULL,
            team2_id INTEGER NOT NULL,
            ncaa_game_code TEXT,
            source_event_id TEXT,
            season_type_slug TEXT,
            UNIQUE (season, date, team1_id, team2_id)
        );

        CREATE TABLE ncaa_tournament_availability_reports (
            availability_report_id INTEGER PRIMARY KEY,
            source_name TEXT NOT NULL,
            source_url TEXT,
            source_report_id TEXT,
            source_dedupe_key TEXT NOT NULL,
            source_content_sha256 TEXT NOT NULL,
            reported_at TEXT,
            effective_at TEXT,
            captured_at TEXT NOT NULL,
            imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            game_id INTEGER,
            team_id INTEGER,
            linkage_status TEXT NOT NULL,
            linkage_notes TEXT,
            raw_team_name TEXT,
            raw_opponent_name TEXT,
            raw_matchup_label TEXT,
            payload TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(source_name, source_dedupe_key)
        );

        CREATE TABLE ncaa_tournament_availability_player_statuses (
            availability_player_status_id INTEGER PRIMARY KEY,
            availability_report_id INTEGER NOT NULL,
            source_item_key TEXT NOT NULL,
            source_content_sha256 TEXT NOT NULL,
            row_order INTEGER,
            source_player_id TEXT,
            team_id INTEGER,
            raw_team_name TEXT,
            player_name TEXT NOT NULL,
            player_name_key TEXT,
            status_key TEXT NOT NULL,
            status_label TEXT,
            status_detail TEXT,
            source_updated_at TEXT,
            expected_return TEXT,
            payload TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(availability_report_id, source_item_key)
        );
        """
    )
    connection.execute(
        """
        INSERT INTO teams (team_id, team_key, ncaa_team_code, name)
        VALUES (1, 'arizona-state', NULL, 'Arizona State Sun Devils')
        """
    )
    connection.execute(
        """
        INSERT INTO teams (team_id, team_key, ncaa_team_code, name)
        VALUES (2, 'arizona', NULL, 'Arizona Wildcats')
        """
    )
    connection.execute(
        """
        INSERT INTO team_aliases (team_alias_id, team_id, alias_key, alias_name)
        VALUES (1, 1, 'arizona-st', 'Arizona St.')
        """
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
            ncaa_game_code,
            source_event_id,
            season_type_slug
        )
        VALUES (
            10,
            2026,
            '2026-01-14',
            '2026-01-15T02:00:00+00:00',
            1,
            2,
            NULL,
            NULL,
            'regular-season'
        )
        """
    )
    connection.commit()
    connection.close()


def test_load_official_availability_captures_parses_big12_archive_fixture() -> None:
    reports = load_official_availability_captures(FIXTURE_PATH)

    assert len(reports) == 4
    assert {report.source_name for report in reports} == {
        "big12_mbb_availability_archive"
    }
    assert {report.published_at for report in reports} == {None}
    assert {report.game.scheduled_start for report in reports} == {
        "2026-01-14T00:00:00+00:00"
    }
    assert {
        (report.game.home_team.name, report.game.away_team.name)
        for report in reports
    } == {("Arizona St.", "Arizona")}

    initial_report = next(
        report
        for report in reports
        if report.game.source_event_id is not None
        and ":initial:" in report.game.source_event_id
        and report.rows[0].team.name == "Arizona St."
    )
    assert [row.player_name for row in initial_report.rows] == [
        "Adante Holiman",
        "Bryce Ford",
    ]
    assert [row.status for row in initial_report.rows] == ["out", "questionable"]
    assert [row.jersey_number for row in initial_report.rows] == ["3", "4"]

    arizona_initial = next(
        report
        for report in reports
        if report.game.source_event_id is not None
        and ":initial:" in report.game.source_event_id
        and report.rows[0].team.name == "Arizona"
    )
    assert [row.status for row in arizona_initial.rows] == ["probable"]


def test_ingest_official_availability_reports_persists_big12_archive_fixture(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "availability.sqlite"
    create_archive_import_test_db(db_path)
    database_url = f"sqlite+pysqlite:///{db_path}"

    summary = ingest_official_availability_reports(
        [FIXTURE_PATH],
        database_url=database_url,
    )

    assert summary.snapshots_imported == 4
    assert summary.player_rows_imported == 6
    assert summary.games_matched == 4
    assert summary.teams_matched == 4
    assert summary.rows_unmatched == 0
    assert summary.duplicates_skipped == 0

    availability_summary = get_availability_shadow_summary(database_url)
    assert availability_summary.reports_loaded == 4
    assert availability_summary.player_rows_loaded == 6
    assert availability_summary.games_covered == 1
    assert availability_summary.source_labels == ("big12_mbb_availability_archive",)
    assert availability_summary.latest_update_at is None
    assert availability_summary.average_minutes_before_tip is None
    assert availability_summary.latest_minutes_before_tip is None

    engine = create_engine(database_url)
    with engine.connect() as connection:
        report_rows = connection.execute(
            text(
                """
                SELECT raw_team_name, raw_opponent_name, linkage_status
                FROM ncaa_tournament_availability_reports
                ORDER BY availability_report_id
                """
            )
        ).mappings()
        assert sorted(tuple(row.values()) for row in report_rows) == sorted([
            ("Arizona St.", "Arizona", "matched"),
            ("Arizona St.", "Arizona", "matched"),
            ("Arizona", "Arizona St.", "matched"),
            ("Arizona", "Arizona St.", "matched"),
        ])

        status_rows = connection.execute(
            text(
                """
                SELECT status_key, COUNT(*) AS row_count
                FROM ncaa_tournament_availability_player_statuses
                GROUP BY status_key
                ORDER BY status_key
                """
            )
        ).mappings()
        assert [tuple(row.values()) for row in status_rows] == [
            ("available", 2),
            ("out", 2),
            ("probable", 1),
            ("questionable", 1),
        ]
