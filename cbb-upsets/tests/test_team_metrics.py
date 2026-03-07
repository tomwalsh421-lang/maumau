import sqlite3

from cbb.metrics.team_metrics import compute_team_metrics


def create_test_db(path):
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE teams (
            team_id INTEGER PRIMARY KEY,
            ncaa_team_code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL
        );

        CREATE TABLE team_metrics (
            team_metrics_id INTEGER PRIMARY KEY,
            season INTEGER NOT NULL,
            team_id INTEGER NOT NULL,
            win_pct NUMERIC,
            point_diff NUMERIC,
            seed INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(season, team_id)
        );

        CREATE TABLE games (
            game_id INTEGER PRIMARY KEY,
            season INTEGER NOT NULL,
            date TEXT NOT NULL,
            team1_id INTEGER NOT NULL,
            team2_id INTEGER NOT NULL,
            round TEXT,
            ncaa_game_code TEXT UNIQUE,
            result TEXT,
            UNIQUE(season, date, team1_id, team2_id)
        );
        """
    )
    connection.executemany(
        "INSERT INTO teams (team_id, ncaa_team_code, name) VALUES (?, ?, ?)",
        [
            (1, "A", "Alpha"),
            (2, "B", "Beta"),
            (3, "C", "Gamma"),
        ],
    )
    connection.executemany(
        """
        INSERT INTO games (season, date, team1_id, team2_id, round, ncaa_game_code, result)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (2026, "2026-03-01", 1, 2, "R64", "g1", "W"),
            (2026, "2026-03-02", 2, 3, "R64", "g2", "L"),
            (2026, "2026-03-03", 3, 1, "R32", "g3", "L"),
            (2026, "2026-03-04", 1, 3, "R16", "g4", None),
        ],
    )
    connection.commit()
    connection.close()


def test_compute_team_metrics_updates_team_metrics_table(tmp_path):
    db_path = tmp_path / "metrics.sqlite"
    create_test_db(db_path)

    database_url = f"sqlite+pysqlite:///{db_path}"
    summaries = compute_team_metrics(2026, database_url=database_url)

    assert [(summary.team_id, summary.wins, summary.losses, summary.win_pct) for summary in summaries] == [
        (1, 2, 0, 1.0),
        (2, 0, 2, 0.0),
        (3, 1, 1, 0.5),
    ]

    connection = sqlite3.connect(db_path)
    rows = connection.execute(
        "SELECT season, team_id, win_pct FROM team_metrics ORDER BY team_id"
    ).fetchall()
    connection.close()

    assert rows == [
        (2026, 1, 1),
        (2026, 2, 0),
        (2026, 3, 0.5),
    ]


def test_compute_team_metrics_is_idempotent(tmp_path):
    db_path = tmp_path / "metrics.sqlite"
    create_test_db(db_path)

    database_url = f"sqlite+pysqlite:///{db_path}"
    compute_team_metrics(2026, database_url=database_url)
    compute_team_metrics(2026, database_url=database_url)

    connection = sqlite3.connect(db_path)
    row_count = connection.execute("SELECT COUNT(*) FROM team_metrics").fetchone()[0]
    connection.close()

    assert row_count == 3
