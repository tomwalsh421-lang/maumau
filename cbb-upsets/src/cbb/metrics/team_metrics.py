from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text

from cbb.db import get_engine


TEAM_METRICS_SQL = text(
    """
    WITH team_games AS (
        SELECT
            team1_id AS team_id,
            CASE result
                WHEN 'W' THEN 1
                WHEN 'L' THEN 0
            END AS win
        FROM games
        WHERE season = :season
          AND result IN ('W', 'L')

        UNION ALL

        SELECT
            team2_id AS team_id,
            CASE result
                WHEN 'L' THEN 1
                WHEN 'W' THEN 0
            END AS win
        FROM games
        WHERE season = :season
          AND result IN ('W', 'L')
    ),
    aggregated AS (
        SELECT
            team_id,
            COUNT(*) AS games_played,
            SUM(win) AS wins
        FROM team_games
        GROUP BY team_id
    )
    SELECT
        team_id,
        games_played,
        wins,
        games_played - wins AS losses,
        ROUND(CAST(wins AS FLOAT) / games_played, 4) AS win_pct
    FROM aggregated
    ORDER BY team_id
    """
)

UPSERT_TEAM_METRIC_SQL = text(
    """
    INSERT INTO team_metrics (season, team_id, win_pct, point_diff, seed)
    VALUES (:season, :team_id, :win_pct, :point_diff, :seed)
    ON CONFLICT (season, team_id) DO UPDATE SET
        win_pct = excluded.win_pct,
        point_diff = excluded.point_diff,
        seed = excluded.seed
    """
)


@dataclass(frozen=True)
class TeamMetricSummary:
    season: int
    team_id: int
    games_played: int
    wins: int
    losses: int
    win_pct: float
    point_diff: float | None = None
    seed: int | None = None


def compute_team_metrics(season: int, database_url: str | None = None) -> list[TeamMetricSummary]:
    engine = get_engine(database_url)

    with engine.begin() as connection:
        rows = connection.execute(TEAM_METRICS_SQL, {"season": season}).mappings().all()
        metrics = [
            TeamMetricSummary(
                season=season,
                team_id=int(row["team_id"]),
                games_played=int(row["games_played"]),
                wins=int(row["wins"]),
                losses=int(row["losses"]),
                win_pct=float(row["win_pct"]),
            )
            for row in rows
        ]

        for metric in metrics:
            connection.execute(
                UPSERT_TEAM_METRIC_SQL,
                {
                    "season": metric.season,
                    "team_id": metric.team_id,
                    "win_pct": metric.win_pct,
                    "point_diff": metric.point_diff,
                    "seed": metric.seed,
                },
            )

    return metrics
