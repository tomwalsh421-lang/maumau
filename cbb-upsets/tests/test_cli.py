from typer.testing import CliRunner

from cbb.cli import app
from cbb.ingest import HistoricalIngestOptions, HistoricalIngestSummary


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
