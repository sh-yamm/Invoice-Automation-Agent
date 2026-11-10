"""Runtime settings, read from the repository-level .env file and the environment."""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    nvidia_api_key: str = ""
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    parse_url: str = "https://ai.api.nvidia.com/v1/retrieval/nvidia/nemotron-3.5-parse/parse"
    model_parse: str = "nvidia/nemotron-3.5-parse"
    model_extract: str = "nvidia/nemotron-3.5-super-vl-120b-a12b"  # vision: scanned invoices (Mistral timed out)
    model_extract_text: str = "nvidia/nemotron-3-ultra-550b-a55b"  # text: digital invoices (much faster)
    model_fast: str = "nvidia/nemotron-3-ultra-550b-a55b"
    model_agent: str = "nvidia/nemotron-3-ultra-550b-a55b"
    model_embed: str = "nvidia/nemotron-3.5-embed-1b"
    # Backups, tried in order when a model stays down after its retries (each checked live on 2026-11-11).
    fallback_vision: list[str] = ["mistralai/mistral-large-4-1t-a52b", "google/gemma-4-31b-it"]
    fallback_text: list[str] = ["mistralai/mistral-large-4-1t-a52b", "deepseek-ai/deepseek-v4.1-flash"]
    llm_max_rpm: int = 35

    rulebook_path: Path = REPO_ROOT / "rulebook" / "aop.yaml"
    erp_dir: Path = REPO_ROOT / "data" / "erp"
    seed_path: Path = REPO_ROOT / "data" / "seed" / "history.json"
    samples_dir: Path = REPO_ROOT / "samples"
    storage_dir: Path = REPO_ROOT / "storage"
