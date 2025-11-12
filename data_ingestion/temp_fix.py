def setup_storage():
    """Make sure our storage folders exist and copy sensor metadata"""
    Path(RAW_DATA_PATH).mkdir(parents=True, exist_ok=True)
    Path(METADATA_PATH).mkdir(parents=True, exist_ok=True)
    
    # Note: sensors.json will be copied manually or can be retrieved from iot_data_generator
    print("[INFO] Storage directories initialized")
