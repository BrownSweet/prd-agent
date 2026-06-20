from __future__ import annotations

import pytest

from prd_agent.models import (
    ClarificationQuestion,
    CompletenessAssessment,
    LogicValidationResult,
    ProductTypeCode,
    ProductTypeSelection,
    RequirementStructureResult,
    reconcile_questions,
)


def test_question_ids_are_normalized_and_stable() -> None:
    first = reconcile_questions(
        [],
        [
            ClarificationQuestion(
                question_id="Q-999",
                question_type="模块",
                description="覆盖哪些模块？",
                importance="决定范围",
            )
        ],
        [],
        None,
    )
    assert first[0].question_id == "Q-001"

    second = reconcile_questions(
        first,
        [
            ClarificationQuestion(
                question_id="Q-888",
                question_type="模块",
                description="覆盖哪些模块？",
                importance="决定范围",
            )
        ],
        [],
        None,
    )
    assert second[0].question_id == "Q-001"


def test_structure_result_ignores_untrusted_source_inputs() -> None:
    result = RequirementStructureResult.model_validate(
        {
            "requirementSpec": {
                "title": "Telegram频道监听",
                "summary": "读取频道消息并分析交易标的",
                "sourceInputs": [{"text": b"\xff"}],
                "completeness": CompletenessAssessment().model_dump(
                    mode="json", by_alias=True
                ),
            },
            "questions": [],
            "resolvedQuestionIds": [],
            "summaryMarkdown": "待澄清",
        }
    )

    assert result.requirement_spec.source_inputs == []


def test_logic_result_ignores_untrusted_source_inputs() -> None:
    result = LogicValidationResult.model_validate(
        {
            "requirementSpec": {
                "sourceInputs": [{"text": b"\xff"}],
            },
            "issues": [],
            "resolvedIssueIds": [],
            "summaryMarkdown": "扫描完成",
        }
    )

    assert result.requirement_spec.source_inputs == []


@pytest.mark.parametrize("primary", list(ProductTypeCode))
def test_all_six_product_types_are_supported(primary: ProductTypeCode) -> None:
    selection = ProductTypeSelection(
        primary=primary,
        secondary=[ProductTypeCode.API, primary],
        matched_features=["特征"],
        rationale="测试",
    )
    assert primary not in selection.secondary
