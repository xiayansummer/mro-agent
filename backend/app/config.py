import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    DB_HOST: str = os.getenv("DB_HOST", "39.107.14.53")
    DB_PORT: int = int(os.getenv("DB_PORT", "3307"))
    DB_USER: str = os.getenv("DB_USER", "")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "")
    DB_NAME: str = os.getenv("DB_NAME", "d_mymro_sample")

    AI_API_KEY: str = os.getenv("AI_API_KEY", "")
    AI_BASE_URL: str = os.getenv("AI_BASE_URL", "")
    AI_MODEL: str = os.getenv("AI_MODEL", "qwen-plus")

    MEMOS_URL: str = os.getenv("MEMOS_URL", "http://localhost:5230")
    MEMOS_ACCESS_TOKEN: str = os.getenv("MEMOS_ACCESS_TOKEN", "")
    MEMOS_USERNAME: str = os.getenv("MEMOS_USERNAME", "mro-admin")
    MEMOS_PASSWORD: str = os.getenv("MEMOS_PASSWORD", "mro-memory-2026")

    @property
    def database_url(self) -> str:
        return (
            f"mysql+aiomysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
            "?charset=utf8mb4"
        )


settings = Settings()
