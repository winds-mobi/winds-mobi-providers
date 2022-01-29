CREATE EXTENSION IF NOT EXISTS postgis;
-- CREATE EXTENSION IF NOT EXISTS timescaledb;

DROP TABLE IF EXISTS stations;
CREATE TABLE stations (
    id VARCHAR(50) PRIMARY KEY,
    name VARCHAR,
    alt INTEGER,
    loc geography(POINT,4326),
    peak BOOLEAN NOT NULL,
    provider_code VARCHAR,
    provider_id VARCHAR,
    provider_name VARCHAR,
    seen TIMESTAMP,
    short VARCHAR,
    status VARCHAR,
    tz VARCHAR,
    url VARCHAR
);
CREATE INDEX stations_loc_idx
  ON stations
  USING GIST (loc);

DROP TABLE IF EXISTS measures;
CREATE TABLE measures (
    ts TIMESTAMP NOT NULL,
    station_id VARCHAR(50) NOT NULL,
    wind_dir REAL,
    wind_avg REAL,
    wind_max REAL,
    temp REAL,
    hum REAL,
    pressure_qfe REAL,
    pressure_qnh REAL,
    pressure_qff REAL,
    rain REAL,
    updated_at TIMESTAMP NOT NULL
);

-- SELECT create_hypertable('measures', 'ts', 'station_id');
-- CREATE INDEX ON measures (ts desc, station_id);
