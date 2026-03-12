import json
import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from cbb.db import get_availability_shadow_summary
from cbb.ingest.availability import (
    OfficialAvailabilityImportSummary,
    ingest_official_availability_reports,
)
from cbb.ingest.clients.ncaa import (
    OFFICIAL_NCAA_AVAILABILITY_SOURCE,
    expand_official_ncaa_capture_paths,
    load_official_ncaa_availability_capture,
)

FIXTURE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "availability"
    / "official_ncaa_availability_capture.json"
)


def create_import_test_db(path: Path) -> None:
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
        VALUES (1, 'duke', '150', 'Duke Blue Devils')
        """
    )
    connection.execute(
        """
        INSERT INTO teams (team_id, team_key, ncaa_team_code, name)
        VALUES (2, 'north-carolina', '153', 'North Carolina Tar Heels')
        """
    )
    connection.execute(
        """
        INSERT INTO team_aliases (team_alias_id, team_id, alias_key, alias_name)
        VALUES (1, 1, 'duke-blue-devils', 'Duke Blue Devils')
        """
    )
    connection.execute(
        """
        INSERT INTO team_aliases (team_alias_id, team_id, alias_key, alias_name)
        VALUES (2, 2, 'north-carolina-tar-heels', 'North Carolina Tar Heels')
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
            '2026-03-19',
            '2026-03-19T23:30:00+00:00',
            1,
            2,
            '401729842',
            '401729842',
            'postseason'
        )
        """
    )
    connection.commit()
    connection.close()


def test_load_official_ncaa_availability_capture_parses_fixture() -> None:
    report = load_official_ncaa_availability_capture(FIXTURE_PATH)

    assert report.source_name == OFFICIAL_NCAA_AVAILABILITY_SOURCE
    assert report.source_url.endswith("/availability-report")
    assert report.captured_at == "2026-03-19T01:12:00+00:00"
    assert report.published_at == "2026-03-19T01:00:00+00:00"
    assert report.effective_at == "2026-03-19T23:30:00+00:00"
    assert report.game.ncaa_game_code == "401729842"
    assert report.game.home_team.name == "Duke Blue Devils"
    assert report.game.away_team.ncaa_team_code == "153"
    assert [row.player_name for row in report.rows] == ["Mason Hale", "Evan Cole"]
    assert [row.status for row in report.rows] == ["out", "questionable"]


def test_expand_official_ncaa_capture_paths_sorts_directory_contents(
    tmp_path: Path,
) -> None:
    first_path = tmp_path / "a.json"
    second_path = tmp_path / "nested" / "b.json"
    second_path.parent.mkdir()

    fixture_bytes = FIXTURE_PATH.read_bytes()
    first_path.write_bytes(fixture_bytes)
    second_path.write_bytes(fixture_bytes)

    expanded_paths = expand_official_ncaa_capture_paths([tmp_path])

    assert expanded_paths == (first_path.resolve(), second_path.resolve())


def test_load_official_ncaa_availability_capture_rejects_unknown_status(
    tmp_path: Path,
) -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    payload["report"]["statuses"][0]["status"] = "probable"
    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported availability status"):
        load_official_ncaa_availability_capture(invalid_path)


def test_ingest_official_availability_reports_loads_sorted_reports(
    tmp_path: Path,
) -> None:
    first_path = tmp_path / "b.json"
    second_path = tmp_path / "a.json"
    fixture_bytes = FIXTURE_PATH.read_bytes()
    first_path.write_bytes(fixture_bytes)
    second_path.write_bytes(fixture_bytes)
    captured: dict[str, object] = {}

    def fake_persist_reports(
        reports,
        *,
        database_url: str | None = None,
    ) -> OfficialAvailabilityImportSummary:
        captured["paths"] = [report.source_path.name for report in reports]
        captured["database_url"] = database_url
        return OfficialAvailabilityImportSummary(
            snapshots_imported=2,
            player_rows_imported=4,
            games_matched=2,
            teams_matched=4,
            rows_unmatched=0,
            duplicates_skipped=1,
        )

    summary = ingest_official_availability_reports(
        [tmp_path],
        database_url="sqlite+pysqlite:///availability.sqlite",
        persist_reports=fake_persist_reports,
    )

    assert captured["paths"] == ["a.json", "b.json"]
    assert captured["database_url"] == "sqlite+pysqlite:///availability.sqlite"
    assert summary == OfficialAvailabilityImportSummary(
        snapshots_imported=2,
        player_rows_imported=4,
        games_matched=2,
        teams_matched=4,
        rows_unmatched=0,
        duplicates_skipped=1,
    )


def test_ingest_official_availability_reports_persists_shadow_data(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "availability.sqlite"
    create_import_test_db(db_path)
    database_url = f"sqlite+pysqlite:///{db_path}"

    summary = ingest_official_availability_reports(
        [FIXTURE_PATH],
        database_url=database_url,
    )

    assert summary == OfficialAvailabilityImportSummary(
        snapshots_imported=1,
        player_rows_imported=2,
        games_matched=1,
        teams_matched=2,
        rows_unmatched=0,
        duplicates_skipped=0,
    )

    engine = create_engine(database_url, future=True)
    with engine.connect() as connection:
        report_row = connection.execute(
            text(
                """
                SELECT
                    source_report_id,
                    game_id,
                    team_id,
                    linkage_status
                FROM ncaa_tournament_availability_reports
                """
            )
        ).mappings().one()
        status_rows = connection.execute(
            text(
                """
                SELECT raw_team_name, team_id, status_key
                FROM ncaa_tournament_availability_player_statuses
                ORDER BY row_order
                """
            )
        ).mappings().all()

    assert report_row["source_report_id"] == "401729842"
    assert report_row["game_id"] == 10
    assert report_row["team_id"] == 1
    assert report_row["linkage_status"] == "matched"
    assert status_rows == [
        {
            "raw_team_name": "Duke Blue Devils",
            "team_id": 1,
            "status_key": "out",
        },
        {
            "raw_team_name": "North Carolina Tar Heels",
            "team_id": 2,
            "status_key": "questionable",
        },
    ]

    shadow_summary = get_availability_shadow_summary(database_url)
    assert shadow_summary.reports_loaded == 1
    assert shadow_summary.player_rows_loaded == 2
    assert shadow_summary.games_covered == 1
    assert shadow_summary.matched_player_rows == 2
    assert shadow_summary.unmatched_player_rows == 0
    assert shadow_summary.seasons == (2026,)
    assert shadow_summary.scope_labels == ("postseason",)
    assert shadow_summary.source_labels == ("official_ncaa_availability",)
    assert [status.status for status in shadow_summary.status_counts] == [
        "out",
        "questionable",
    ]


def test_ingest_official_availability_reports_skips_exact_duplicates(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "duplicate-availability.sqlite"
    create_import_test_db(db_path)
    database_url = f"sqlite+pysqlite:///{db_path}"

    first_summary = ingest_official_availability_reports(
        [FIXTURE_PATH],
        database_url=database_url,
    )
    second_summary = ingest_official_availability_reports(
        [FIXTURE_PATH],
        database_url=database_url,
    )

    assert first_summary.snapshots_imported == 1
    assert second_summary == OfficialAvailabilityImportSummary(
        snapshots_imported=0,
        player_rows_imported=0,
        games_matched=0,
        teams_matched=0,
        rows_unmatched=0,
        duplicates_skipped=1,
    )
