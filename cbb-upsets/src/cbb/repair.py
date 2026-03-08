"""Database repair workflow for canonical D1 team normalization."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import bindparam, inspect, text
from sqlalchemy.engine import Connection

from cbb.db import get_engine
from cbb.team_catalog import (
    TeamCatalog,
    load_team_catalog,
    resolve_team_id,
    seed_team_catalog,
)

FETCH_TEAMS_SQL = text(
    """
    SELECT team_id, team_key, name
    FROM teams
    ORDER BY team_id
    """
)

FETCH_GAMES_SQL = text(
    """
    SELECT
        game_id,
        season,
        date,
        team1_id,
        team2_id,
        source_event_id,
        completed,
        home_score,
        away_score,
        last_score_update
    FROM games
    ORDER BY game_id
    """
)

FETCH_GAMES_FOR_TEAM_IDS_SQL = text(
    """
    SELECT game_id
    FROM games
    WHERE team1_id IN :team_ids OR team2_id IN :team_ids
    """
).bindparams(bindparam("team_ids", expanding=True))

DELETE_ODDS_FOR_GAMES_SQL = text(
    """
    DELETE FROM odds_snapshots
    WHERE game_id IN :game_ids
    """
).bindparams(bindparam("game_ids", expanding=True))

DELETE_PREDICTIONS_FOR_GAMES_SQL = text(
    """
    DELETE FROM predictions
    WHERE game_id IN :game_ids
    """
).bindparams(bindparam("game_ids", expanding=True))

DELETE_GAMES_SQL = text(
    """
    DELETE FROM games
    WHERE game_id IN :game_ids
    """
).bindparams(bindparam("game_ids", expanding=True))

DELETE_TEAM_METRICS_SQL = text(
    """
    DELETE FROM team_metrics
    WHERE team_id IN :team_ids
    """
).bindparams(bindparam("team_ids", expanding=True))

UPDATE_GAME_TEAMS_SQL = text(
    """
    UPDATE games
    SET team1_id = :team1_id,
        team2_id = :team2_id
    WHERE game_id = :game_id
    """
)

UPDATE_GAME_SOURCE_EVENT_SQL = text(
    """
    UPDATE games
    SET source_event_id = :source_event_id
    WHERE game_id = :game_id
    """
)

MERGE_ODDS_SNAPSHOTS_SQL = text(
    """
    INSERT INTO odds_snapshots (
        game_id,
        bookmaker_key,
        bookmaker_title,
        market_key,
        captured_at,
        is_closing_line,
        team1_price,
        team2_price,
        team1_point,
        team2_point,
        over_price,
        under_price,
        total_points,
        payload
    )
    SELECT
        :to_game_id,
        bookmaker_key,
        bookmaker_title,
        market_key,
        captured_at,
        is_closing_line,
        team1_price,
        team2_price,
        team1_point,
        team2_point,
        over_price,
        under_price,
        total_points,
        payload
    FROM odds_snapshots
    WHERE game_id = :from_game_id
    ON CONFLICT (game_id, bookmaker_key, market_key, captured_at) DO UPDATE SET
        bookmaker_title = excluded.bookmaker_title,
        is_closing_line = odds_snapshots.is_closing_line OR excluded.is_closing_line,
        team1_price = excluded.team1_price,
        team2_price = excluded.team2_price,
        team1_point = excluded.team1_point,
        team2_point = excluded.team2_point,
        over_price = excluded.over_price,
        under_price = excluded.under_price,
        total_points = excluded.total_points,
        payload = excluded.payload
    """
)

MOVE_PREDICTIONS_SQL = text(
    """
    INSERT INTO predictions (model_run_id, game_id, prediction_ts, upset_prob)
    SELECT model_run_id, :to_game_id, prediction_ts, upset_prob
    FROM predictions
    WHERE game_id = :from_game_id
    ON CONFLICT (model_run_id, game_id) DO NOTHING
    """
)

DELETE_PREDICTIONS_FOR_GAME_SQL = text(
    """
    DELETE FROM predictions
    WHERE game_id = :game_id
    """
)

DELETE_ODDS_FOR_GAME_SQL = text(
    """
    DELETE FROM odds_snapshots
    WHERE game_id = :game_id
    """
)

DELETE_GAME_SQL = text(
    """
    DELETE FROM games
    WHERE game_id = :game_id
    """
)

FETCH_ODDS_COUNT_SQL = text(
    """
    SELECT COUNT(*)
    FROM odds_snapshots
    WHERE game_id = :game_id
    """
)

INSERT_TEAM_METRICS_SQL = text(
    """
    INSERT INTO team_metrics (season, team_id, win_pct, point_diff, seed)
    SELECT season, :to_team_id, win_pct, point_diff, seed
    FROM team_metrics
    WHERE team_id = :from_team_id
    ON CONFLICT (season, team_id) DO NOTHING
    """
)

DELETE_TEAM_METRICS_FOR_TEAM_SQL = text(
    """
    DELETE FROM team_metrics
    WHERE team_id = :team_id
    """
)

DELETE_NON_CANONICAL_TEAMS_SQL = text(
    """
    DELETE FROM teams
    WHERE team_id NOT IN :team_ids
    """
).bindparams(bindparam("team_ids", expanding=True))


@dataclass(frozen=True)
class RepairSummary:
    """Summary of a canonical team repair run."""

    canonical_teams: int
    teams_resolved: int
    teams_unresolved: int
    teams_deleted: int
    games_deleted: int
    games_merged: int
    odds_snapshots_merged: int


@dataclass(frozen=True)
class TeamRow:
    """Minimal team row used during repair."""

    team_id: int
    team_key: str
    name: str


@dataclass(frozen=True)
class GameRow:
    """Minimal game row used during repair."""

    game_id: int
    season: int
    date: str
    team1_id: int
    team2_id: int
    source_event_id: str | None
    completed: bool
    home_score: int | None
    away_score: int | None
    last_score_update: str | None


def repair_database(
    database_url: str | None = None,
    catalog: TeamCatalog | None = None,
) -> RepairSummary:
    """Normalize the database onto canonical D1 teams.

    Args:
        database_url: Optional database URL override.
        catalog: Optional preloaded team catalog for tests.

    Returns:
        A summary of the repair actions performed.
    """
    engine = get_engine(database_url)
    team_catalog = catalog or load_team_catalog()

    with engine.begin() as connection:
        canonical_team_ids = seed_team_catalog(connection, team_catalog)
        team_rows = _fetch_team_rows(connection)
        resolved_team_ids: dict[int, int] = {}
        unresolved_team_ids: set[int] = set()

        for team_row in team_rows:
            canonical_team_id = canonical_team_ids.get(team_row.team_key)
            if canonical_team_id is not None:
                resolved_team_ids[team_row.team_id] = canonical_team_id
                continue

            canonical_team_id = resolve_team_id(
                connection,
                team_name=team_row.name,
                catalog=team_catalog,
                team_ids_by_key=canonical_team_ids,
            )
            if canonical_team_id is None:
                unresolved_team_ids.add(team_row.team_id)
                continue
            resolved_team_ids[team_row.team_id] = canonical_team_id

        games_deleted = _delete_unresolved_games(connection, unresolved_team_ids)
        games_merged, odds_snapshots_merged = _merge_games(
            connection,
            resolved_team_ids,
            unresolved_team_ids,
        )
        _merge_team_metrics(connection, resolved_team_ids)

        teams_before_delete = len(team_rows)
        connection.execute(
            DELETE_NON_CANONICAL_TEAMS_SQL,
            {"team_ids": list(canonical_team_ids.values())},
        )
        teams_deleted = teams_before_delete - len(canonical_team_ids)

    return RepairSummary(
        canonical_teams=len(canonical_team_ids),
        teams_resolved=sum(
            1
            for team_row in team_rows
            if team_row.team_key not in canonical_team_ids
            and team_row.team_id in resolved_team_ids
        ),
        teams_unresolved=len(unresolved_team_ids),
        teams_deleted=teams_deleted,
        games_deleted=games_deleted,
        games_merged=games_merged,
        odds_snapshots_merged=odds_snapshots_merged,
    )


def _fetch_team_rows(connection: Connection) -> list[TeamRow]:
    rows = connection.execute(FETCH_TEAMS_SQL).mappings()
    return [
        TeamRow(
            team_id=int(row["team_id"]),
            team_key=str(row["team_key"]),
            name=str(row["name"]),
        )
        for row in rows
    ]


def _delete_unresolved_games(
    connection: Connection,
    unresolved_team_ids: set[int],
) -> int:
    if not unresolved_team_ids:
        return 0

    affected_rows = connection.execute(
        FETCH_GAMES_FOR_TEAM_IDS_SQL,
        {"team_ids": list(unresolved_team_ids)},
    ).mappings()
    game_ids = [int(row["game_id"]) for row in affected_rows]
    if not game_ids:
        if _table_exists(connection, "team_metrics"):
            connection.execute(
                DELETE_TEAM_METRICS_SQL,
                {"team_ids": list(unresolved_team_ids)},
            )
        return 0

    connection.execute(DELETE_ODDS_FOR_GAMES_SQL, {"game_ids": game_ids})
    if _table_exists(connection, "predictions"):
        connection.execute(DELETE_PREDICTIONS_FOR_GAMES_SQL, {"game_ids": game_ids})
    connection.execute(DELETE_GAMES_SQL, {"game_ids": game_ids})
    if _table_exists(connection, "team_metrics"):
        connection.execute(
            DELETE_TEAM_METRICS_SQL,
            {"team_ids": list(unresolved_team_ids)},
        )
    return len(game_ids)


def _merge_games(
    connection: Connection,
    resolved_team_ids: dict[int, int],
    unresolved_team_ids: set[int],
) -> tuple[int, int]:
    game_rows = _fetch_game_rows(connection)
    groups: dict[tuple[int, str, int, int], list[GameRow]] = {}

    for game_row in game_rows:
        if (
            game_row.team1_id in unresolved_team_ids
            or game_row.team2_id in unresolved_team_ids
        ):
            continue

        groups.setdefault(
            (
                game_row.season,
                game_row.date,
                resolved_team_ids.get(game_row.team1_id, game_row.team1_id),
                resolved_team_ids.get(game_row.team2_id, game_row.team2_id),
            ),
            [],
        ).append(game_row)

    games_merged = 0
    odds_snapshots_merged = 0

    for (_, _, target_team1_id, target_team2_id), group in groups.items():
        keeper = max(group, key=_game_priority_key)
        duplicate_games = [game for game in group if game.game_id != keeper.game_id]

        for duplicate_game in duplicate_games:
            odds_snapshots_merged += _move_game_dependents(
                connection,
                from_game_id=duplicate_game.game_id,
                to_game_id=keeper.game_id,
            )
            if (
                keeper.source_event_id is None
                and duplicate_game.source_event_id is not None
            ):
                connection.execute(
                    UPDATE_GAME_SOURCE_EVENT_SQL,
                    {
                        "game_id": keeper.game_id,
                        "source_event_id": duplicate_game.source_event_id,
                    },
                )
            connection.execute(DELETE_GAME_SQL, {"game_id": duplicate_game.game_id})

        if keeper.team1_id != target_team1_id or keeper.team2_id != target_team2_id:
            connection.execute(
                UPDATE_GAME_TEAMS_SQL,
                {
                    "game_id": keeper.game_id,
                    "team1_id": target_team1_id,
                    "team2_id": target_team2_id,
                },
            )

        games_merged += len(duplicate_games)

    return games_merged, odds_snapshots_merged


def _fetch_game_rows(connection: Connection) -> list[GameRow]:
    rows = connection.execute(FETCH_GAMES_SQL).mappings()
    return [
        GameRow(
            game_id=int(row["game_id"]),
            season=int(row["season"]),
            date=str(row["date"]),
            team1_id=int(row["team1_id"]),
            team2_id=int(row["team2_id"]),
            source_event_id=(
                str(row["source_event_id"])
                if row["source_event_id"] is not None
                else None
            ),
            completed=bool(row["completed"]),
            home_score=_optional_int(row["home_score"]),
            away_score=_optional_int(row["away_score"]),
            last_score_update=(
                str(row["last_score_update"])
                if row["last_score_update"] is not None
                else None
            ),
        )
        for row in rows
    ]


def _move_game_dependents(
    connection: Connection,
    *,
    from_game_id: int,
    to_game_id: int,
) -> int:
    odds_count = int(
        connection.execute(
            FETCH_ODDS_COUNT_SQL,
            {"game_id": from_game_id},
        ).scalar_one()
    )
    if odds_count:
        connection.execute(
            MERGE_ODDS_SNAPSHOTS_SQL,
            {"from_game_id": from_game_id, "to_game_id": to_game_id},
        )
        connection.execute(DELETE_ODDS_FOR_GAME_SQL, {"game_id": from_game_id})

    if _table_exists(connection, "predictions"):
        connection.execute(
            MOVE_PREDICTIONS_SQL,
            {"from_game_id": from_game_id, "to_game_id": to_game_id},
        )
        connection.execute(
            DELETE_PREDICTIONS_FOR_GAME_SQL,
            {"game_id": from_game_id},
        )

    return odds_count


def _merge_team_metrics(
    connection: Connection,
    resolved_team_ids: dict[int, int],
) -> None:
    if not _table_exists(connection, "team_metrics"):
        return

    for from_team_id, to_team_id in resolved_team_ids.items():
        if from_team_id == to_team_id:
            continue
        connection.execute(
            INSERT_TEAM_METRICS_SQL,
            {"from_team_id": from_team_id, "to_team_id": to_team_id},
        )
        connection.execute(
            DELETE_TEAM_METRICS_FOR_TEAM_SQL,
            {"team_id": from_team_id},
        )


def _table_exists(connection: Connection, table_name: str) -> bool:
    inspector = inspect(connection)
    return table_name in inspector.get_table_names()


def _game_priority_key(game_row: GameRow) -> tuple[int, int, int, int, int]:
    return (
        int(game_row.completed),
        int(game_row.last_score_update is not None),
        int(game_row.home_score is not None and game_row.away_score is not None),
        int(game_row.source_event_id is not None),
        -game_row.game_id,
    )


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float, str)):
        return int(value)
    raise TypeError(f"Expected int-compatible value, got {type(value).__name__}")
