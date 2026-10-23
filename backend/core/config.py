import json
from typing import List, Union
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "ICVER - Informal Worker Income Verification System"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"
    DEBUG: bool = False

    # The legacy /score endpoint is deprecated and will be removed.
    LEGACY_SCORE_ENABLED: bool = True

    # Feature override permission
    ALLOW_FEATURE_OVERRIDES: bool = False

    # Affordability policy parameter for the new /verify flow.
    # Assumption (not a regulatory assertion): cap total EMI obligations at 50% of
    # conservative verified income. Lenders must review this against current guidance.
    FOIR_CAP: float = 0.5

    # Database Configuration (MariaDB / MySQL via PyMySQL)
    DATABASE_URL: str = "mysql+pymysql://icver_user:icver_password@localhost:3306/icver_db"

    # CORS Settings
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8000",
    ]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("[") and v.endswith("]"):
                try:
                    return json.loads(v)
                except Exception:
                    pass
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, list):
            return v
        return [str(v)]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )


settings = Settings()
