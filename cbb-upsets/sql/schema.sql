-- PostgreSQL schema for the supported cbb-upsets workflows:
-- canonical team storage, game ingest, odds ingest, checkpoints, and repair.

-- Canonical D1 teams.
CREATE TABLE IF NOT EXISTS teams (
    team_id         SERIAL PRIMARY KEY,
    team_key        VARCHAR(120) UNIQUE NOT NULL,
    ncaa_team_code  VARCHAR(20) UNIQUE,
    name            VARCHAR(255) NOT NULL,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT now()
);

ALTER TABLE teams ADD COLUMN IF NOT EXISTS team_key VARCHAR(120);
ALTER TABLE teams ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE DEFAULT now();
ALTER TABLE teams ALTER COLUMN ncaa_team_code DROP NOT NULL;
UPDATE teams
SET team_key = lower(regexp_replace(name, '[^a-zA-Z0-9]+', '-', 'g'))
WHERE team_key IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_teams_team_key ON teams(team_key);

-- Maps provider-specific team names back to canonical D1 teams.
CREATE TABLE IF NOT EXISTS team_aliases (
    team_alias_id    SERIAL PRIMARY KEY,
    team_id          INT NOT NULL REFERENCES teams(team_id) ON DELETE CASCADE,
    alias_key        VARCHAR(160) NOT NULL UNIQUE,
    alias_name       VARCHAR(255) NOT NULL,
    created_at       TIMESTAMP WITH TIME ZONE DEFAULT now()
);

ALTER TABLE team_aliases ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE DEFAULT now();
CREATE UNIQUE INDEX IF NOT EXISTS idx_team_aliases_alias_key ON team_aliases(alias_key);
CREATE INDEX IF NOT EXISTS idx_team_aliases_team_id ON team_aliases(team_id);

-- Games (team1 is the home team for current odds loads).
CREATE TABLE IF NOT EXISTS games (
    game_id          SERIAL PRIMARY KEY,
    season           INT NOT NULL,
    date             DATE NOT NULL,
    commence_time    TIMESTAMP WITH TIME ZONE,
    team1_id         INT NOT NULL REFERENCES teams(team_id),
    team2_id         INT NOT NULL REFERENCES teams(team_id),
    round            VARCHAR(30),
    ncaa_game_code   VARCHAR(40) UNIQUE,
    source_event_id  VARCHAR(64) UNIQUE,
    sport_key        VARCHAR(64),
    sport_title      VARCHAR(120),
    result           VARCHAR(10),
    completed        BOOLEAN NOT NULL DEFAULT FALSE,
    home_score       INT,
    away_score       INT,
    last_score_update TIMESTAMP WITH TIME ZONE,
    CHECK (team1_id <> team2_id),
    UNIQUE (season, date, team1_id, team2_id)
);

ALTER TABLE games ADD COLUMN IF NOT EXISTS commence_time TIMESTAMP WITH TIME ZONE;
ALTER TABLE games ADD COLUMN IF NOT EXISTS source_event_id VARCHAR(64);
ALTER TABLE games ADD COLUMN IF NOT EXISTS sport_key VARCHAR(64);
ALTER TABLE games ADD COLUMN IF NOT EXISTS sport_title VARCHAR(120);
ALTER TABLE games ADD COLUMN IF NOT EXISTS completed BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE games ADD COLUMN IF NOT EXISTS home_score INT;
ALTER TABLE games ADD COLUMN IF NOT EXISTS away_score INT;
ALTER TABLE games ADD COLUMN IF NOT EXISTS last_score_update TIMESTAMP WITH TIME ZONE;
UPDATE games
SET source_event_id = ncaa_game_code
WHERE source_event_id IS NULL
  AND ncaa_game_code IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_games_source_event_id ON games(source_event_id);

-- Tracks fully ingested source/date slices so reruns can skip them.
CREATE TABLE IF NOT EXISTS ingest_checkpoints (
    ingest_checkpoint_id SERIAL PRIMARY KEY,
    source_name         VARCHAR(64) NOT NULL,
    sport_key           VARCHAR(64) NOT NULL,
    game_date           DATE NOT NULL,
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT now(),
    UNIQUE(source_name, sport_key, game_date)
);

ALTER TABLE ingest_checkpoints ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE DEFAULT now();
CREATE UNIQUE INDEX IF NOT EXISTS idx_ingest_checkpoints_source_sport_date
ON ingest_checkpoints(source_name, sport_key, game_date);

-- Odds snapshots for current and historical captures.
CREATE TABLE IF NOT EXISTS odds_snapshots (
    odds_id           SERIAL PRIMARY KEY,
    game_id           INT NOT NULL REFERENCES games(game_id),
    bookmaker_key     VARCHAR(64) NOT NULL,
    bookmaker_title   VARCHAR(128) NOT NULL,
    market_key        VARCHAR(64) NOT NULL,
    captured_at       TIMESTAMP WITH TIME ZONE NOT NULL,
    is_closing_line   BOOLEAN NOT NULL DEFAULT FALSE,
    team1_price       NUMERIC(12,4),
    team2_price       NUMERIC(12,4),
    team1_point       NUMERIC(12,4),
    team2_point       NUMERIC(12,4),
    over_price        NUMERIC(12,4),
    under_price       NUMERIC(12,4),
    total_points      NUMERIC(12,4),
    payload           TEXT NOT NULL,
    UNIQUE(game_id, bookmaker_key, market_key, captured_at)
);

ALTER TABLE odds_snapshots ADD COLUMN IF NOT EXISTS bookmaker_key VARCHAR(64);
ALTER TABLE odds_snapshots ADD COLUMN IF NOT EXISTS bookmaker_title VARCHAR(128);
ALTER TABLE odds_snapshots ADD COLUMN IF NOT EXISTS market_key VARCHAR(64);
ALTER TABLE odds_snapshots ADD COLUMN IF NOT EXISTS is_closing_line BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE odds_snapshots ADD COLUMN IF NOT EXISTS team1_price NUMERIC(12,4);
ALTER TABLE odds_snapshots ADD COLUMN IF NOT EXISTS team2_price NUMERIC(12,4);
ALTER TABLE odds_snapshots ADD COLUMN IF NOT EXISTS team1_point NUMERIC(12,4);
ALTER TABLE odds_snapshots ADD COLUMN IF NOT EXISTS team2_point NUMERIC(12,4);
ALTER TABLE odds_snapshots ADD COLUMN IF NOT EXISTS over_price NUMERIC(12,4);
ALTER TABLE odds_snapshots ADD COLUMN IF NOT EXISTS under_price NUMERIC(12,4);
ALTER TABLE odds_snapshots ADD COLUMN IF NOT EXISTS total_points NUMERIC(12,4);
ALTER TABLE odds_snapshots ADD COLUMN IF NOT EXISTS payload TEXT;
UPDATE odds_snapshots
SET bookmaker_key = COALESCE(bookmaker_key, 'unknown'),
    bookmaker_title = COALESCE(bookmaker_title, 'Unknown'),
    market_key = COALESCE(market_key, 'h2h'),
    payload = COALESCE(payload, '{}')
WHERE bookmaker_key IS NULL
   OR bookmaker_title IS NULL
   OR market_key IS NULL
   OR payload IS NULL;
ALTER TABLE odds_snapshots ALTER COLUMN bookmaker_key SET NOT NULL;
ALTER TABLE odds_snapshots ALTER COLUMN bookmaker_title SET NOT NULL;
ALTER TABLE odds_snapshots ALTER COLUMN market_key SET NOT NULL;
ALTER TABLE odds_snapshots ALTER COLUMN payload SET NOT NULL;
ALTER TABLE odds_snapshots DROP CONSTRAINT IF EXISTS odds_snapshots_game_id_captured_at_key;
CREATE UNIQUE INDEX IF NOT EXISTS idx_odds_snapshots_game_bookmaker_market_capture
ON odds_snapshots(game_id, bookmaker_key, market_key, captured_at);
CREATE INDEX IF NOT EXISTS idx_odds_snapshots_closing_market
ON odds_snapshots(game_id, market_key, is_closing_line);

-- Tracks completed historical odds snapshot requests so reruns can skip them.
CREATE TABLE IF NOT EXISTS historical_odds_checkpoints (
    historical_odds_checkpoint_id SERIAL PRIMARY KEY,
    source_name                  VARCHAR(64) NOT NULL,
    sport_key                    VARCHAR(64) NOT NULL,
    market_key                   VARCHAR(64) NOT NULL,
    filters_key                  VARCHAR(128) NOT NULL,
    snapshot_time                TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at                   TIMESTAMP WITH TIME ZONE DEFAULT now(),
    UNIQUE(source_name, sport_key, market_key, filters_key, snapshot_time)
);

ALTER TABLE historical_odds_checkpoints ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE DEFAULT now();
CREATE UNIQUE INDEX IF NOT EXISTS idx_historical_odds_checkpoints_lookup
ON historical_odds_checkpoints(source_name, sport_key, market_key, filters_key, snapshot_time);

-- Indexes for active query patterns.
CREATE INDEX IF NOT EXISTS idx_games_season_date ON games(season, date);
CREATE INDEX IF NOT EXISTS idx_games_commence_time ON games(commence_time);
CREATE INDEX IF NOT EXISTS idx_odds_game ON odds_snapshots(game_id);
CREATE INDEX IF NOT EXISTS idx_odds_market_capture ON odds_snapshots(market_key, captured_at);
