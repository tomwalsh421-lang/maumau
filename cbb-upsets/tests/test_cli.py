from typer.testing import CliRunner

from cbb.cli import app
from cbb.ingest import (
    ApiQuota,
    ClosingOddsIngestOptions,
    ClosingOddsIngestSummary,
    HistoricalIngestOptions,
    HistoricalIngestSummary,
)


runner = CliRunner()


def test_ingest_data_command_defaults_to_three_year_backfill(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_ingest_historical_games(**kwargs: object) -> HistoricalIngestSummary:
        captured.update(kwargs)
        return HistoricalIngestSummary(
            sport="basketball_ncaab",
            start_date="2023-03-07",
            end_date="2026-03-07",
            dates_requested=100,
            dates_skipped=50,
            dates_completed=100,
            teams_seen=200,
            games_seen=300,
            games_inserted=250,
        )

    monkeypatch.setattr("cbb.cli.ingest_historical_games", fake_ingest_historical_games)

    result = runner.invoke(app, ["ingest-data"])

    assert result.exit_code == 0
    options = captured["options"]
    assert isinstance(options, HistoricalIngestOptions)
    assert options.years_back == 3
    assert options.start_date is None
    assert options.end_date is None
    assert options.force_refresh is False
    assert "range=2023-03-07..2026-03-07" in result.stdout
    assert "dates_requested=100" in result.stdout


def test_ingest_closing_odds_command_defaults_to_one_year_backfill(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_ingest_closing_odds(**kwargs: object) -> ClosingOddsIngestSummary:
        captured.update(kwargs)
        return ClosingOddsIngestSummary(
            sport="basketball_ncaab",
            market="h2h",
            start_date="2025-03-07",
            end_date="2026-03-07",
            snapshot_slots_found=12,
            snapshot_slots_requested=4,
            snapshot_slots_skipped=6,
            snapshot_slots_deferred=2,
            games_considered=40,
            games_matched=16,
            games_unmatched=3,
            odds_snapshots_upserted=16,
            credits_spent=40,
            quota=ApiQuota(remaining=1960, used=40, last_cost=10),
        )

    monkeypatch.setattr("cbb.cli.run_ingest_closing_odds", fake_ingest_closing_odds)

    result = runner.invoke(app, ["ingest-closing-odds"])

    assert result.exit_code == 0
    options = captured["options"]
    assert isinstance(options, ClosingOddsIngestOptions)
    assert options.years_back == 1
    assert options.market == "h2h"
    assert options.max_snapshots is None
    assert "range=2025-03-07..2026-03-07" in result.stdout
    assert "snapshot_slots_requested=4" in result.stdout
    assert "credits_spent=40" in result.stdout
