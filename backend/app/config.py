from pathlib import Path
from urllib.parse import urlparse

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration with strict production validation."""

    model_config = SettingsConfigDict(env_prefix="INFD_", env_file=".env", extra="ignore")

    app_name: str = "InfDrawing API"
    debug: bool = True
    environment: str = "development"
    request_id_header: str = "X-Request-ID"

    llm_provider: str = "deepseek"
    ollama_base_url: str = "http://127.0.0.1:11434/v1"
    ollama_model: str = "qwen2.5:7b-instruct"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    openai_api_key: str = ""
    openai_image_model: str = "gpt-image-1"
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"
    deepseek_api_key: str = ""
    provider_allowed_hosts: list[str] = [
        "api.openai.com",
        "api.deepseek.com",
        "dashscope.aliyuncs.com",
        "127.0.0.1",
        "localhost",
    ]
    intent_confidence_threshold: float = 0.65

    comfyui_base_url: str = "http://127.0.0.1:8188"
    comfyui_output_dir: Path = Path(r"D:\ComfyUI\output")

    dashscope_api_key: str = Field(
        default="",
        validation_alias=AliasChoices(
            "dashscope_api_key", "INFD_DASHSCOPE_API_KEY", "INFD_ALIBABA_API_KEY"
        ),
    )
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/api/v1"
    dashscope_t2i_model: str = "wanx2.1-t2i-turbo"
    dashscope_edit_model: str = "wanx2.1-imageedit"
    cloud_image_timeout_seconds: float = 180.0
    cloud_image_poll_seconds: float = 2.0

    cedit_vision_model: str = "gpt-4o"
    cedit_vision_timeout_seconds: float = 90.0
    cedit_preserve_threshold: float = 0.7
    cedit_composition_threshold: float = 0.75
    cedit_max_retries: int = 1
    cedit_max_reference_images: int = 4
    cedit_input_fidelity: str = "high"
    cedit_max_entities: int = 30
    cedit_scene_provider: str = "dashscope"
    cedit_scene_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    cedit_scene_model: str = "qwen3-vl-plus"
    cedit_scene_bbox_format: str = "xyxy_1000"
    cedit_image_provider: str = "dashscope"
    cedit_image_model: str = "qwen-image-edit-plus"
    cedit_lock_feather: float = 0.12
    cedit_lock_paste: bool = False
    cedit_prompt_style: str = "preserve"
    cedit_subject_shift_threshold: float = 0.08
    cedit_subject_area_threshold: float = 0.15

    persistence_backend: str = "memory"
    database_url: str = ""
    redis_url: str = ""
    storage_backend: str = "local"
    s3_endpoint_url: str = ""
    s3_bucket: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    api_key_pepper: str = ""
    auth_required: bool = False
    rate_limit_per_minute: int = 60
    job_timeout_seconds: int = 600
    job_max_retries: int = 2
    job_lease_seconds: int = 90
    sse_heartbeat_seconds: float = 15.0
    sse_poll_seconds: float = 1.0
    gpu_concurrency: int = 1
    queue_gpu: str = "jobs:gpu"
    queue_cpu: str = "jobs:cpu"
    queue_api: str = "jobs:api"
    max_upload_bytes: int = 20 * 1024 * 1024
    max_image_pixels: int = 40_000_000
    redact_log_fields: list[str] = [
        "authorization",
        "api_key",
        "openai_api_key",
        "deepseek_api_key",
        "dashscope_api_key",
        "s3_secret_key",
    ]

    repo_root: Path = Path(__file__).resolve().parents[2]
    data_dir: Path = repo_root / "data"
    uploads_dir: Path = data_dir / "uploads"
    outputs_dir: Path = data_dir / "outputs"
    artifacts_dir: Path = data_dir / "artifacts"
    logs_dir: Path = data_dir / "logs"

    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, value: str) -> str:
        """Normalize and validate the deployment environment."""
        normalized = value.lower()
        if normalized not in {"development", "test", "production"}:
            raise ValueError("environment must be development, test, or production")
        return normalized

    def validate_runtime(self) -> None:
        """Fail fast when production infrastructure or security is incomplete."""
        if self.auth_required and len(self.api_key_pepper) < 32:
            raise RuntimeError("api_key_pepper must contain at least 32 characters")
        if self.environment != "production":
            return
        missing: list[str] = []
        if self.persistence_backend != "postgres" or not self.database_url:
            missing.append("database_url with persistence_backend=postgres")
        elif not self.database_url.startswith("postgresql+asyncpg://"):
            missing.append("database_url using postgresql+asyncpg://")
        if not self.redis_url:
            missing.append("redis_url")
        if self.storage_backend != "s3":
            missing.append("storage_backend=s3")
        for name in ("s3_endpoint_url", "s3_bucket", "s3_access_key", "s3_secret_key"):
            if not getattr(self, name):
                missing.append(name)
        if not self.auth_required:
            missing.append("auth_required=true")
        if self.debug:
            missing.append("debug=false")
        if any("localhost" in origin or "127.0.0.1" in origin for origin in self.cors_origins):
            missing.append("non-local cors_origins")
        if missing:
            raise RuntimeError(f"Invalid production configuration: {', '.join(missing)}")

    def validate_provider_url(self, url: str) -> None:
        """Reject provider URLs that could be used for SSRF."""
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("provider URL must be absolute HTTP(S)")
        if parsed.hostname not in set(self.provider_allowed_hosts):
            raise ValueError("provider host is not allowlisted")
        if self.environment == "production" and parsed.scheme != "https":
            raise ValueError("provider URL must use HTTPS in production")


settings = Settings()
