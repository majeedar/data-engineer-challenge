-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Create schemas
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;

-- ====================
-- SILVER LAYER
-- ====================

-- Silver: Cleaned, indexed sensor readings
CREATE TABLE IF NOT EXISTS silver.sensor_reading (
    time TIMESTAMPTZ NOT NULL,
    sensor_id VARCHAR(50) NOT NULL,
    value DOUBLE PRECISION NOT NULL
);

-- Indexes for fast queries
CREATE INDEX IF NOT EXISTS idx_silver_sensor_time 
    ON silver.sensor_reading (sensor_id, time DESC);

CREATE INDEX IF NOT EXISTS idx_silver_time 
    ON silver.sensor_reading (time DESC);

-- ====================
-- GOLD LAYER
-- ====================

-- Gold: 1-minute mean values (simplified)
CREATE TABLE IF NOT EXISTS gold.reading_1min_mean (
    bucket TIMESTAMPTZ NOT NULL,
    sensor_id VARCHAR(50) NOT NULL,
    val_mean DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (bucket, sensor_id)
);

-- Indexes for gold layer
CREATE INDEX IF NOT EXISTS idx_gold_bucket 
    ON gold.reading_1min_mean (bucket DESC);

CREATE INDEX IF NOT EXISTS idx_gold_sensor_bucket 
    ON gold.reading_1min_mean (sensor_id, bucket DESC);

-- ====================
-- COMMENTS
-- ====================

COMMENT ON SCHEMA silver IS 'Silver layer: Cleaned, indexed sensor data';
COMMENT ON SCHEMA gold IS 'Gold layer: Business-ready aggregated data';
COMMENT ON TABLE silver.sensor_reading IS 'Real-time sensor readings';
COMMENT ON TABLE gold.reading_1min_mean IS '1-minute mean values using TimescaleDB time_bucket';
