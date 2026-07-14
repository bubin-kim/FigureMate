"""애플리케이션 설정. .env 파일에서 환경 변수를 로드한다.

M1 작업지시서(docs/milestones/M1.md) Step 1 참고.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- LLM Provider Layer (app/core/llm/) ---
    # 기본값 mock: .env 무설정 상태에서는 어떤 유료 API도 호출되지 않는다 (CLAUDE.md 가드레일).
    # Anthropic은 임베딩 API가 없으므로 LLM/임베딩 Provider를 별도 env로 분리한다 (사용자 결정).
    llm_provider: str = "mock"        # mock | ollama | anthropic | openai(슬롯 예약)
    embedding_provider: str = "mock"  # mock | ollama

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"  # M3 텍스트 매칭 검증용 (텍스트 전용)
    # M4 explainer용 (Vision 필수 — 텍스트 모델과 분리). 3b→7b 승격(2026-07-14 실측):
    # 3b는 확률적 JSON 파싱 실패·영어 혼입·한자 혼입이 잦았고, 7b는 어려운 케이스 4/4에서
    # 첫 시도 파싱+깨끗한 한국어 (대가: warm ~20초/Figure, 3b의 ~3배).
    ollama_vision_model: str = "qwen2.5vl:7b"
    ollama_embedding_model: str = "nomic-embed-text"

    database_url: str = "postgresql+psycopg://figuremate:figuremate@localhost:5432/figuremate"

    storage_backend: str = "local"
    storage_local_path: str = "./storage"

    app_env: str = "development"
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
