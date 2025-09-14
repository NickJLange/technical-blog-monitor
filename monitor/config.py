"""
Configuration management for the technical blog monitor.

This module uses pydantic-settings to manage all configuration aspects including:
- Feed sources
- Browser settings
- Caching
- Embedding providers
- Vector databases
- Runtime settings

Configuration is loaded from environment variables, .env files, or mounted secrets.
"""
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlparse

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict


class LogLevel(str, Enum):
    """Log levels supported by the application."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class Environment(str, Enum):
    """Application environment."""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class FeedConfig(BaseModel):
    """Configuration for a single feed source."""
    name: str
    url: AnyHttpUrl
    check_interval_minutes: int = 60
    max_posts_per_check: int = 10
    headers: Dict[str, str] = Field(default_factory=dict)
    enabled: bool = True


class BrowserConfig(BaseModel):
    """Configuration for the headless browser."""
    headless: bool = True
    browser_type: str = "chromium"  # chromium, firefox, webkit
    timeout_seconds: int = 30
    viewport_width: int = 1280
    viewport_height: int = 800
    user_agent: Optional[str] = None
    wait_until: str = "networkidle"  # load, domcontentloaded, networkidle
    screenshot_full_page: bool = True
    screenshot_format: str = "png"  # png, jpeg
    max_concurrent_browsers: int = 3
    disable_javascript: bool = False
    block_ads: bool = True
    stealth_mode: bool = True
    # Optional directory where screenshots are stored. If not provided, defaults to
    # "<cwd>/data/screenshots" and will be created on demand.
    screenshot_dir: Optional[Path] = None

    @field_validator("screenshot_dir")
    def _ensure_screenshot_dir(cls, v: Optional[Path]) -> Optional[Path]:
        if v is not None:
            v.mkdir(parents=True, exist_ok=True)
        return v


class CacheConfig(BaseModel):
    """Configuration for the caching layer."""
    enabled: bool = True
    redis_url: Optional[str] = None
    redis_password: Optional[SecretStr] = None
    cache_ttl_hours: int = 24 * 7  # 1 week default
    local_storage_path: Path = Field(default=Path("./cache"))
    
    @field_validator("local_storage_path")
    def validate_local_storage_path(cls, v: Path) -> Path:
        """Ensure the local storage path exists."""
        v.mkdir(parents=True, exist_ok=True)
        return v


class EmbeddingModelType(str, Enum):
    """Types of embedding models supported."""
    OPENAI = "openai"
    HUGGINGFACE = "huggingface"
    SENTENCE_TRANSFORMERS = "sentence_transformers"
    CUSTOM = "custom"


class EmbeddingConfig(BaseModel):
    """Configuration for embedding generation."""
    text_model_type: EmbeddingModelType = EmbeddingModelType.OPENAI
    text_model_name: str = "text-embedding-ada-002"
    image_model_type: Optional[EmbeddingModelType] = None
    image_model_name: Optional[str] = None
    
    # API credentials
    openai_api_key: Optional[SecretStr] = None
    huggingface_api_key: Optional[SecretStr] = None
    
    # Model parameters
    # Text embedding dimensions; depends on the selected model
    embedding_dimensions: Optional[int] = None
    # Image embedding dimensions (e.g., CLIP defaults to 512)
    image_embedding_dimensions: int = 512
    batch_size: int = 8
    max_retries: int = 3
    timeout_seconds: int = 30
    
    # Local model settings
    local_model_path: Optional[Path] = None
    use_gpu: bool = False
    
    @model_validator(mode='after')
    def validate_model_config(self) -> 'EmbeddingConfig':
        """Validate that required credentials are provided for the chosen model type."""
        if self.text_model_type == EmbeddingModelType.OPENAI and not self.openai_api_key:
            raise ValueError("OpenAI API key is required when using OpenAI embeddings")
        if self.text_model_type == EmbeddingModelType.HUGGINGFACE and not self.huggingface_api_key:
            raise ValueError("HuggingFace API key is required when using HuggingFace embeddings")
        return self


class VectorDBType(str, Enum):
    """Types of vector databases supported."""
    QDRANT = "qdrant"
    CHROMA = "chroma"
    PINECONE = "pinecone"
    MILVUS = "milvus"
    WEAVIATE = "weaviate"


class VectorDBConfig(BaseModel):
    """Configuration for the vector database."""
    db_type: VectorDBType = VectorDBType.QDRANT
    connection_string: str = "http://localhost:6333"
    api_key: Optional[SecretStr] = None
    collection_name: str = "technical_blog_posts"
    
    # Schema configuration
    text_vector_dimension: int = 1536  # Default for OpenAI ada-002
    image_vector_dimension: Optional[int] = None
    distance_metric: str = "cosine"  # cosine, euclidean, dot
    
    # Performance settings
    batch_size: int = 100
    timeout_seconds: int = 30
    
    @field_validator("connection_string")
    def validate_connection_string(cls, v: str) -> str:
        """Validate the connection string format."""
        try:
            parsed = urlparse(v)
            if not parsed.scheme or not parsed.netloc:
                raise ValueError("Invalid URL format")
        except Exception:
            raise ValueError(f"Invalid connection string: {v}")
        return v


class SchedulerConfig(BaseModel):
    """Configuration for the job scheduler."""
    job_store_type: str = "memory"  # memory, redis, sqlalchemy
    job_store_url: Optional[str] = None
    max_instances: int = 1
    timezone: str = "UTC"
    coalesce: bool = True
    misfire_grace_time: int = 60  # seconds


class MetricsConfig(BaseModel):
    """Configuration for metrics and monitoring."""
    enabled: bool = True
    prometheus_enabled: bool = False
    prometheus_port: int = 8000
    log_metrics: bool = True
    log_level: LogLevel = LogLevel.INFO
    structured_logging: bool = True


class WebDashboardConfig(BaseModel):
    """Configuration for the web dashboard."""
    enabled: bool = True
    host: str = "0.0.0.0"
    port: int = 8080
    auto_refresh_seconds: int = 30
    show_mock_data: bool = True  # Show mock data when no real data available


class ArticleProcessingConfig(BaseModel):
    """
    Configuration controlling how individual articles are processed after they
    are discovered in a feed.

    This allows enabling full-content capture, limiting the amount of work the
    daemon does per run, as well as toggling optional summarisation / archival
    features that can be rolled out later without changing code.
    """

    # --- Core behaviour -------------------------------------------------- #
    full_content_capture: bool = True
    """If True the crawler will visit the article URL, render it and extract the
    complete content (text, images, screenshots).  If False only the feed
    metadata is stored."""

    max_articles_per_feed: int = 50
    """Safety-valve: cap how many articles we pull per feed per run to avoid
    runaway processing (e.g. after long downtime)."""

    concurrent_article_tasks: int = 5
    """Number of articles that can be processed concurrently (limits CPU/GPU
    pressure and Playwright browser usage)."""

    # --- Summarisation --------------------------------------------------- #
    generate_summary: bool = False
    """Whether to call an LLM or local model to generate an abstractive summary
    for each article.  Implementation to be wired in later."""

    summary_max_tokens: int = 256
    """Upper bound on tokens the summariser should return (if enabled)."""

    # --- Archival options ------------------------------------------------ #
    archive_html: bool = True
    """Persist the cleaned article HTML to cache / disk for long-term storage."""

    archive_screenshots: bool = True
    """Persist Playwright screenshots of the rendered article."""

    archive_raw: bool = False
    """If True store the raw HTTP response body as well."""

    screenshot_strategy: str = "full"  # full, viewport, none

    @model_validator(mode="after")
    def _sanity_checks(self) -> "ArticleProcessingConfig":
        """Basic sanity checks to keep misconfigurations from blowing up."""
        if self.max_articles_per_feed <= 0:
            raise ValueError("max_articles_per_feed must be positive")
        if not self.full_content_capture and (
            self.archive_html or self.archive_screenshots or self.archive_raw
        ):
            # Archival makes no sense if we are not capturing the page.
            raise ValueError(
                "Archival options require full_content_capture=True"
            )
        if self.concurrent_article_tasks <= 0:
            raise ValueError("concurrent_article_tasks must be positive")
        return self


class Settings(BaseSettings):
    """Main settings class for the technical blog monitor."""
    # Application metadata
    app_name: str = "technical-blog-monitor"
    version: str = "0.1.0"
    environment: Environment = Environment.DEVELOPMENT
    debug: bool = Field(default=False)
    
    # Base paths
    base_dir: Path = Field(default_factory=lambda: Path.cwd())
    data_dir: Path = Field(default_factory=lambda: Path.cwd() / "data")
    
    # Feed sources
    feeds: List[FeedConfig] = Field(default_factory=list)
    feed_list_url: Optional[AnyHttpUrl] = None  # Optional URL to fetch feed list
    
    # Component configurations
    browser: BrowserConfig = Field(default_factory=BrowserConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    vector_db: VectorDBConfig = Field(default_factory=VectorDBConfig)
    # Article processing (full-content capture, summarisation, archival…)
    article_processing: ArticleProcessingConfig = Field(default_factory=ArticleProcessingConfig)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    metrics: MetricsConfig = Field(default_factory=MetricsConfig)
    web_dashboard: WebDashboardConfig = Field(default_factory=WebDashboardConfig)
    
    # Runtime settings
    max_concurrent_tasks: int = 10
    request_timeout_seconds: int = 30
    backoff_max_retries: int = 5
    backoff_max_time: int = 60  # seconds
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
        validate_default=True,
    )
    
    @model_validator(mode='after')
    def create_directories(self) -> 'Settings':
        """Ensure required directories exist."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return self
    
    @field_validator("feeds", mode="before")
    @classmethod
    def _coerce_feeds_from_mapping(cls, v):
        """Allow FEEDS__0__... style env to load as a list in Pydantic v2.
        When pydantic-settings assembles nested env for FEEDS, it may produce
        a mapping like {"0": {...}, "1": {...}}; convert to a list ordered by key.
        """
        if isinstance(v, dict):
            try:
                return [v[k] for k in sorted(v.keys(), key=lambda x: int(x))]
            except Exception:
                return list(v.values())
        return v

    @field_validator("feeds")
    def validate_feeds(cls, feeds: List[FeedConfig]) -> List[FeedConfig]:
        """Validate that feed names are unique."""
        feed_names = [feed.name for feed in feeds]
        if len(feed_names) != len(set(feed_names)):
            raise ValueError("Feed names must be unique")
        return feeds
    
    def get_feed_by_name(self, name: str) -> Optional[FeedConfig]:
        """Get a feed configuration by name."""
        for feed in self.feeds:
            if feed.name == name:
                return feed
        return None


def load_settings() -> Settings:
    """Load settings from environment variables and .env file."""
    return Settings()

