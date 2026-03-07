import sqlite3

from typer.testing import CliRunner

from cbb.cli import app


runner = CliRunner()


def create_test_db(path):
    connection = sqlite3.connect(path)
    connection.executescript(
        """
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

        INSERT INTO games (season, date, team1_id, team2_id, result)
        VALUES (2026, '2026-03-01', 10, 20, 'W');
        """
    )
    connection.commit()
    connection.close()


def test_compute_metrics_command_reads_database_url_from_env(monkeypatch, tmp_path):
    db_path = tmp_path / "cli.sqlite"
    create_test_db(db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db_path}")

    result = runner.invoke(app, ["compute-metrics", "2026"])

    assert result.exit_code == 0
    assert "Computed team metrics for season 2026: 2 teams updated" in result.stdout
