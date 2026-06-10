from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    APP_NAME: str = "E-Commerce Recommendation System"
    APP_VERSION: str = "1.0.0"

    DATABASE_URL: str = "sqlite:///./recommendation.db"

    CF_WEIGHT: float = 0.6
    CONTENT_WEIGHT: float = 0.4

    SVD_N_COMPONENTS: int = 50
    COLD_START_EVENT_THRESHOLD: int = 5
    TRENDING_WINDOW_DAYS: int = 7
    NEW_PRODUCT_WINDOW_DAYS: int = 30

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
