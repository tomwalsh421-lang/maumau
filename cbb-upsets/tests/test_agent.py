from datetime import UTC, date

import pytest

from cbb.agent import AgentSyncOptions, run_agent_sync
from cbb.ingest import ApiQuota, HistoricalIngestSummary
from cbb.ingest.models import OddsIngestSummary
from cbb.modeling import PredictionSummary


def test_run_agent_sync_refreshes_recent_espn_window_and_current_odds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        "cbb.agent.get_latest_ingest_checkpoint_date",
        lambda **_kwargs: date(2026, 3, 9),
    )
    monkeypatch.setattr(
        "cbb.agent.get_latest_completed_game_date",
        lambda **_kwargs: None,
    )

    def fake_ingest_historical_games(
        options: object,
        database_url: str | None = None,
    ) -> HistoricalIngestSummary:
        captured["historical_options"] = options
        captured["historical_database_url"] = database_url
        return HistoricalIngestSummary(
            sport="basketball_ncaab",
            start_date="2026-03-11",
            end_date="2026-03-13",
            dates_requested=3,
            dates_skipped=0,
            dates_completed=3,
            teams_seen=12,
            games_seen=18,
            games_inserted=16,
            games_skipped=2,
        )

    def fake_ingest_current_odds(
        options: object,
        database_url: str | None = None,
    ) -> OddsIngestSummary:
        captured["odds_options"] = options
        captured["odds_database_url"] = database_url
        return OddsIngestSummary(
            sport="basketball_ncaab",
            teams_seen=12,
            games_upserted=8,
            games_skipped=1,
            odds_snapshots_upserted=64,
            completed_games_updated=3,
            odds_quota=ApiQuota(remaining=1990, used=10, last_cost=10),
            scores_quota=ApiQuota(remaining=999, used=1, last_cost=1),
        )

    monkeypatch.setattr(
        "cbb.agent.ingest_historical_games",
        fake_ingest_historical_games,
    )
    monkeypatch.setattr("cbb.agent.ingest_current_odds", fake_ingest_current_odds)

    summary = run_agent_sync(
        AgentSyncOptions(
            espn_refresh_days=3,
            regions="us,uk",
            markets="h2h,spreads",
            bookmakers="draftkings,fanduel",
            scores_days_from=2,
            scan_bets=False,
        ),
        today=date(2026, 3, 13),
        database_url="postgresql://example",
    )

    historical_options = captured["historical_options"]
    odds_options = captured["odds_options"]

    assert summary.started_at.tzinfo == UTC
    assert summary.completed_at.tzinfo == UTC
    assert summary.espn_resume_anchor_date == date(2026, 3, 9)
    assert summary.espn_resume_anchor_source == "checkpoint"
    assert summary.espn_effective_start_date == date(2026, 3, 10)
    assert summary.espn_effective_end_date == date(2026, 3, 13)
    assert summary.effective_scores_days_from == 3
    assert captured["historical_database_url"] == "postgresql://example"
    assert captured["odds_database_url"] == "postgresql://example"
    assert historical_options.start_date == date(2026, 3, 10)
    assert historical_options.end_date == date(2026, 3, 13)
    assert historical_options.force_refresh is True
    assert odds_options.regions == "us,uk"
    assert odds_options.markets == "h2h,spreads"
    assert odds_options.bookmakers == "draftkings,fanduel"
    assert odds_options.days_from == 3


def test_run_agent_sync_rejects_disabled_sources() -> None:
    with pytest.raises(ValueError, match="At least one live refresh source"):
        run_agent_sync(
            AgentSyncOptions(
                refresh_espn=False,
                refresh_odds=False,
            ),
            today=date(2026, 3, 13),
        )


def test_run_agent_sync_falls_back_to_recent_window_without_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        "cbb.agent.get_latest_ingest_checkpoint_date",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        "cbb.agent.get_latest_completed_game_date",
        lambda **_kwargs: None,
    )

    def fake_ingest_historical_games(
        options: object,
        database_url: str | None = None,
    ) -> HistoricalIngestSummary:
        captured["historical_options"] = options
        return HistoricalIngestSummary(
            sport="basketball_ncaab",
            start_date="2026-03-11",
            end_date="2026-03-13",
            dates_requested=3,
            dates_skipped=0,
            dates_completed=3,
            teams_seen=12,
            games_seen=18,
            games_inserted=16,
            games_skipped=2,
        )

    monkeypatch.setattr(
        "cbb.agent.ingest_historical_games",
        fake_ingest_historical_games,
    )
    monkeypatch.setattr(
        "cbb.agent.ingest_current_odds",
        lambda *args, **kwargs: OddsIngestSummary(
            sport="basketball_ncaab",
            teams_seen=0,
            games_upserted=0,
            games_skipped=0,
            odds_snapshots_upserted=0,
            completed_games_updated=0,
            odds_quota=ApiQuota(remaining=2000, used=0, last_cost=0),
        ),
    )

    summary = run_agent_sync(
        AgentSyncOptions(
            espn_refresh_days=3,
            scores_days_from=1,
            scan_bets=False,
        ),
        today=date(2026, 3, 13),
    )

    historical_options = captured["historical_options"]

    assert summary.espn_resume_anchor_date is None
    assert summary.espn_resume_anchor_source == "recent_window"
    assert summary.espn_effective_start_date == date(2026, 3, 11)
    assert summary.effective_scores_days_from == 3
    assert historical_options.start_date == date(2026, 3, 11)


def test_run_agent_sync_scans_upcoming_bets_after_refresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        "cbb.agent.get_latest_ingest_checkpoint_date",
        lambda **_kwargs: date(2026, 3, 12),
    )
    monkeypatch.setattr(
        "cbb.agent.ingest_historical_games",
        lambda *args, **kwargs: HistoricalIngestSummary(
            sport="basketball_ncaab",
            start_date="2026-03-13",
            end_date="2026-03-13",
            dates_requested=1,
            dates_skipped=0,
            dates_completed=1,
            teams_seen=4,
            games_seen=2,
            games_inserted=2,
            games_skipped=0,
        ),
    )
    monkeypatch.setattr(
        "cbb.agent.ingest_current_odds",
        lambda *args, **kwargs: OddsIngestSummary(
            sport="basketball_ncaab",
            teams_seen=4,
            games_upserted=2,
            games_skipped=0,
            odds_snapshots_upserted=16,
            completed_games_updated=1,
            odds_quota=ApiQuota(remaining=1990, used=10, last_cost=10),
        ),
    )

    def fake_predict_best_bets(options: object) -> PredictionSummary:
        captured["prediction_options"] = options
        return PredictionSummary(
            market="best",
            available_games=8,
            candidates_considered=3,
            bets_placed=1,
            recommendations=[],
            artifact_name="latest",
        )

    monkeypatch.setattr("cbb.agent.predict_best_bets", fake_predict_best_bets)

    summary = run_agent_sync(
        AgentSyncOptions(
            artifact_name="latest",
            bankroll=2500.0,
            limit=4,
        ),
        today=date(2026, 3, 13),
        database_url="postgresql://example",
    )

    prediction_options = captured["prediction_options"]
    assert prediction_options.market == "best"
    assert prediction_options.artifact_name == "latest"
    assert prediction_options.bankroll == 2500.0
    assert prediction_options.limit == 4
    assert prediction_options.database_url == "postgresql://example"
    assert summary.prediction_summary is not None
    assert summary.prediction_summary.available_games == 8
    assert summary.prediction_error is None
