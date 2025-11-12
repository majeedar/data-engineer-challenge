from typing import Optional

from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache


class MqttSettings(BaseSettings):
    model_config = {
        'env_file': '.env',
        'env_prefix': 'mqtt_'
    }

    host: str = "localhost"
    port: int = 1883
    topic: str = "sensors"
    username: Optional[str] = None
    password: Optional[str] = None


class Settings(BaseSettings):
    model_config = {
        'env_file': '.env'
    }

    mqtt: MqttSettings = Field(default_factory=MqttSettings)
    interval_ms: int = 1000
    logging_level: int = 30


@lru_cache()
def get_settings() -> Settings:
    return Settings()