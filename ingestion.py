import paho.mqtt.client as mqtt
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
import psycopg2
import time

# Storage paths
RAW_DATA_PATH = "/data/raw"

# Database connection
db_conn = None
db_cursor = None

# Gold layer refresh tracking
last_gold_refresh = datetime.now()

def setup_storage():
    """Initialize storage directories"""
    Path(RAW_DATA_PATH).mkdir(parents=True, exist_ok=True)
    print("[INFO] Storage directories initialized")

def connect_database():
    """Connect to database with retries"""
    global db_conn, db_cursor
    
    db_config = {
        'host': os.getenv('DB_HOST', 'timescaledb'),
        'port': int(os.getenv('DB_PORT', 5432)),
        'database': os.getenv('DB_NAME', 'sensors'),
        'user': os.getenv('DB_USER', 'postgres'),
        'password': os.getenv('DB_PASSWORD', 'password')
    }
    
    max_retries = 5
    retry_delay = 5
    
    for attempt in range(max_retries):
        try:
            print(f"[INFO] Connecting to database at {db_config['host']}:{db_config['port']}...")
            db_conn = psycopg2.connect(**db_config)
            db_conn.autocommit = False
            db_cursor = db_conn.cursor()
            
            # Create schemas if they don't exist
            db_cursor.execute("CREATE SCHEMA IF NOT EXISTS silver")
            db_cursor.execute("CREATE SCHEMA IF NOT EXISTS gold")
            db_conn.commit()
            
            print("[SUCCESS] Database connected")
            return True
        except psycopg2.OperationalError as e:
            print(f"[WARNING] Attempt {attempt + 1}/{max_retries} failed")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
            else:
                print("[ERROR] Could not connect to database")
                return False

def store_raw_data(data):
    """Store raw sensor data to JSONL files (Bronze Layer)"""
    try:
        sensor_id = data['id'].replace(' ', '_')
        timestamp = data['dt']
        date = datetime.fromisoformat(timestamp).date()
        filename = f"{RAW_DATA_PATH}/{date}_{sensor_id}.jsonl"
        
        with open(filename, 'a') as f:
            f.write(json.dumps(data) + '\n')
        
        return True
    except Exception as e:
        print(f"[ERROR] Bronze storage error: {e}")
        return False

def store_to_silver(data):
    """Store sensor data to silver layer"""
    global db_conn, db_cursor
    
    try:
        if db_conn is None or db_cursor is None:
            return False
        
        query = "INSERT INTO silver.sensor_reading (time, sensor_id, value) VALUES (%s, %s, %s)"
        db_cursor.execute(query, (data['dt'], data['id'], data['value']))
        
        return True
    except Exception as e:
        print(f"[ERROR] Silver storage error: {e}")
        if "connection" in str(e).lower():
            connect_database()
        return False

def refresh_gold_layer():
    """
    Refresh gold layer using UPSERT approach:
    - Re-aggregate last 5 minutes from silver using time_bucket
    - Insert new buckets or update existing ones (ON CONFLICT)
    - This ensures incomplete buckets get updated as more data arrives
    """
    global db_conn, db_cursor
    
    try:
        if db_conn is None or db_cursor is None:
            return False
        
        # Upsert: Insert new or update existing buckets
        query = """
            INSERT INTO gold.reading_1min_mean 
                (bucket, sensor_id, val_mean, val_min, val_max, sample_count, data_quality, last_updated)
            SELECT 
                time_bucket('1 minute', time) AS bucket,
                sensor_id,
                ROUND(AVG(value), 2) AS val_mean,
                MIN(value) AS val_min,
                MAX(value) AS val_max,
                COUNT(*) AS sample_count,
                CASE 
                    WHEN COUNT(*) >= 58 THEN 'Good'
                    WHEN COUNT(*) >= 50 THEN 'Fair'
                    ELSE 'Poor'
                END AS data_quality,
                NOW() AS last_updated
            FROM silver.sensor_reading
            WHERE time >= NOW() - INTERVAL '5 minutes'
            GROUP BY bucket, sensor_id
            ON CONFLICT (bucket, sensor_id) 
            DO UPDATE SET
                val_mean = EXCLUDED.val_mean,
                val_min = EXCLUDED.val_min,
                val_max = EXCLUDED.val_max,
                sample_count = EXCLUDED.sample_count,
                data_quality = EXCLUDED.data_quality,
                last_updated = EXCLUDED.last_updated
        """
        
        db_cursor.execute(query)
        db_conn.commit()
        
        rows_affected = db_cursor.rowcount
        print(f"[GOLD] Upserted {rows_affected} bucket(s) (last 5 min window)")
        
        return True
        
    except Exception as e:
        print(f"[ERROR] Gold refresh failed: {e}")
        db_conn.rollback()
        return False

# Batch processing
batch_buffer = []
batch_size = 10
last_commit_time = time.time()
commit_interval = 5

def flush_batch():
    """Commit batched silver layer writes"""
    global db_conn, last_commit_time
    
    if db_conn and batch_buffer:
        try:
            db_conn.commit()
            count = len(batch_buffer)
            batch_buffer.clear()
            last_commit_time = time.time()
            print(f"[SILVER] Committed {count} records")
        except Exception as e:
            print(f"[ERROR] Commit failed: {e}")
            db_conn.rollback()

def on_connect(client, userdata, flags, rc, properties=None):
    """Callback when connected to MQTT broker"""
    if rc == 0:
        print("[SUCCESS] Connected to MQTT broker")
        client.subscribe("sensors")
        print("[INFO] Subscribed to topic: sensors")
    else:
        print(f"[ERROR] MQTT connection failed: {rc}")

def on_message(client, userdata, msg):
    """Callback when message received from MQTT"""
    global last_gold_refresh
    
    try:
        data = json.loads(msg.payload.decode())
        
        # Bronze: Raw files
        raw_ok = store_raw_data(data)
        
        # Silver: Database
        silver_ok = store_to_silver(data)
        
        if silver_ok:
            batch_buffer.append(data)
        
        # Log status
        bronze_status = "[BRONZE:OK]" if raw_ok else "[BRONZE:FAIL]"
        silver_status = "[SILVER:OK]" if silver_ok else "[SILVER:FAIL]"
        print(f"{bronze_status} {silver_status} {data['id']:10s} @ {data['dt'][11:19]} = {data['value']:3d}")
        
        # Commit batch
        if len(batch_buffer) >= batch_size or (time.time() - last_commit_time) > commit_interval:
            flush_batch()
        
        # Refresh gold every 60 seconds
        now = datetime.now()
        if (now - last_gold_refresh).seconds >= 60:
            refresh_gold_layer()
            last_gold_refresh = now
        
    except Exception as e:
        print(f"[ERROR] Message processing failed: {e}")

def main():
    """Main entry point"""
    print("=" * 70)
    print("IoT Data Pipeline - Bronze → Silver → Gold")
    print("=" * 70)
    
    setup_storage()
    connect_database()
    
    print(f"[INFO] Bronze: {RAW_DATA_PATH}/*.jsonl")
    print("[INFO] Silver: silver.sensor_reading")
    print("[INFO] Gold:   gold.reading_1min_mean (time_bucket + UPSERT)")
    print("[INFO] Refresh: UPSERT last 5 minutes every 60s")
    print("=" * 70)
    
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message
    
    mqtt_host = os.getenv('MQTT_HOST', 'mqtt_broker')
    mqtt_port = int(os.getenv('MQTT_PORT', 1883))
    
    client.connect(mqtt_host, mqtt_port, 60)
    
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print("\n[INFO] Shutting down...")
        flush_batch()
        if db_conn:
            db_conn.close()

if __name__ == "__main__":
    main()
