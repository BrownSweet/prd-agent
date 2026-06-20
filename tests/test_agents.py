from __future__ import annotations

import pytest

from prd_agent.agents import AgentFactory
from prd_agent.settings import Settings


@pytest.mark.filterwarnings("ignore::DeprecationWarning")
def test_agent_activates_only_requested_skill(monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test")
    monkeypatch.setenv("LLM_MODEL", "deepseek/deepseek-chat")
    monkeypatch.setenv(
        "DATABASE_URL",
        "mysql+pymysql://user:password@localhost/prd_agent?charset=utf8mb4",
    )
    monkeypatch.setenv(
        "TEST_DATABASE_URL",
        "mysql+pymysql://user:password@localhost/prd_agent_test?charset=utf8mb4",
    )
    settings = Settings()

    factory = AgentFactory(settings)
    agent = factory.product_analyst("structure-requirements")

    assert factory.llm.provider == "deepseek"
    assert factory.llm.model == "deepseek-chat"
    assert factory.supports_native_structured_output is False
    assert agent.skills is not None
    assert [skill.name for skill in agent.skills] == ["structure-requirements"]
    assert agent.skills[0].instructions
    assert agent.skills[0].resource_files == {
        "references": ["requirements-contract.md"]
    }


@pytest.mark.filterwarnings("ignore::DeprecationWarning")
def test_agent_supports_custom_openai_compatible_endpoint() -> None:
    settings = Settings(
        _env_file=None,
        database_url=(
            "mysql+pymysql://user:password@localhost/"
            "prd_agent?charset=utf8mb4"
        ),
        test_database_url=(
            "mysql+pymysql://user:password@localhost/"
            "prd_agent_test?charset=utf8mb4"
        ),
        llm_model="custom-model-id",
        llm_provider="openai",
        llm_api_key="test",
        llm_base_url="http://localhost:8000/v1",
    )

    llm = AgentFactory(settings).llm

    assert llm.provider == "openai"
    assert llm.model == "custom-model-id"
    assert llm.base_url == "http://localhost:8000/v1"


def test_native_structured_output_can_be_overridden() -> None:
    settings = Settings(
        _env_file=None,
        database_url=(
            "mysql+pymysql://user:password@localhost/"
            "prd_agent?charset=utf8mb4"
        ),
        test_database_url=(
            "mysql+pymysql://user:password@localhost/"
            "prd_agent_test?charset=utf8mb4"
        ),
        llm_model="deepseek/deepseek-chat",
        llm_api_key="test",
        llm_native_structured_output=True,
    )

    assert AgentFactory(settings).supports_native_structured_output is True
