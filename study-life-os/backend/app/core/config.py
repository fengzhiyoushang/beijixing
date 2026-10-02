"""全局配置：环境变量驱动，支持 SQLite/MySQL、Redis/内存 双模运行。"""
from functools import lru_cache
from typing import List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    APP_NAME: str = "StudyLifeOS API"
    DEBUG: bool = True
    SECRET_KEY: str = "dev-secret-change-in-production"
    ACCESS_TOKEN_EXPIRE_DAYS: int = 7

    # ---------- 数据库 ----------
    DB_BACKEND: str = "sqlite"          # sqlite | mysql
    DATABASE_URL: Optional[str] = None  # 显式连接串，优先级最高
    MYSQL_HOST: str = "127.0.0.1"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "root"
    MYSQL_PASSWORD: str = ""
    MYSQL_DB: str = "study_life_os"

    # ---------- 缓存 ----------
    REDIS_ENABLED: bool = True
    REDIS_URL: str = "redis://127.0.0.1:6379/0"

    # ---------- DeepSeek ----------
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_MODEL: str = "deepseek-chat"

    # ---------- 微信小程序 ----------
    WX_APPID: str = ""
    WX_SECRET: str = ""
    WX_SUBSCRIBE_TEMPLATE_ID: str = ""

    # ---------- 其他 ----------
    UPLOAD_DIR: str = "uploads"
    CORS_ORIGINS: List[str] = ["*"]
    SEED_DEMO: bool = True

    @property
    def sqlalchemy_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        if self.DB_BACKEND.lower() == "mysql":
            return (
                f"mysql+pymysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}"
                f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DB}?charset=utf8mb4"
            )
        return "sqlite:///data/study_life_os.db"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
