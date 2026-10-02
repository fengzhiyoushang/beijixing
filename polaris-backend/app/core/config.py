"""全局配置：环境变量 / .env 注入，统一由此读取。"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── 应用 ──
    APP_NAME: str = "Polaris Terminal API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    API_PREFIX: str = "/api/v1"

    # ── 数据库 ──
    DB_BACKEND: str = "mysql"          # mysql | sqlite
    MYSQL_HOST: str = "127.0.0.1"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "root"
    MYSQL_PASSWORD: str = "root"
    MYSQL_DB: str = "polaris_terminal"
    MYSQL_CHARSET: str = "utf8mb4"
    SQLITE_PATH: str = "data/polaris.db"
    DB_ECHO: bool = False

    # ── Redis ──
    REDIS_URL: str = "redis://127.0.0.1:6379/0"
    REDIS_ENABLED: bool = True
    CACHE_TTL: int = 300

    # ── 认证 ──
    JWT_SECRET: str = "polaris-terminal-dev-secret-please-change"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7

    # ── DeepSeek ──
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_MODEL: str = "deepseek-chat"
    DEEPSEEK_VL_MODEL: str = "deepseek-vl"
    DEEPSEEK_TIMEOUT: int = 60
    MAX_TOOL_ROUNDS: int = 4

    # ── 向量 / RAG ──
    EMBEDDING_PROVIDER: str = "local"   # local | deepseek
    EMBEDDING_MODEL: str = "deepseek-embedding"
    EMBEDDING_DIM: int = 512
    RAG_CHUNK_SIZE: int = 500
    RAG_CHUNK_OVERLAP: int = 80
    RAG_TOP_K: int = 5

    # ── 其它 ──
    CORS_ORIGINS: str = "http://localhost:5200,http://127.0.0.1:5200"
    UPLOAD_DIR: str = "uploads"
    BACKUP_DIR: str = "backups"
    MAX_UPLOAD_MB: int = 20

    # ── 微信小程序（订阅消息推送）──
    WX_APPID: str = ""
    WX_APP_SECRET: str = ""
    WX_TEMPLATE_DDL: str = ""          # 任务到期提醒模板 ID
    WX_TEMPLATE_CLASS: str = ""        # 上课提醒模板 ID
    WX_MP_STATE: str = "formal"        # formal | trial | developer
    WX_PUSH_ENABLED: bool = True       # 是否允许推送（仍受配额与配置限制）
    WX_DDL_AHEAD_MINUTES: int = 180    # DDL 提前多少分钟提醒
    WX_CLASS_AHEAD_MINUTES: int = 30   # 上课提前多少分钟提醒
    WX_SCHEDULER_ENABLED: bool = False  # 进程内定时扫描（生产建议用 cron 调 scripts/push_reminders.py）
    WX_PUSH_INTERVAL_MIN: int = 10

    # ── 派生属性 ──
    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def sqlalchemy_url(self) -> str:
        """当前生效的数据库连接串（MySQL；不可用时由 database 层回退 SQLite）。"""
        if self.DB_BACKEND.lower() == "sqlite":
            return self.sqlite_url
        return (
            f"mysql+pymysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DB}"
            f"?charset={self.MYSQL_CHARSET}"
        )

    @property
    def sqlite_url(self) -> str:
        path = Path(self.SQLITE_PATH)
        if not path.is_absolute():
            path = BASE_DIR / path
        path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{path}"

    @property
    def mysql_server_url(self) -> str:
        """不带库名的连接串，用于 init_db 建库。"""
        return (
            f"mysql+pymysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/?charset={self.MYSQL_CHARSET}"
        )

    @property
    def upload_path(self) -> Path:
        p = BASE_DIR / self.UPLOAD_DIR
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def backup_path(self) -> Path:
        p = BASE_DIR / self.BACKUP_DIR
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def deepseek_configured(self) -> bool:
        return bool(self.DEEPSEEK_API_KEY.strip())

    @property
    def wechat_configured(self) -> bool:
        return bool(self.WX_APPID.strip() and self.WX_APP_SECRET.strip())

    def template_of(self, kind: str) -> str:
        return self.WX_TEMPLATE_DDL if kind == "ddl" else self.WX_TEMPLATE_CLASS


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
