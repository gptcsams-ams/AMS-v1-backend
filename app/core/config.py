from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str

    SECRET_KEY: str
    ALGORITHM: str = "HS256"

    # Fernet key for encrypting SMTP passwords (email_settings). Generate with:
    # python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    ENCRYPTION_KEY: str = ""

    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    ENVIRONMENT: str = "production"
    SCHOOL_NAME: str = "AMS School"

    MEDIA_ROOT: str = "/app/media"

    INSIGHTFACE_MODEL: str = "buffalo_s"
    INSIGHTFACE_CTX_ID: int = -1
    MAX_CONCURRENT_WORKERS: int = 30

    STORAGE_BACKEND: str = "local"

    IMAGEKIT_PUBLIC_KEY: Optional[str] = None
    IMAGEKIT_PRIVATE_KEY: Optional[str] = None
    IMAGEKIT_URL_ENDPOINT: Optional[str] = None

    MINIO_ENDPOINT: Optional[str] = None
    MINIO_ACCESS_KEY: Optional[str] = None
    MINIO_SECRET_KEY: Optional[str] = None
    MINIO_BUCKET: str = "ams-media"

    TWILIO_ACCOUNT_SID: Optional[str] = None
    TWILIO_AUTH_TOKEN: Optional[str] = None
    TWILIO_WHATSAPP_FROM: Optional[str] = None

    MSG91_API_KEY: Optional[str] = None
    MSG91_SENDER_ID: Optional[str] = None
    MSG91_FLOW_ID: Optional[str] = None

    SENDGRID_API_KEY: Optional[str] = None
    SENDGRID_FROM_EMAIL: Optional[str] = None
    SENDGRID_WEBHOOK_PUB_KEY: Optional[str] = None
    EMAIL_FROM: Optional[str] = None  # alias kept for backward compat

    # Global SMTP fallback — used for parent/attendance emails when a branch has
    # no active email_settings row. Configure once here instead of per-branch.
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None        # plaintext app password (env only)
    SMTP_SENDER_NAME: Optional[str] = None
    SMTP_SENDER_EMAIL: Optional[str] = None

    DEFAULT_ATTENDANCE_THRESHOLD: float = 75.0
    NOTIFICATION_THROTTLE_DEFAULT_MIN: int = 60

    # Parent Portal — base URL used to build {{portal_link}} in notifications.
    PARENT_PORTAL_BASE_URL: str = "https://ams.school.com"

    RATE_LIMIT_PER_MINUTE: int = 120
    ALLOWED_ORIGINS: str = "*"

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
