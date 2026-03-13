import hashlib
import sqlite3

import orjson
import pytest
from sqlalchemy import create_engine, text

from cbb.ingest.models import NcaaTournamentAvailabilityPersistenceSummary
from cbb.ingest.persistence import (
    NcaaTournamentAvailabilityPlayerStatusRecord,
    NcaaTournamentAvailabilityReportRecord,
    upsert_ncaa_tournament_availability_report,
)


def create_availability_test_db(path) -> None:
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
            '2026-03-20',
            '2026-03-20T23:30:00+00:00',
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


def test_upsert_ncaa_tournament_availability_report_is_idempotent(
    tmp_path,
) -> None:
    db_path = tmp_path / "availability.sqlite"
    create_availability_test_db(db_path)
    engine = create_engine(f"sqlite+pysqlite:///{db_path}", future=True)

    report_payload = {
        "matchup": "North Carolina Tar Heels vs Duke Blue Devils",
        "items": [
            {"player": "Tyrese Proctor", "status": "out"},
            {"player": "Cooper Flagg", "status": "questionable"},
        ],
    }
    player_statuses = [
        NcaaTournamentAvailabilityPlayerStatusRecord(
            source_item_key="tyrese-proctor",
            player_name="Tyrese Proctor",
            player_name_key="tyrese-proctor",
            status_key="out",
            status_label="Out",
            status_detail="Left knee",
            source_updated_at="2026-03-20T11:58:00Z",
            payload={"player": "Tyrese Proctor", "status": "Out"},
            row_order=1,
        ),
        NcaaTournamentAvailabilityPlayerStatusRecord(
            source_item_key="cooper-flagg",
            player_name="Cooper Flagg",
            player_name_key="cooper-flagg",
            status_key="questionable",
            status_label="Questionable",
            status_detail="Ankle",
            source_updated_at="2026-03-20T11:59:00Z",
            expected_return="Game-time decision",
            payload={"player": "Cooper Flagg", "status": "Questionable"},
            row_order=2,
        ),
    ]
    report = NcaaTournamentAvailabilityReportRecord(
        source_name="ncaa_tournament_official",
        source_url="https://www.ncaa.com/news/basketball-men/article/report",
        source_report_id="report-2026-03-20-duke",
        source_dedupe_key="2026-03-20-duke-vs-unc",
        reported_at="2026-03-20T12:00:00Z",
        effective_at="2026-03-20T23:30:00Z",
        captured_at="2026-03-20T12:05:00Z",
        imported_at="2026-03-20T12:06:00Z",
        game_id=10,
        team_id=1,
        payload=report_payload,
        player_statuses=player_statuses,
        raw_team_name="Duke Blue Devils",
        raw_opponent_name="North Carolina Tar Heels",
        raw_matchup_label="North Carolina Tar Heels at Duke Blue Devils",
    )

    with engine.begin() as connection:
        summary = upsert_ncaa_tournament_availability_report(connection, report)
        rerun_summary = upsert_ncaa_tournament_availability_report(connection, report)
        report_count = connection.execute(
            text("SELECT COUNT(*) FROM ncaa_tournament_availability_reports")
        ).scalar_one()
        status_count = connection.execute(
            text(
                "SELECT COUNT(*) "
                "FROM ncaa_tournament_availability_player_statuses"
            )
        ).scalar_one()
        report_row = connection.execute(
            text(
                """
                SELECT
                    source_content_sha256,
                    payload,
                    effective_at,
                    captured_at,
                    imported_at,
                    linkage_status
                FROM ncaa_tournament_availability_reports
                """
            )
        ).mappings().one()
        status_rows = connection.execute(
            text(
                """
                SELECT
                    source_item_key,
                    source_content_sha256,
                    status_key,
                    payload,
                    source_updated_at
                FROM ncaa_tournament_availability_player_statuses
                ORDER BY row_order
                """
            )
        ).mappings().all()

    expected_payload = orjson.dumps(
        report_payload,
        option=orjson.OPT_SORT_KEYS,
    ).decode("utf-8")
    expected_item_payload = orjson.dumps(
        {"player": "Tyrese Proctor", "status": "Out"},
        option=orjson.OPT_SORT_KEYS,
    ).decode("utf-8")

    assert summary == NcaaTournamentAvailabilityPersistenceSummary(
        reports_upserted=1,
        player_status_rows_upserted=2,
        unmatched_reports_upserted=0,
    )
    assert rerun_summary == summary
    assert report_count == 1
    assert status_count == 2
    assert report_row["payload"] == expected_payload
    assert report_row["effective_at"] == "2026-03-20T23:30:00+00:00"
    assert report_row["captured_at"] == "2026-03-20T12:05:00+00:00"
    assert report_row["imported_at"] == "2026-03-20T12:06:00+00:00"
    assert report_row["linkage_status"] == "matched"
    assert report_row["source_content_sha256"] == hashlib.sha256(
        expected_payload.encode("utf-8")
    ).hexdigest()
    assert [row["source_item_key"] for row in status_rows] == [
        "tyrese-proctor",
        "cooper-flagg",
    ]
    assert status_rows[0]["status_key"] == "out"
    assert status_rows[0]["payload"] == expected_item_payload
    assert status_rows[0]["source_updated_at"] == "2026-03-20T11:58:00+00:00"
    assert status_rows[0]["source_content_sha256"] == hashlib.sha256(
        expected_item_payload.encode("utf-8")
    ).hexdigest()


def test_upsert_ncaa_tournament_availability_report_keeps_unmatched_linkage(
    tmp_path,
) -> None:
    db_path = tmp_path / "unmatched-availability.sqlite"
    create_availability_test_db(db_path)
    engine = create_engine(f"sqlite+pysqlite:///{db_path}", future=True)

    initial_report = NcaaTournamentAvailabilityReportRecord(
        source_name="ncaa_tournament_official",
        source_dedupe_key="2026-03-21-sju-vcu",
        captured_at="2026-03-21T10:00:00Z",
        reported_at="2026-03-21T09:55:00Z",
        effective_at="2026-03-21T17:00:00Z",
        payload={"team": "Saint Joseph's Hawks", "items": 2},
        player_statuses=[
            NcaaTournamentAvailabilityPlayerStatusRecord(
                source_item_key="erik-reynolds",
                player_name="Erik Reynolds II",
                status_key="out",
                status_detail="Hand",
                source_updated_at="2026-03-21T09:52:00Z",
                payload={"player": "Erik Reynolds II", "status": "Out"},
                row_order=1,
            ),
            NcaaTournamentAvailabilityPlayerStatusRecord(
                source_item_key="rasheer-fleming",
                player_name="Rasheer Fleming",
                status_key="available",
                source_updated_at="2026-03-21T09:53:00Z",
                payload={"player": "Rasheer Fleming", "status": "Available"},
                row_order=2,
            ),
        ],
        linkage_status="game_unmatched",
        linkage_notes="Bracket matchup not yet linked to canonical game",
        raw_team_name="Saint Joseph's Hawks",
        raw_opponent_name="VCU Rams",
        raw_matchup_label="VCU Rams vs Saint Joseph's Hawks",
    )
    updated_report = NcaaTournamentAvailabilityReportRecord(
        source_name="ncaa_tournament_official",
        source_dedupe_key="2026-03-21-sju-vcu",
        captured_at="2026-03-21T10:30:00Z",
        reported_at="2026-03-21T10:25:00Z",
        effective_at="2026-03-21T17:05:00Z",
        payload={"team": "Saint Joseph's Hawks", "items": 1},
        player_statuses=[
            NcaaTournamentAvailabilityPlayerStatusRecord(
                source_item_key="erik-reynolds",
                player_name="Erik Reynolds II",
                status_key="doubtful",
                status_detail="Warmups only",
                source_updated_at="2026-03-21T10:20:00Z",
                payload={"player": "Erik Reynolds II", "status": "Doubtful"},
                row_order=1,
            )
        ],
        linkage_status="game_unmatched",
        linkage_notes="Waiting for manual game reconciliation",
        raw_team_name="Saint Joseph's Hawks",
        raw_opponent_name="VCU Rams",
        raw_matchup_label="VCU Rams vs Saint Joseph's Hawks",
    )

    with engine.begin() as connection:
        first_summary = upsert_ncaa_tournament_availability_report(
            connection,
            initial_report,
        )
        second_summary = upsert_ncaa_tournament_availability_report(
            connection,
            updated_report,
        )
        report_row = connection.execute(
            text(
                """
                SELECT
                    game_id,
                    team_id,
                    linkage_status,
                    linkage_notes,
                    raw_team_name,
                    raw_opponent_name,
                    raw_matchup_label,
                    effective_at
                FROM ncaa_tournament_availability_reports
                """
            )
        ).mappings().one()
        status_rows = connection.execute(
            text(
                """
                SELECT
                    source_item_key,
                    status_key,
                    status_detail,
                    source_updated_at
                FROM ncaa_tournament_availability_player_statuses
                ORDER BY row_order
                """
            )
        ).mappings().all()

    assert first_summary == NcaaTournamentAvailabilityPersistenceSummary(
        reports_upserted=1,
        player_status_rows_upserted=2,
        unmatched_reports_upserted=1,
    )
    assert second_summary == NcaaTournamentAvailabilityPersistenceSummary(
        reports_upserted=1,
        player_status_rows_upserted=1,
        unmatched_reports_upserted=1,
    )
    assert report_row["game_id"] is None
    assert report_row["team_id"] is None
    assert report_row["linkage_status"] == "game_unmatched"
    assert report_row["linkage_notes"] == "Waiting for manual game reconciliation"
    assert report_row["raw_team_name"] == "Saint Joseph's Hawks"
    assert report_row["raw_opponent_name"] == "VCU Rams"
    assert report_row["raw_matchup_label"] == "VCU Rams vs Saint Joseph's Hawks"
    assert report_row["effective_at"] == "2026-03-21T17:05:00+00:00"
    assert status_rows == [
        {
            "source_item_key": "erik-reynolds",
            "status_key": "doubtful",
            "status_detail": "Warmups only",
            "source_updated_at": "2026-03-21T10:20:00+00:00",
        }
    ]


def test_upsert_ncaa_tournament_availability_report_rejects_duplicate_item_keys(
    tmp_path,
) -> None:
    db_path = tmp_path / "duplicate-availability.sqlite"
    create_availability_test_db(db_path)
    engine = create_engine(f"sqlite+pysqlite:///{db_path}", future=True)

    report = NcaaTournamentAvailabilityReportRecord(
        source_name="ncaa_tournament_official",
        source_dedupe_key="2026-03-22-duplicate-keys",
        captured_at="2026-03-22T11:00:00Z",
        payload={"team": "Duke Blue Devils"},
        player_statuses=[
            NcaaTournamentAvailabilityPlayerStatusRecord(
                source_item_key="duplicate-key",
                player_name="Player One",
                status_key="out",
                payload={"player": "Player One"},
            ),
            NcaaTournamentAvailabilityPlayerStatusRecord(
                source_item_key="duplicate-key",
                player_name="Player Two",
                status_key="available",
                payload={"player": "Player Two"},
            ),
        ],
    )

    with engine.begin() as connection:
        with pytest.raises(ValueError, match="unique source_item_key"):
            upsert_ncaa_tournament_availability_report(connection, report)
        report_count = connection.execute(
            text("SELECT COUNT(*) FROM ncaa_tournament_availability_reports")
        ).scalar_one()

    assert report_count == 0
