-- =====================================================================
--  THE CONTRACT
--  Agreed by both of us at kickoff. Changing anything in this file
--  breaks the other person's work without them touching a thing —
--  so tell them BEFORE you open a pull request that edits it.
-- =====================================================================

-- TimescaleDB turns Postgres into a time-series database.
-- Safe to run more than once.
CREATE EXTENSION IF NOT EXISTS timescaledb;


-- ---------------------------------------------------------------------
--  vessel_positions — the moving information.
--  One row every time a ship broadcasts where it is.
--  This table grows fast: a busy bounding box is millions of rows a week.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS vessel_positions (
    mmsi        BIGINT        NOT NULL,  -- the ship's permanent 9-digit radio ID
    ts          TIMESTAMPTZ   NOT NULL,  -- when the broadcast was made, always UTC
    lat         DOUBLE PRECISION,        -- degrees north
    lon         DOUBLE PRECISION,        -- degrees east
    sog         REAL,                    -- speed over ground, in knots
    cog         REAL,                    -- course over ground, 0-360 degrees
    heading     REAL,                    -- where the bow points (differs from cog in current/wind)
    nav_status  SMALLINT,                -- 0 = under way, 1 = at anchor, 5 = moored, ...
    source      TEXT          NOT NULL,  -- 'digitraffic' or 'aisstream'

    -- Deduplication happens here, not in Python. The same position often
    -- arrives twice; the database simply refuses the second copy.
    PRIMARY KEY (mmsi, ts)
);

-- Turn it into a hypertable: Timescale transparently splits it into
-- weekly chunks so queries on a time range stay fast as it grows.
SELECT create_hypertable(
    'vessel_positions', 'ts',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE
);

-- "Show me everything this one ship did" is the query we run constantly.
CREATE INDEX IF NOT EXISTS idx_positions_mmsi_ts
    ON vessel_positions (mmsi, ts DESC);


-- ---------------------------------------------------------------------
--  vessels — the fixed information.
--  One row per ship. Updated rarely, so we overwrite rather than append.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS vessels (
    mmsi        BIGINT      PRIMARY KEY,  -- joins to vessel_positions.mmsi
    name        TEXT,                     -- often blank, often misspelled
    call_sign   TEXT,
    imo         BIGINT,                   -- a second, more official ship ID
    ship_type   SMALLINT,                 -- 70-79 cargo, 80-89 tanker, 30 fishing, ...
    length_m    REAL,                     -- needed to estimate emissions
    width_m     REAL,
    draught_m   REAL,                     -- how deep it sits: a proxy for how loaded it is
    destination TEXT,                     -- typed in by the crew, so wildly unreliable
    eta         TEXT,                     -- also crew-entered, also unreliable
    updated_at  TIMESTAMPTZ NOT NULL      -- last time we heard static data for this ship
);
