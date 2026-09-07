from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "GridSphere IoT Core"
    DATABASE_URL: str
    REDIS_URL: str | None = None

    MQTT_BROKER: str
    MQTT_PORT: int = 1883
    MQTT_USER: str = ""
    MQTT_PASS: str = ""

    # --- JWT signing ---
    # Anyone holding this value can mint a token for any user, so it must never
    # be committed. Blank falls back to a random per-process key, which is safe
    # but logs everyone out on restart — see app/core/security.py.
    JWT_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # --- Task manager / GitHub integration ---
    # Fernet key used to encrypt per-tenant GitHub tokens at rest.
    # Blank disables GitHub features; manual tasks still work.
    GITHUB_ENC_KEY: str = ""
    # Minutes between reconcile passes that catch webhook deliveries we missed.
    # 0 disables the background loop (webhooks still work).
    GITHUB_SYNC_INTERVAL_MINUTES: int = 30
    # Cap issues pulled per repo per reconcile, to stay inside rate limits.
    GITHUB_SYNC_PAGE_LIMIT: int = 3

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
