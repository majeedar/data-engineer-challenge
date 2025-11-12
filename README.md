# Data Engineer - Challenge

# SOLUTION PART ONE (Technical Documentation)

## Development Environment

### Tools Used
- **Docker Desktop** (Windows) - Container orchestration
- **Git Bash** (MinGW64) - Command-line interface
- **VS Code** - Code editor and debugging
- **PostgreSQL Client** (psql) - Database interaction

### Tech Stack

**Infrastructure:**
- Docker Compose 
- Eclipse Mosquitto 2.0 - MQTT message broker

**Data Generation:**
- Python 3.10 (Alpine Linux)
- paho-mqtt 2.0+ - MQTT client
- pydantic 2.0+ / pydantic-settings - Configuration management

**Data Ingestion:**
- Python 3.10 (Debian Slim)
- paho-mqtt 2.0+ - MQTT subscriber
- psycopg2-binary 2.9+ - PostgreSQL driver

**Storage:**
- TimescaleDB (PostgreSQL 14) - Time-series database
- Local filesystem - JSONL file storage

---

## Debugging IoT Data Generator

### Issue 1: Pydantic v2 Compatibility

**Problem:**
```
pydantic.errors.PydanticImportError: `BaseSettings` has been moved to `pydantic-settings`
```

**Root Cause:**  
Original code used Pydantic v1 syntax. Docker installed Pydantic v2 by default.

**Solution:**

Modified `iot_data_generator/settings.py`:
```python
# Before (Pydantic v1)
from pydantic import BaseSettings
class Config:
    env_file = '.env'

# After (Pydantic v2)
from pydantic_settings import BaseSettings
model_config = {'env_file': '.env'}
```

Updated `requirements.txt`:
```txt
pydantic>=2.0.0
pydantic-settings>=2.0.0
```

### Issue 2: UTC Timestamp

**Problem:**  
Timestamps appeared 1 hour behind local time (UTC vs local timezone).

**Root Cause:**  
Original code: `datetime.datetime.utcnow()`

**Solution:**

Modified `iot_data_generator/sensor.py` line 16:
```python
# Before
"dt": datetime.datetime.utcnow().isoformat()

# After
"dt": datetime.datetime.now().isoformat()
```


---

## Current Architecture

### Medallion Architecture (Bronze → Silver → Gold)
```
┌─────────────────────────────────────────────────────────────────┐
│                     IoT Data Pipeline                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  [IoT Sensors] → [MQTT Broker] → [Data Ingestion Service]      │
│                                           ↓                      │
│                          ┌────────────────┴──────────────┐      │
│                          ↓                                ↓      │
│                   Bronze Layer                     Silver Layer  │
│                  (Raw Storage)                 (Cleaned Storage) │
│                   JSONL Files              silver.sensor_reading │
│                  Partitioned by:                Real-time DB     │
│                  date + sensor_id                  Indexed       │
│                                                        ↓         │
│                                                   Gold Layer     │
│                                            (Aggregated Storage)  │
│                                         gold.reading_1min_mean   │
│                                            1-min averages        │
│                                           Refreshed every 60s    │
└─────────────────────────────────────────────────────────────────┘
```

---

## Part One Implementation

### Step 1: Raw Data Storage (Bronze Layer)

**Format:** JSONL (JSON Lines - one JSON per line)

**Partitioning Strategy:**
```
data_storage/raw/YYYY-MM-DD_Sensor_X.jsonl
```

**Example:**
```
data_storage/raw/2025-11-12_Sensor_1.jsonl
data_storage/raw/2025-11-12_Sensor_2.jsonl
```

**File Content:**
```json
{"id": "Sensor 1", "dt": "2025-11-12T10:15:01", "value": 25}
{"id": "Sensor 1", "dt": "2025-11-12T10:15:02", "value": 19}
{"id": "Sensor 1", "dt": "2025-11-12T10:15:03", "value": 33}
```

---

### Step 2: Queryable Storage (Silver Layer)

**Implementation:** PostgreSQL table in `silver` schema

**Purpose:**
- Real-time querying
- Fast time-series access
- BI tool compatibility

**Technology:**
- TimescaleDB (PostgreSQL 14)
- Indexed for fast queries
- Batch commits (10 records) for performance

---

### Step 3: 1-Minute Aggregation (Gold Layer)

**Selected Option:** Physical table with UPSERT strategy

**Implementation:**
- Table: `gold.reading_1min_mean`
- Refresh: Every 60 seconds
- Window: Last 5 minutes (re-aggregate incomplete buckets)
- Method: UPSERT (INSERT ... ON CONFLICT DO UPDATE)

**Why UPSERT?**
- Efficient: Only updates changed buckets
- Atomic: Single transaction
- Handles incomplete minutes gracefully

**Refresh Strategy:**
```
Every minute:
1. Query last 5 minutes from silver layer
2. Aggregate using time_bucket('1 minute')
3. UPSERT into gold layer
   - If bucket exists → UPDATE
   - If bucket new → INSERT
```

**Benefits:**
- 98%+ data reduction
- Faster BI queries (5-10x)
- Business-ready aggregates

---

## Data Models

### Bronze Layer (Files)

**Schema:** JSONL format
```json
{
  "id": "string",          // Sensor identifier (Sensor 1-5)
  "dt": "ISO8601",         // Timestamp (YYYY-MM-DDTHH:MM:SS)
  "value": "integer"       // Temperature reading (0-45)
}
```

---

### Silver Layer (Database)

**Table:** `silver.sensor_reading`
```
Column    | Type              | Description
----------|-------------------|---------------------------
time      | TIMESTAMPTZ       | Timestamp of reading
sensor_id | VARCHAR(50)       | Sensor identifier
value     | DOUBLE PRECISION  | Temperature value
```

**Indexes:**
- `idx_silver_sensor_time` on (sensor_id, time DESC)
- `idx_silver_time` on (time DESC)

---

### Gold Layer (Database)

**Table:** `gold.reading_1min_mean`
```
Column    | Type              | Description
----------|-------------------|---------------------------
bucket    | TIMESTAMPTZ       | 1-minute time bucket
sensor_id | VARCHAR(50)       | Sensor identifier
val_mean  | DOUBLE PRECISION  | Mean value for the minute
```

**Primary Key:** (bucket, sensor_id)


---

## Data Flow / Pipeline Logic

### Real-Time Data Flow
```
Second 0:  Sensor generates value → MQTT publish
           ↓
Second 0:  MQTT broker receives → broadcasts to subscribers
           ↓
Second 0:  Ingestion service receives
           ↓
Second 0:  Write to bronze (JSONL file) [~5ms]
           ↓
Second 0:  Write to silver (database) [~10ms]
           ↓
Second 10: Batch commit (10 records) [~50ms]
           ↓
Minute 1:  Gold layer refresh triggered
           ↓
Minute 1:  Aggregate last 5 minutes from silver [~200ms]
           ↓
Minute 1:  UPSERT into gold layer [~100ms]
```



### Ingestion Service Logic

**When sensor data arrives via MQTT:**

1. **Parse the message** - Extract sensor ID, timestamp, and value
2. **Write to Bronze** - Append JSON to file `YYYY-MM-DD_Sensor_X.jsonl`
3. **Write to Silver** - Insert record into `silver.sensor_reading` table
4. **Batch commit** - Commit to database every 10 records or 5 seconds
5. **Trigger gold refresh** - Every 60 seconds, aggregate last 5 minutes

### Gold Layer Refresh Logic

**Executed every 60 seconds:**

1. **Query silver layer** - Fetch all records from last 5 minutes
2. **Group by time buckets** - Use 1-minute windows (time_bucket function)
3. **Calculate aggregates** - Compute average (mean) for each bucket and sensor
4. **UPSERT to gold** - Insert new buckets or update existing ones
   - If bucket doesn't exist → Insert new record
   - If bucket exists → Update with new average


## Testing/Demo

```bash
# Navigate to project directory and Start all containers
docker compose up -d

# Verify all containers are running
docker compose ps
### Sample Queries

#### Bronze Layer (File System)
```bash
# List bronze files
ls -lh data_storage/raw/

# View raw data
head -10 data_storage/raw/2025-11-12_Sensor_1.jsonl

# Count records per file
wc -l data_storage/raw/*.jsonl
```

---
### Silver Layer Tests (Database)
```bash
# Connect to database
docker compose exec timescaledb psql -U postgres -d sensors
```
```sql
-- Check total records in silver layer
SELECT COUNT(*) as total_records 
FROM silver.sensor_reading;

-- View most recent 10 readings
SELECT * FROM silver.sensor_reading 
ORDER BY time DESC 
LIMIT 10;

-- View data for specific sensor
SELECT * FROM silver.sensor_reading
WHERE sensor_id = 'Sensor 1'
ORDER BY time DESC
LIMIT 20;
```
---

### Gold Layer Tests (Database)
```sql
-- Check total buckets in gold layer
SELECT COUNT(*) as total_buckets 
FROM gold.reading_1min_mean;

-- View most recent 15 aggregates
SELECT * FROM gold.reading_1min_mean 
ORDER BY bucket DESC 
LIMIT 15;

-- Summary per sensor
SELECT 
    sensor_id,
    COUNT(*) as bucket_count,
    ROUND(CAST(AVG(val_mean) AS numeric), 2) as overall_avg,
    MIN(bucket) as first_bucket,
    MAX(bucket) as last_bucket
FROM gold.reading_1min_mean
GROUP BY sensor_id
ORDER BY sensor_id;

### Exit PostgreSQL
```bash

\q
```

---
---------------------------------------------------------------------------
# SOLUION PART TWO : Cloud Solution Design - Concise Plan
--------------------------------------------------
## Architecture

**Simple Flow:**
```
IoT Sensors → Azure IoT Hub → Event Hubs → Azure Databricks → Delta Lake (Bronze/Silver/Gold) →  APIs
                                                                                                          ↓
                                                                  Power Platform (Power Automate + SharePoint + Chatbot)
                                                                                          ↓
                                                                              Customer Communication
```

**Key Principle:** Single platform (Databricks) for data processing. Power Platform for customer communication automation.

---

## Technology Stack

### Data Layer
- **Azure IoT Hub** - Device management
- **Azure Event Hubs** - Message streaming
- **Azure Data Lake Gen2** - Storage
- **Delta Lake** - ACID transactions on data lake
- **Azure Databricks** - Unified data processing (ingestion + transformation)

### Data access Layer
- **Azure API Management** - REST APIs
- **Azure Functions** - API backends

### Communication Layer (Power Platform)
- **Power Automate** - Workflow automation
- **SharePoint Online** - Documentation storage
- **Power Virtual Agents** - Chatbot interface
- **Azure OpenAI + RAG** - Intelligent answers
- **Azure DevOps** - Ticket tracking

### Monitoring Layer
- **Azure Monitor** - Infrastructure health
- **Databricks Workflows** - Job orchestration
- **Great Expectations** - Data quality

---

## Deployment

**Infrastructure as Code:** Terraform

**Key Resources:** IoT Hub, Event Hubs, ADLS Gen2, Databricks, SharePoint, Power Platform Environment

**Environments:** Dev → Staging → Production via CI/CD


---

## Data Pipeline

- **Bronze:** Raw data from Event Hubs → Delta Lake (continuous)
- **Silver:** Cleaned data, deduplication, validation (every 5 min)
- **Gold:** 1-minute aggregates (every 1 min)

---

## Monitoring

**Azure Monitor:** Infrastructure metrics, alerts (Critical/Warning/Info)

**Databricks:** Job runs, latency, resource usage

**Quality Checks:** Schema, nulls, ranges, completeness, freshness

**Quality Score:** 0-100% (>95% = good, 80-95% = warning, <80% = critical)

---

## Customer Communication (Power Platform)

### 1. Automated Quality Reports
- **Power Automate** queries Databricks daily at 8 AM
- Generates PDF report per customer
- Emails report and stores in **SharePoint**

### 2. AI Documentation Chatbot
- **SharePoint** stores all documentation
- **Azure OpenAI + RAG** answers questions from SharePoint docs
- **Power Virtual Agents** provides chatbot interface
- 24/7 instant answers, creates tickets if needed

### 3. Automated Ticket System
- **Power Automate** receives requests (email/portal/chatbot)
- AI categorizes and routes to **Azure DevOps**
- Sends confirmation, tracks SLA, updates customer
- Auto-resolves common issues from SharePoint knowledge base

