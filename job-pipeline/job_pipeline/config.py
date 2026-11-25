from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import quote_plus

from dotenv import load_dotenv

load_dotenv()


def _int_setting(name: str, default: int) -> int:
    value = os.getenv(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _bool_setting(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
    candidate_position: str = os.getenv("CANDIDATE_POSITION", "")
    candidate_stack: str = os.getenv("CANDIDATE_STACK", "")
    candidate_experience: str = os.getenv("CANDIDATE_EXPERIENCE", "")
    candidate_resume_file: str = os.getenv("CANDIDATE_RESUME_FILE", "")
    hh_client_id: str = os.getenv("HH_CLIENT_ID", "")
    hh_client_secret: str = os.getenv("HH_CLIENT_SECRET", "")
    hh_user_agent: str = os.getenv("HH_USER_AGENT", "job-pipeline/1.0")
    hh_search_query: str = os.getenv("HH_SEARCH_QUERY", "Системный аналитик OR Project Manager")
    hh_area: int = _int_setting("HH_AREA", 113)
    hh_per_page: int = _int_setting("HH_PER_PAGE", 15)
    hh_max_pages: int = _int_setting("HH_MAX_PAGES", 2)
    hh_request_delay: float = float(os.getenv("HH_REQUEST_DELAY", "3"))
    hh_scan_interval_minutes: int = _int_setting("HH_SCAN_INTERVAL_MINUTES", 360)
    bot_demo_mode: bool = _bool_setting("BOT_DEMO_MODE")

    def __post_init__(self):
        if self.bot_demo_mode:
            database_name = os.getenv("DB_NAME") or os.getenv("MYSQL_DATABASE") or ""
            if not database_name.endswith("_test"):
                raise ValueError(
                    "BOT_DEMO_MODE requires DB_NAME to end with '_test' "
                    "so the demo cannot use the production database"
                )
            object.__setattr__(
                self,
                "database_url",
                self._build_database_url(database_name),
            )
            return
        object.__setattr__(
            self,
            "database_url",
            self.database_url or self._build_database_url(),
        )

    @staticmethod
    def _build_database_url(database_name: str | None = None) -> str:
        db_user = os.getenv("DB_USER") or os.getenv("MYSQL_USER") or "root"
        db_password = os.getenv("DB_PASSWORD") or os.getenv("MYSQL_PASSWORD") or ""
        db_host = os.getenv("DB_HOST") or os.getenv("MYSQL_HOST") or "127.0.0.1"
        db_port = os.getenv("DB_PORT") or os.getenv("MYSQL_PORT") or "3306"
        db_name = (
            database_name
            or os.getenv("DB_NAME")
            or os.getenv("MYSQL_DATABASE")
            or "hh_automation"
        )
        return (
            f"mysql+mysqlconnector://{quote_plus(db_user)}:{quote_plus(db_password)}"
            f"@{db_host}:{db_port}/{db_name}"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
