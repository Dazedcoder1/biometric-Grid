from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_env_file() -> Path:
    """Locate the repository's single .env by walking up from this file.

    There is exactly one .env for the whole project, at the repository root,
    shared by the backend and the frontend. Resolving it from __file__ rather
    than the working directory means `uvicorn`, `alembic` and the seed script
    all find it no matter which folder you launch them from.
    """
    for directory in Path(__file__).resolve().parents:
        candidate = directory / ".env"
        if candidate.is_file():
            return candidate
    # Nothing found: hand back the conventional path so pydantic raises a
    # "field required" error naming the missing keys, which is a far better
    # message than anything we could invent here.
    return Path(__file__).resolve().parents[2] / ".env"


ENV_FILE = _find_env_file()


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

    # --- Credential vault: key management ---
    # "mock"  -> local KEK from KMS_MOCK_KEY. Development only.
    # "aws"   -> real AWS KMS via boto3, KMS_KEY_ID names the key.
    # The interface is identical either way; only custody differs.
    KMS_PROVIDER: str = "mock"
    KMS_KEY_ID: str = "local-dev-kek-v1"
    # 32 url-safe base64 bytes. Generate with:
    #   python -c "import base64,os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
    KMS_MOCK_KEY: str = ""
    AWS_REGION: str = "ap-south-1"

    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

settings = Settings()
