from __future__ import annotations

import pytest

from prd_agent.gates import (
    WorkflowGateError,
    assert_logic_ready,
    assert_structure_ready,
    transition,
)
from prd_agent.models import (
    ClarificationQuestion,
    LogicIssue,
    ProjectState,
    Severity,
    Stage,
)

from conftest import complete_spec


def test_structure_gate_requires_all_five_dimensions() -> None:
    state = ProjectState(requirement_spec=complete_spec())
    assert_structure_ready(state)

    state.requirement_spec.completeness.dependencies_clear = False
    with pytest.raises(WorkflowGateError, match="依赖关系"):
        assert_structure_ready(state)


def test_structure_gate_rejects_open_question() -> None:
    state = ProjectState(
        requirement_spec=complete_spec(),
        questions=[
            ClarificationQuestion(
                question_id="Q-001",
                question_type="边界",
                description="上限是多少？",
                importance="决定校验规则",
            )
        ],
    )
    with pytest.raises(WorkflowGateError, match="未解决"):
        assert_structure_ready(state)


def test_logic_gate_rejects_blocking_and_important() -> None:
    state = ProjectState(
        logic_issues=[
            LogicIssue(
                issue_id="L-001",
                dimension="异常",
                description="失败后行为未知",
                severity=Severity.BLOCKING,
            ),
            LogicIssue(
                issue_id="L-002",
                dimension="交互",
                description="反馈方式未知",
                severity=Severity.IMPORTANT,
            ),
        ]
    )
    with pytest.raises(WorkflowGateError) as raised:
        assert_logic_ready(state)
    assert len(raised.value.errors) == 2


def test_illegal_transition_is_rejected() -> None:
    state = ProjectState(stage=Stage.STRUCTURING)
    with pytest.raises(WorkflowGateError, match="非法阶段迁移"):
        transition(state, Stage.PRD_GENERATING)

