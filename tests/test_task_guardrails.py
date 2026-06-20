from __future__ import annotations

from types import SimpleNamespace

from prd_agent.agents import AgentFactory
from prd_agent.models import BusinessRule, PrdResult, RequirementStructureResult
from prd_agent.settings import Settings
from prd_agent.tasks import CrewAITaskExecutor, output_guardrail

from conftest import PRD_HEADINGS, complete_spec, document

DATABASE_URL = (
    "mysql+pymysql://user:password@localhost/prd_agent?charset=utf8mb4"
)
TEST_DATABASE_URL = (
    "mysql+pymysql://user:password@localhost/prd_agent_test?charset=utf8mb4"
)


def test_prd_guardrail_rejects_missing_sections() -> None:
    result = PrdResult(
        markdown="## 文档信息\n内容",
        business_rules=[BusinessRule(rule_id="R-001", description="规则")],
    )
    ok, message = output_guardrail(PrdResult)(
        SimpleNamespace(pydantic=result, raw="{}")
    )
    assert not ok
    assert "缺少章节" in message


def test_prd_guardrail_accepts_complete_document() -> None:
    result = PrdResult(
        markdown=document(PRD_HEADINGS, "内容"),
        business_rules=[BusinessRule(rule_id="R-001", description="规则")],
    )
    ok, raw = output_guardrail(PrdResult)(
        SimpleNamespace(pydantic=result, raw='{"ok": true}')
    )
    assert ok
    assert raw == '{"ok": true}'


def test_structure_guardrail_rejects_incomplete_result_without_questions() -> None:
    spec = complete_spec()
    spec.completeness.interactions_clear = False
    result = RequirementStructureResult(
        requirement_spec=spec,
        questions=[],
        summary_markdown="✅ 信息充分。请求进入步骤2。",
    )

    ok, message = output_guardrail(RequirementStructureResult)(
        SimpleNamespace(pydantic=result, raw="{}")
    )

    assert not ok
    assert "结构化需求仍不完整" in message


def test_deepseek_task_uses_prompt_validated_json() -> None:
    factory = AgentFactory(
        Settings(
            _env_file=None,
            database_url=DATABASE_URL,
            test_database_url=TEST_DATABASE_URL,
            llm_model="deepseek-chat",
            llm_provider="deepseek",
            llm_api_key="test",
        )
    )
    executor = CrewAITaskExecutor(factory)

    task = executor._create_task(
        agent=factory.product_analyst("structure-requirements"),
        description="结构化需求",
        expected_output="RequirementStructureResult JSON",
        output_model=RequirementStructureResult,
    )

    assert task.output_pydantic is None
    assert "JSON Schema" in task.description
    assert '"requirementSpec"' in task.description


def test_openai_task_uses_native_structured_output() -> None:
    factory = AgentFactory(
        Settings(
            _env_file=None,
            database_url=DATABASE_URL,
            test_database_url=TEST_DATABASE_URL,
            llm_model="gpt-4o-mini",
            llm_provider="openai",
            llm_api_key="test",
        )
    )
    executor = CrewAITaskExecutor(factory)

    task = executor._create_task(
        agent=factory.product_analyst("structure-requirements"),
        description="结构化需求",
        expected_output="RequirementStructureResult JSON",
        output_model=RequirementStructureResult,
    )

    assert task.output_pydantic is RequirementStructureResult
    assert "JSON Schema" not in task.description
