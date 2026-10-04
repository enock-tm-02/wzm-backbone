-- Canonical schema (PostgreSQL + PostGIS). Loaded by docker-compose on first start.
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS segment (          -- TMC or agency link
    segment_id      text PRIMARY KEY,
    road_name       text,
    direction       text,
    lanes           int,
    length_mi       numeric,
    geom            geometry(LineString, 4326)
);

CREATE TABLE IF NOT EXISTS work_zone (
    zone_id         text PRIMARY KEY,
    source          text NOT NULL,            -- wzdx | permits
    source_id       text,
    segment_ids     text[],
    work_type       text,
    normal_lanes    int,
    open_lanes      int,
    hard_barrier    boolean,
    reduced_speed_mph numeric,
    planned_start   timestamptz,
    planned_end     timestamptz,
    actual_start    timestamptz,              -- from reconcile step
    actual_end      timestamptz,
    geom            geometry(Geometry, 4326)
);

CREATE TABLE IF NOT EXISTS speed_obs (
    segment_id      text REFERENCES segment,
    ts              timestamptz,
    source          text,                     -- npmrds | inrix | here | detectors
    speed_mph       numeric,
    travel_time_s   numeric,
    PRIMARY KEY (segment_id, ts, source)
);

CREATE TABLE IF NOT EXISTS volume_obs (
    station_id      text,
    segment_id      text REFERENCES segment,
    ts              timestamptz,
    volume_vph      numeric,
    occupancy_pct   numeric,
    heavy_pct       numeric,
    PRIMARY KEY (station_id, ts)
);

CREATE TABLE IF NOT EXISTS crash (
    crash_id        text PRIMARY KEY,
    ts              timestamptz,
    severity        text,
    in_work_zone    boolean,
    geom            geometry(Point, 4326)
);

CREATE TABLE IF NOT EXISTS context_obs (       -- weather, events, incidents
    id              bigserial PRIMARY KEY,
    kind            text,
    ts_start        timestamptz,
    ts_end          timestamptz,
    attributes      jsonb,
    geom            geometry(Geometry, 4326)
);

CREATE TABLE IF NOT EXISTS prediction (
    zone_id         text REFERENCES work_zone,
    interval_start  timestamptz,
    model           text,                     -- hcm-baseline | gbm-v1 ...
    made_at         timestamptz DEFAULT now(),
    queue_miles_p50 numeric,
    queue_miles_p10 numeric,
    queue_miles_p90 numeric,
    delay_veh_hours numeric,
    speed_drop_mph  numeric,
    crash_rr        numeric,
    PRIMARY KEY (zone_id, interval_start, model, made_at)
);
