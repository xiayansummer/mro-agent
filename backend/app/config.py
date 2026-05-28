import os
from urllib.parse import quote_plus

from dotenv import load_dotenv

load_dotenv()


def _csv_env(name: str, default: str = "") -> list[str]:
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


class Settings:
    APP_ENV: str = os.getenv("APP_ENV", "development")

    DB_HOST: str = os.getenv("DB_HOST", "127.0.0.1")
    DB_PORT: int = int(os.getenv("DB_PORT", "3306"))
    DB_USER: str = os.getenv("DB_USER", "")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "")
    DB_NAME: str = os.getenv("DB_NAME", "mro_agent_dev")

    AI_API_KEY: str = os.getenv("AI_API_KEY", "")
    AI_BASE_URL: str = os.getenv("AI_BASE_URL", "")
    AI_MODEL: str = os.getenv("AI_MODEL", "qwen-plus")
    AI_VISION_MODEL: str = os.getenv("AI_VISION_MODEL", "qwen-vl-plus")

    MEMOS_URL: str = os.getenv("MEMOS_URL", "http://localhost:5230")
    MEMOS_ACCESS_TOKEN: str = os.getenv("MEMOS_ACCESS_TOKEN", "")
    MEMOS_USERNAME: str = os.getenv("MEMOS_USERNAME", "mro-admin")
    MEMOS_PASSWORD: str = os.getenv("MEMOS_PASSWORD", "")

    # Invite token required for user registration. Empty = registration open (dev mode).
    REGISTER_TOKEN: str = os.getenv("REGISTER_TOKEN", "")
    CORS_ORIGINS: list[str] = _csv_env(
        "CORS_ORIGINS",
        "http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173",
    )

    @property
    def database_url(self) -> str:
        # URL-encode credentials so special characters (e.g. @ in password) don't break URL parsing
        return (
            f"mysql+aiomysql://{quote_plus(self.DB_USER)}:{quote_plus(self.DB_PASSWORD)}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
            "?charset=utf8mb4"
        )

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.lower() in {"production", "prod"}

    def validate(self) -> None:
        if not self.is_production:
            return
        missing = []
        if not self.REGISTER_TOKEN:
            missing.append("REGISTER_TOKEN")
        if not self.CORS_ORIGINS:
            missing.append("CORS_ORIGINS")
        if self.MEMOS_URL and not (self.MEMOS_ACCESS_TOKEN or self.MEMOS_PASSWORD):
            missing.append("MEMOS_ACCESS_TOKEN or MEMOS_PASSWORD")
        if missing:
            raise RuntimeError(
                "Missing required production configuration: " + ", ".join(missing)
            )


settings = Settings()
settings.validate()
