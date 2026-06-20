from __future__ import annotations

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine

from prd_agent.repositories import SQLAlchemyRepository
from prd_agent.settings import Settings

PRODUCTION_URL = (
    "mysql+pymysql://user:password@localhost:3306/prd_agent?charset=utf8mb4"
)
TEST_URL = (
    "mysql+pymysql://user:password@localhost:3306/prd_agent_test?charset=utf8mb4"
)


@pytest.fixture(autouse=True)
def clear_llm_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "LLM_MODEL",
        "LLM_API_KEY",
        "LLM_BASE_URL",
        "LLM_PROVIDER",
        "OPENAI_MODEL",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)


def test_settings_accept_separate_mysql_databases() -> None:
    settings = Settings(
        _env_file=None,
        database_url=PRODUCTION_URL,
        test_database_url=TEST_URL,
    )
    assert settings.database_url == PRODUCTION_URL
    assert settings.test_database_url == TEST_URL


def test_settings_allow_missing_database_for_setup_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)

    settings = Settings(_env_file=None)

    assert settings.database_url is None
    assert settings.test_database_url is None


def test_settings_resolve_provider_neutral_llm_configuration() -> None:
    settings = Settings(
        _env_file=None,
        database_url=PRODUCTION_URL,
        test_database_url=TEST_URL,
        llm_model="deepseek-chat",
        llm_provider="deepseek",
        llm_api_key="secret",
    )

    settings.require_llm()

    assert settings.resolved_llm_model == "deepseek-chat"
    assert settings.resolved_llm_api_key == "secret"


def test_settings_strip_duplicate_explicit_provider_prefix() -> None:
    settings = Settings(
        _env_file=None,
        database_url=PRODUCTION_URL,
        test_database_url=TEST_URL,
        llm_model="deepseek/deepseek-chat",
        llm_provider="deepseek",
        llm_api_key="secret",
    )

    assert settings.resolved_llm_model == "deepseek-chat"


def test_settings_allow_keyless_local_llm() -> None:
    settings = Settings(
        _env_file=None,
        database_url=PRODUCTION_URL,
        test_database_url=TEST_URL,
        llm_model="ollama/llama3.2",
    )

    settings.require_llm()

    assert settings.resolved_llm_api_key is None


def test_settings_support_legacy_openai_configuration() -> None:
    settings = Settings(
        _env_file=None,
        database_url=PRODUCTION_URL,
        test_database_url=TEST_URL,
        openai_model="gpt-4o-mini",
        openai_api_key="legacy-secret",
    )

    settings.require_llm()

    assert settings.resolved_llm_model == "openai/gpt-4o-mini"
    assert settings.resolved_llm_api_key == "legacy-secret"


def test_settings_reject_bare_model_without_provider() -> None:
    settings = Settings(
        _env_file=None,
        database_url=PRODUCTION_URL,
        test_database_url=TEST_URL,
        llm_model="custom-model-id",
    )

    with pytest.raises(ValueError, match="provider/model"):
        settings.require_llm()


def test_settings_reject_invalid_llm_base_url() -> None:
    with pytest.raises(ValidationError, match="HTTP\\(S\\)"):
        Settings(
            _env_file=None,
            database_url=PRODUCTION_URL,
            test_database_url=TEST_URL,
            llm_model="deepseek/deepseek-chat",
            llm_base_url="not-a-url",
        )


def test_settings_accept_blank_native_structured_output_flag() -> None:
    settings = Settings(
        _env_file=None,
        database_url=PRODUCTION_URL,
        test_database_url=TEST_URL,
        llm_model="deepseek/deepseek-chat",
        llm_native_structured_output="",
    )

    assert settings.llm_native_structured_output is None


@pytest.mark.parametrize(
    ("database_url", "test_database_url", "message"),
    [
        ("sqlite://", TEST_URL, "mysql\\+pymysql"),
        (PRODUCTION_URL, PRODUCTION_URL, "_test"),
        (
            "mysql+pymysql://user:password@localhost:3306/shared_test?charset=utf8mb4",
            "mysql+pymysql://other:password@localhost:3306/shared_test?charset=utf8mb4",
            "不同数据库",
        ),
        (
            PRODUCTION_URL,
            "mysql+pymysql://user:password@localhost:3306/prd_agent_test",
            "utf8mb4",
        ),
    ],
)
def test_settings_reject_invalid_database_configuration(
    database_url: str,
    test_database_url: str,
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        Settings(
            _env_file=None,
            database_url=database_url,
            test_database_url=test_database_url,
        )


def test_repository_rejects_non_mysql_engine() -> None:
    with pytest.raises(ValueError, match="仅支持MySQL"):
        SQLAlchemyRepository(create_engine("sqlite://"))
