from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="INFD_", env_file=".env", extra="ignore")

    app_name: str = "InfDrawing API"
    debug: bool = True

    ollama_base_url: str = "http://127.0.0.1:11434/v1"
    ollama_model: str = "qwen2.5:7b-instruct"

    comfyui_base_url: str = "http://127.0.0.1:8188"
    comfyui_output_dir: Path = Path(r"D:\ComfyUI\output")

    dashscope_api_key: str = ""

    repo_root: Path = Path(__file__).resolve().parents[2]
    data_dir: Path = repo_root / "data"
    uploads_dir: Path = data_dir / "uploads"
    outputs_dir: Path = data_dir / "outputs"
    logs_dir: Path = data_dir / "logs"

    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]


settings = Settings()
