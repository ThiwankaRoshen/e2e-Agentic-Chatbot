from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    
    Required variables will raise a validation error if missing.
    Optional variables have sensible defaults.
    """
    
    # Required - will raise ValidationError if missing
    OPENAI_API_KEY: str = Field(
        ...,
        description="OpenAI API key for LLM inference"
    )
    MISTRAL_API_KEY: str = Field(
        ...,
        description="Mistral API key for LLM inference"
    )
    OPENAI_EMBEDDING_MODEL_API_KEY: str = Field(
        ...,
        description="OpenAI API key for embedding models"
    )
    TAVILY_API_KEY: str = Field(
        ...,
        description="Tavily API key for search functionality"
    )
    ALPHA_VANTAGE_API_KEY: str = Field(
        ...,
        description="Alpha Vantage API key for financial data"
    )
    
    # Optional with defaults
    OPENAI_API_BASE: str = Field(
        default="https://models.github.ai/inference",
        description="Base URL for OpenAI API calls"
    )
    OPENAI_MODEL_NAME: str = Field(
        default="openai/gpt-4o-mini",
        description="OpenAI model name to use"
    )
    SQLITE_DB_PATH: str = Field(
        default="chatbot_state.db",
        description="Path to SQLite database file"
    )
    FAISS_INDEX_PATH: str = Field(
        default="faiss_index",
        description="Path to FAISS index directory"
    )
    CORS_ORIGINS: str = Field(
        default="http://localhost:3000",
        description="Comma-separated list of allowed CORS origins"
    )
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
        frozen=False,  # Set to True if you want immutable settings
    )
    
    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS origins into a list."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]


# Create a singleton instance
settings = Settings()

 