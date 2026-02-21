-- schema.sql for cbb-upsets Postgres database
-- ----------------------------------------------

-- Teams reference table
CREATE TABLE IF NOT EXISTS teams (
    team_id         SERIAL PRIMARY KEY,
    ncaa_team_code  VARCHAR(20) UNIQUE NOT NULL,
    name            VARCHAR(255) NOT NULL
);

-- Stores static and per-season team metrics
CREATE TABLE IF NOT EXISTS team_metrics (
    team_metrics_id SERIAL PRIMARY KEY,
    season         INT NOT NULL,
    team_id        INT NOT NULL REFERENCES teams(team_id) ON DELETE CASCADE,
    win_pct        NUMERIC(5,4),
    point_diff     NUMERIC(5,1),
    seed           INT,
    created_at     TIMESTAMP WITH TIME ZONE DEFAULT now(),
    UNIQUE(season, team_id)
);

-- Games (matchups: regular season or tournament)
CREATE TABLE IF NOT EXISTS games (
    game_id        SERIAL PRIMARY KEY,
    season        INT NOT NULL,
    date          DATE NOT NULL,
    team1_id      INT NOT NULL REFERENCES teams(team_id),
    team2_id      INT NOT NULL REFERENCES teams(team_id),
    round         VARCHAR(30),
    ncaa_game_code VARCHAR(40) UNIQUE,
    result        VARCHAR(10), -- W/L for team1
    UNIQUE (season, date, team1_id, team2_id)
);

-- Odds snapshots: per game, per time, etc.
CREATE TABLE IF NOT EXISTS odds_snapshots (
    odds_id        SERIAL PRIMARY KEY,
    game_id        INT NOT NULL REFERENCES games(game_id),
    captured_at    TIMESTAMP WITH TIME ZONE NOT NULL,
    team1_ml_odds  INT,  -- Moneyline for team1
    team2_ml_odds  INT,  -- Moneyline for team2
    UNIQUE(game_id, captured_at)
);

-- Model runs for auditability/reproducibility
CREATE TABLE IF NOT EXISTS model_runs (
    model_run_id   SERIAL PRIMARY KEY,
    run_ts        TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    model_hash    VARCHAR(128) NOT NULL,
    feature_hash  VARCHAR(128) NOT NULL,
    train_season  INT NOT NULL,
    params        JSONB,
    UNIQUE(model_hash, feature_hash, train_season)
);

-- Predictions made by the model on games
CREATE TABLE IF NOT EXISTS predictions (
    prediction_id  SERIAL PRIMARY KEY,
    model_run_id   INT NOT NULL REFERENCES model_runs(model_run_id) ON DELETE CASCADE,
    game_id        INT NOT NULL REFERENCES games(game_id) ON DELETE CASCADE,
    prediction_ts  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    upset_prob     NUMERIC(5,4) NOT NULL,
    UNIQUE(model_run_id, game_id)
);

-- Indexes for performance (some created implicitly by PK/UNIQUE)
CREATE INDEX IF NOT EXISTS idx_team_metrics_team_season ON team_metrics(team_id, season);
CREATE INDEX IF NOT EXISTS idx_games_season_date ON games(season, date);
CREATE INDEX IF NOT EXISTS idx_odds_game ON odds_snapshots(game_id);
CREATE INDEX IF NOT EXISTS idx_predictions_model_run ON predictions(model_run_id);

