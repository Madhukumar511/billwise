from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./billwise.db"
    upload_dir: str = "./uploads"
    anthropic_api_key: str = ""
    llm_model: str = "claude-sonnet-4-6"
    max_upload_mb: int = 10

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
