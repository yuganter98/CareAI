from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "CareAI"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"  # "production" in prod
    ALLOWED_ORIGINS: list[str] = ["http://localhost:3000"]
    
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_SERVER: str
    POSTGRES_PORT: int
    POSTGRES_DB: str
    DATABASE_URL: str
    
    SECRET_KEY: str
    ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int
    REFRESH_TOKEN_EXPIRE_DAYS: int
    
    # Storage
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE_MB: int = 10

    # AI Config
    OPENAI_API_KEY: str | None = None
    OPENAI_API_BASE: str | None = None
    # Model name sent to the OpenAI-compatible endpoint (LM Studio ignores it,
    # OpenAI / other providers need a real model id).
    LLM_MODEL: str = "gpt-4o-mini"
    # Ceiling on reply length for every agent call (see agents/llm_client.py).
    # The agents return a short JSON object or a few paragraphs, so 1500 is
    # generous; it exists to stop a provider pricing each request at the
    # model's full 16k output window, which makes a key with modest credit
    # refuse every call. Raise it if the truncation warning ever fires.
    LLM_MAX_TOKENS: int = 1500

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
